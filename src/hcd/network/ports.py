"""TCP connect probes and short HTTP banner / Server-header fingerprints."""

from __future__ import annotations

import socket
from collections.abc import Iterable

DEFAULT_PORTS = (554, 80, 8080, 8000, 37777, 34567)

# Extra ports that are useful but not in the default sweep list.
OPTIONAL_PORTS = (443, 8554, 8899)


def probe_tcp(ip: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_ports(
    ip: str,
    ports: Iterable[int] = DEFAULT_PORTS,
    timeout: float = 0.4,
) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        if probe_tcp(ip, port, timeout=timeout):
            open_ports.append(port)
    return open_ports


def fetch_http_banner(ip: str, port: int = 80, timeout: float = 0.8) -> str | None:
    """Send a minimal HTTP HEAD and return the status line plus Server / auth hints."""
    request = f"HEAD / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: hcd/0.1\r\nConnection: close\r\n\r\n"
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request.encode("ascii"))
            chunks: list[bytes] = []
            while sum(len(part) for part in chunks) < 4096:
                data = sock.recv(1024)
                if not data:
                    break
                chunks.append(data)
    except OSError:
        return None
    raw = b"".join(chunks)
    text = raw.decode("utf-8", errors="replace")
    header = text.split("\r\n\r\n", 1)[0]
    if not header:
        return None
    lines = header.splitlines()
    interesting: list[str] = []
    if lines:
        interesting.append(lines[0].strip())
    for line in lines[1:]:
        lower = line.lower()
        if lower.startswith("server:") or lower.startswith("www-authenticate:"):
            interesting.append(line.strip())
    return " | ".join(interesting) if interesting else header[:200]
