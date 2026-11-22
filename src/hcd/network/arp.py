"""Parse neighbor / ARP tables and guess the local IPv4 CIDR."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Neighbor:
    ip: str
    mac: str
    interface: str | None = None
    source: str = "arp"


_IP_NEIGH = re.compile(
    r"^(?P<ip>\S+)\s+dev\s+(?P<dev>\S+)(?:\s+lladdr\s+(?P<mac>[0-9a-fA-F:.-]+))?",
    re.M,
)
_ARP_AN = re.compile(
    r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:.-]+)",
)
_PROC_MAC = re.compile(r"^[0-9a-fA-F]{1,2}([:-][0-9a-fA-F]{1,2}){5}$")


def parse_ip_neigh(text: str) -> list[Neighbor]:
    found: list[Neighbor] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        if "FAILED" in line or "lladdr" not in line:
            continue
        match = _IP_NEIGH.search(line)
        if not match or not match.group("mac"):
            continue
        ip = match.group("ip")
        try:
            ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            continue
        mac = match.group("mac")
        key = (ip, mac.lower())
        if key in seen:
            continue
        seen.add(key)
        found.append(Neighbor(ip=ip, mac=mac, interface=match.group("dev"), source="ip-neigh"))
    return found


def parse_arp_an(text: str) -> list[Neighbor]:
    found: list[Neighbor] = []
    seen: set[tuple[str, str]] = set()
    for match in _ARP_AN.finditer(text):
        ip, mac = match.group("ip"), match.group("mac")
        if mac.lower() in {"<incomplete>", "(incomplete)"}:
            continue
        key = (ip, mac.lower())
        if key in seen:
            continue
        seen.add(key)
        found.append(Neighbor(ip=ip, mac=mac, source="arp-an"))
    return found


def parse_proc_net_arp(text: str) -> list[Neighbor]:
    found: list[Neighbor] = []
    lines = text.splitlines()
    if not lines:
        return found
    # IP, HW type, Flags, HW address, Mask, Device
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        ip, flags, mac, _mask, dev = parts[0], parts[2], parts[3], parts[4], parts[5]
        if mac == "00:00:00:00:00:00":
            continue
        try:
            if int(flags, 0) == 0:
                continue
        except ValueError:
            continue
        if not _PROC_MAC.match(mac):
            continue
        found.append(Neighbor(ip=ip, mac=mac, interface=dev, source="proc-net-arp"))
    return found


def guess_local_cidr() -> str:
    """Best-effort IPv4 CIDR for the default-route interface (assumes /24 if unknown)."""
    env = os.environ.get("HCD_CIDR")
    if env:
        return env
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        sock.close()
    return str(ipaddress.ip_network(f"{ip}/24", strict=False))


def iter_targets(cidr: str) -> list[str]:
    network = ipaddress.ip_network(cidr, strict=False)
    if network.num_addresses > 4096:
        raise ValueError(f"refusing to sweep {cidr}: too many addresses")
    return [str(ip) for ip in network.hosts()]


def read_neighbors_from_system() -> list[Neighbor]:
    chunks: list[Neighbor] = []
    proc = _read_text("/proc/net/arp")
    if proc:
        chunks.extend(parse_proc_net_arp(proc))
    if not chunks:
        text = _run(["ip", "neigh", "show"])
        if text:
            chunks.extend(parse_ip_neigh(text))
    if not chunks:
        text = _run(["arp", "-an"])
        if text:
            chunks.extend(parse_arp_an(text))
    return _dedupe(chunks)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _run(argv: list[str]) -> str | None:
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 and not result.stdout:
        return None
    return result.stdout


def _dedupe(items: list[Neighbor]) -> list[Neighbor]:
    seen: set[tuple[str, str]] = set()
    out: list[Neighbor] = []
    for item in items:
        key = (item.ip, item.mac.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
