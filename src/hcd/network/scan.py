"""Orchestrate neighbor discovery, port probes, and service fingerprints."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol

from hcd.models import DeviceFinding, NetworkScanReport
from hcd.network.arp import Neighbor, guess_local_cidr, iter_targets, read_neighbors_from_system
from hcd.network.discovery import (
    DiscoveredService,
    live_mdns_browse,
    live_onvif_discover,
    live_ssdp_discover,
)
from hcd.network.ports import DEFAULT_PORTS, fetch_http_banner, probe_ports
from hcd.scoring import score_device
from hcd.vendors import is_locally_administered, lookup_mac, normalize_mac


class NetworkBackend(Protocol):
    """Injectable I/O so unit tests never touch a real network."""

    def neighbors(self) -> list[Neighbor]: ...

    def probe_ports(self, ip: str, ports: Iterable[int], timeout: float) -> list[int]: ...

    def http_banner(self, ip: str, port: int, timeout: float) -> str | None: ...

    def discover(self, timeout: float) -> list[DiscoveredService]: ...

    def sweep_hosts(self, cidr: str) -> None:
        """Optional active touch of the subnet so the ARP table fills in."""


@dataclass
class LiveNetworkBackend:
    """Real sockets, neighbor tables, and multicast discovery."""

    def neighbors(self) -> list[Neighbor]:
        return read_neighbors_from_system()

    def probe_ports(self, ip: str, ports: Iterable[int], timeout: float) -> list[int]:
        return probe_ports(ip, ports, timeout=timeout)

    def http_banner(self, ip: str, port: int, timeout: float) -> str | None:
        return fetch_http_banner(ip, port, timeout=timeout)

    def discover(self, timeout: float) -> list[DiscoveredService]:
        found: list[DiscoveredService] = []
        found.extend(live_onvif_discover(timeout=timeout))
        found.extend(live_ssdp_discover(timeout=timeout))
        found.extend(live_mdns_browse(timeout=timeout))
        return found

    def sweep_hosts(self, cidr: str) -> None:
        # A short TCP connect to 80 (or a closed port) is enough to populate ARP
        # on many OSes without needing raw ICMP sockets / root.
        hosts = iter_targets(cidr)

        def _touch(ip: str) -> None:
            probe_ports(ip, ports=(80,), timeout=0.15)

        with ThreadPoolExecutor(max_workers=64) as pool:
            list(pool.map(_touch, hosts))


@dataclass
class StaticNetworkBackend:
    """Deterministic backend for tests and demos."""

    neighbor_list: list[Neighbor] = field(default_factory=list)
    open_ports: dict[str, list[int]] = field(default_factory=dict)
    banners: dict[tuple[str, int], str] = field(default_factory=dict)
    services: list[DiscoveredService] = field(default_factory=list)
    swept: list[str] = field(default_factory=list)

    def neighbors(self) -> list[Neighbor]:
        return list(self.neighbor_list)

    def probe_ports(self, ip: str, ports: Iterable[int], timeout: float) -> list[int]:
        known = set(self.open_ports.get(ip, []))
        return [port for port in ports if port in known]

    def http_banner(self, ip: str, port: int, timeout: float) -> str | None:
        return self.banners.get((ip, port))

    def discover(self, timeout: float) -> list[DiscoveredService]:
        return list(self.services)

    def sweep_hosts(self, cidr: str) -> None:
        self.swept.append(cidr)


def scan_network(
    cidr: str | None = None,
    *,
    backend: NetworkBackend | None = None,
    ports: Iterable[int] = DEFAULT_PORTS,
    timeout: float = 0.4,
    discovery_timeout: float = 2.0,
    sweep: bool = True,
    workers: int = 32,
) -> NetworkScanReport:
    io = backend or LiveNetworkBackend()
    net = cidr or guess_local_cidr()
    if sweep:
        io.sweep_hosts(net)

    services = io.discover(discovery_timeout)
    neighbors = io.neighbors()

    by_ip: dict[str, DeviceFinding] = {}

    def ensure(ip: str | None, mac: str | None = None) -> DeviceFinding | None:
        if not ip:
            return None
        try:
            ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            return None
        finding = by_ip.get(ip)
        if finding is None:
            finding = DeviceFinding(ip=ip)
            by_ip[ip] = finding
        if mac and not finding.mac:
            try:
                finding.mac = normalize_mac(mac)
                finding.randomized_mac = is_locally_administered(finding.mac)
            except ValueError:
                finding.mac = mac
        return finding

    for neighbor in neighbors:
        ensure(neighbor.ip, neighbor.mac)

    for service in services:
        finding = ensure(service.address)
        if finding is None:
            continue
        label = service.protocol
        if service.name:
            label = f"{service.protocol}:{service.name}"
        if service.tags:
            label = f"{label}[{','.join(service.tags)}]"
        if label not in finding.services:
            finding.services.append(label)
        if finding.hostname is None and service.details:
            finding.hostname = service.details[:120]
        if service.port and service.port not in finding.open_ports:
            # Discovery advertised a port; still confirm later if we probe this host.
            pass

    # Probe every known host, plus discovery addresses, on the camera port set.
    targets = list(by_ip.keys())
    http_ports = [port for port in ports if port in {80, 8080, 8000, 443}]

    def _probe(ip: str) -> tuple[str, list[int], list[str]]:
        open_ports = io.probe_ports(ip, list(ports), timeout)
        banners: list[str] = []
        for port in open_ports:
            if port in http_ports:
                banner = io.http_banner(ip, port, max(timeout, 0.6))
                if banner:
                    banners.append(f"{port}: {banner}")
        return ip, open_ports, banners

    if targets:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_probe, ip) for ip in targets]
            for future in as_completed(futures):
                ip, open_ports, banners = future.result()
                finding = by_ip[ip]
                for port in open_ports:
                    if port not in finding.open_ports:
                        finding.open_ports.append(port)
                for banner in banners:
                    if banner not in finding.http_fingerprints:
                        finding.http_fingerprints.append(banner)

    devices: list[DeviceFinding] = []
    for finding in by_ip.values():
        vendor = lookup_mac(finding.mac) if finding.mac and not finding.randomized_mac else None
        devices.append(score_device(finding, vendor=vendor))
    devices.sort(key=lambda item: (-item.score, item.ip or ""))
    return NetworkScanReport(cidr=net, devices=devices)
