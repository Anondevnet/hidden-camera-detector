"""ONVIF WS-Discovery, mDNS, and SSDP / UPnP parsers and live probes."""

from __future__ import annotations

import re
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree

ONVIF_MULTICAST = ("239.255.255.250", 3702)
SSDP_MULTICAST = ("239.255.255.250", 1900)

MDNS_TYPES = (
    "_onvif._tcp.local.",
    "_rtsp._tcp.local.",
    "_axis-video._tcp.local.",
    "_http._tcp.local.",
)

_CAMERAISH = re.compile(
    r"onvif|rtsp|axis-video|hikvision|dahua|amcrest|reolink|wyze|eufy|tapo|"
    r"foscam|ezviz|imou|uniview|lorex|camera|ipcam|nvr|dvr|ipc",
    re.I,
)

UdpReplies = list[tuple[str, str]]
UdpSender = Callable[[tuple[str, int], bytes, float], UdpReplies]


@dataclass(frozen=True)
class DiscoveredService:
    protocol: str
    name: str
    address: str | None = None
    port: int | None = None
    details: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def onvif_probe_xml() -> bytes:
    message_id = f"uuid:{uuid.uuid4()}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
        ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
        ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        "<e:Header>"
        f"<w:MessageID>{message_id}</w:MessageID>"
        "<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>"
        "<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>"
        "</e:Header>"
        "<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>"
        "</e:Envelope>"
    ).encode()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def parse_onvif_probe_match(xml_text: str, source_ip: str | None = None) -> DiscoveredService | None:
    root = _parse_xml(xml_text)
    if root is None:
        return None

    texts: list[str] = []
    xaddrs: list[str] = []
    types: list[str] = []
    scopes: list[str] = []
    for node in root.iter():
        name = _local(node.tag).lower()
        value = (node.text or "").strip()
        if not value:
            continue
        texts.append(value)
        if name == "xaddrs":
            xaddrs.extend(value.split())
        elif name == "types":
            types.extend(value.split())
        elif name == "scopes":
            scopes.extend(value.split())

    blob = " ".join(texts)
    if "onvif" not in blob.lower() and "networkvideotransmitter" not in blob.lower() and not xaddrs:
        return None

    address = source_ip
    port: int | None = None
    if xaddrs:
        host, port = _host_port_from_url(xaddrs[0])
        address = host or address
    detail_parts: list[str] = []
    if types:
        detail_parts.append("types=" + " ".join(types[:4]))
    if xaddrs:
        detail_parts.append("xaddrs=" + " ".join(xaddrs[:2]))
    names = [scope.rsplit("/", 1)[-1] for scope in scopes if "/name/" in scope.lower()]
    if names:
        detail_parts.append("name=" + names[0])
    return DiscoveredService(
        protocol="onvif",
        name="onvif",
        address=address,
        port=port,
        details="; ".join(detail_parts),
        tags=("onvif",),
    )


def _parse_xml(xml_text: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        start = xml_text.find("<")
        if start < 0:
            return None
        try:
            return ElementTree.fromstring(xml_text[start:])
        except ElementTree.ParseError:
            return None


def _host_port_from_url(url: str) -> tuple[str | None, int | None]:
    match = re.search(r"https?://([^/:]+|\[[^\]]+])(?::(\d+))?", url)
    if not match:
        return None, None
    host = match.group(1).strip("[]")
    if match.group(2):
        port = int(match.group(2))
    elif url.lower().startswith("https"):
        port = 443
    else:
        port = 80
    return host, port


def ssdp_search_payload(st: str = "ssdp:all", mx: int = 2) -> bytes:
    return (
        f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: {mx}\r\nST: {st}\r\n\r\n'
    ).encode("ascii")


def parse_ssdp_response(text: str, source_ip: str | None = None) -> DiscoveredService | None:
    lines = [ln.strip() for ln in re.split(r"\r?\n", text) if ln.strip()]
    if not lines:
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().upper()] = value.strip()
    location = fields.get("LOCATION", "")
    server = fields.get("SERVER", "")
    usn = fields.get("USN", "")
    st = fields.get("ST", fields.get("NT", ""))
    blob = " ".join([location, server, usn, st])
    if not blob.strip():
        return None
    cameraish = bool(_CAMERAISH.search(blob))
    host, port = _host_port_from_url(location) if location else (source_ip, None)
    tags: tuple[str, ...] = ("ssdp", "camera-hint") if cameraish else ("ssdp",)
    return DiscoveredService(
        protocol="ssdp",
        name=st or server or "ssdp",
        address=host or source_ip,
        port=port,
        details=blob[:300],
        tags=tags,
    )


def parse_mdns_browse(
    service_type: str,
    instance_name: str,
    address: str | None,
    port: int | None,
    properties: dict[str, str] | None = None,
) -> DiscoveredService:
    props = properties or {}
    blob = " ".join([service_type, instance_name, *props.values()])
    tags: list[str] = ["mdns"]
    st = service_type.lower()
    if "onvif" in st:
        tags.append("onvif")
    if "rtsp" in st:
        tags.append("rtsp")
    if "axis-video" in st:
        tags.append("axis-video")
    if _CAMERAISH.search(blob):
        tags.append("camera-hint")
    return DiscoveredService(
        protocol="mdns",
        name=f"{instance_name} ({service_type})",
        address=address,
        port=port,
        details=blob[:300],
        tags=tuple(dict.fromkeys(tags)),
    )


def live_onvif_discover(timeout: float = 2.0, send: UdpSender | None = None) -> list[DiscoveredService]:
    replies = (send or _udp_multicast_collect)(ONVIF_MULTICAST, onvif_probe_xml(), timeout)
    found: list[DiscoveredService] = []
    for source, payload in replies:
        parsed = parse_onvif_probe_match(payload, source_ip=source)
        if parsed:
            found.append(parsed)
    return found


def live_ssdp_discover(timeout: float = 2.0, send: UdpSender | None = None) -> list[DiscoveredService]:
    replies = (send or _udp_multicast_collect)(SSDP_MULTICAST, ssdp_search_payload(), timeout)
    found: list[DiscoveredService] = []
    for source, payload in replies:
        parsed = parse_ssdp_response(payload, source_ip=source)
        if parsed:
            found.append(parsed)
    return found


def live_mdns_browse(timeout: float = 2.0) -> list[DiscoveredService]:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return []

    found: list[DiscoveredService] = []

    class _Listener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
            address = None
            port = None
            props: dict[str, str] = {}
            if info is not None:
                port = info.port
                if info.addresses:
                    address = socket.inet_ntoa(info.addresses[0])
                for key, value in (info.properties or {}).items():
                    k = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
                    v = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value or "")
                    props[k] = v
            found.append(parse_mdns_browse(type_, name, address, port, props))

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            return

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            return

    zc = Zeroconf()
    try:
        listener = _Listener()
        browsers = [ServiceBrowser(zc, stype, listener) for stype in MDNS_TYPES]
        time.sleep(timeout)
        for browser in browsers:
            browser.cancel()
    finally:
        zc.close()
    return found


def _udp_multicast_collect(
    target: tuple[str, int],
    payload: bytes,
    timeout: float = 2.0,
) -> UdpReplies:
    replies: UdpReplies = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.sendto(payload, target)
        sock.settimeout(0.25)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                break
            replies.append((addr[0], data.decode("utf-8", errors="replace")))
    finally:
        sock.close()
    return replies
