from __future__ import annotations

from hcd.network.arp import (
    Neighbor,
    iter_targets,
    parse_arp_an,
    parse_ip_neigh,
    parse_proc_net_arp,
)
from hcd.network.discovery import DiscoveredService
from hcd.network.scan import StaticNetworkBackend, scan_network

IP_NEIGH = """
192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.168.1.20 dev wlan0 lladdr c0:56:e3:01:02:03 STALE
fe80::1 dev wlan0 lladdr 11:22:33:44:55:66 REACHABLE
192.168.1.30 dev wlan0 FAILED
"""

ARP_AN = """
? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on en0
? (192.168.1.20) at c0:56:e3:01:02:03 [ether] on en0
? (192.168.1.99) at <incomplete> on en0
"""

PROC = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         aa:bb:cc:dd:ee:ff     *        wlan0
192.168.1.20     0x1         0x2         c0:56:e3:01:02:03     *        wlan0
192.168.1.77     0x1         0x0         00:00:00:00:00:00     *        wlan0
"""


def test_parse_ip_neigh_skips_ipv6_and_failed() -> None:
    neighbors = parse_ip_neigh(IP_NEIGH)
    ips = {item.ip for item in neighbors}
    assert ips == {"192.168.1.1", "192.168.1.20"}
    cam = next(item for item in neighbors if item.ip.endswith(".20"))
    assert cam.mac.lower().startswith("c0:56:e3")


def test_parse_arp_an_and_proc() -> None:
    assert {n.ip for n in parse_arp_an(ARP_AN)} == {"192.168.1.1", "192.168.1.20"}
    proc = parse_proc_net_arp(PROC)
    assert {n.ip for n in proc} == {"192.168.1.1", "192.168.1.20"}


def test_iter_targets_skips_network_and_broadcast() -> None:
    hosts = iter_targets("192.168.1.0/30")
    assert "192.168.1.1" in hosts
    assert "192.168.1.0" not in hosts


def test_scan_network_uses_backend_only() -> None:
    backend = StaticNetworkBackend(
        neighbor_list=[
            Neighbor(ip="192.168.1.20", mac="c0:56:e3:01:02:03"),
            Neighbor(ip="192.168.1.10", mac="00:11:22:33:44:55"),
        ],
        open_ports={"192.168.1.20": [554, 80], "192.168.1.10": [80]},
        banners={("192.168.1.20", 80): "HTTP/1.0 200 OK | Server: Hikvision-Webs"},
        services=[
            DiscoveredService(
                protocol="onvif",
                name="onvif",
                address="192.168.1.20",
                tags=("onvif",),
                details="types=dn:NetworkVideoTransmitter",
            )
        ],
    )
    report = scan_network(cidr="192.168.1.0/24", backend=backend, sweep=True, discovery_timeout=0)
    assert backend.swept == ["192.168.1.0/24"]
    by_ip = {device.ip: device for device in report.devices}
    cam = by_ip["192.168.1.20"]
    assert cam.score >= 70
    assert cam.vendor_id == "hikvision"
    assert 554 in cam.open_ports
    laptop = by_ip["192.168.1.10"]
    assert laptop.score < 40
