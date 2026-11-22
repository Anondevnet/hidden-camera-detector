"""Combine evidence into a 0-100 camera-likelihood score with reasons."""

from __future__ import annotations

import re

from hcd.models import DeviceFinding, Likelihood, Reason
from hcd.vendors import VendorHit

CAMERA_NAME_PATTERNS = [
    r"\bhikvision\b",
    r"\bhik-?connect\b",
    r"\bdahua\b",
    r"\bamcrest\b",
    r"\breolink\b",
    r"\bwyze\b",
    r"\beufy\b",
    r"\btapo\b",
    r"\bfoscam\b",
    r"\bezviz\b",
    r"\bimou\b",
    r"\buniview\b",
    r"\blorex\b",
    r"\bswann\b",
    r"\barlo\b",
    r"\bblink\b",
    r"\bnest[-_ ]?cam",
    r"\bring[-_ ]?(cam|doorbell)",
    r"\bonvif\b",
    r"\bipcam\b",
    r"\bip-?camera\b",
    r"\bnetwork[-_ ]?camera\b",
    r"\bsecurity[-_ ]?cam",
    r"\bcamera\b",
    r"\bwebcam\b",
    r"\bnvr\b",
    r"\bdvr\b",
    r"\bipc[_-]?\d",
    r"^ipc\b",
    r"^cam[-_\d]",
    r"\bcctv\b",
    r"\baxis[-_ ]?cam",
]

# Ports commonly bound by IP cameras, NVRs, or their vendor tools.
CAMERA_PORTS = {
    554: ("rtsp", 35, "TCP 554 open (RTSP, used to stream camera video)"),
    8554: ("rtsp-alt", 20, "TCP 8554 open (alternate RTSP)"),
    37777: ("dahua-dvr", 30, "TCP 37777 open (Dahua / Amcrest media service)"),
    34567: ("xm-sofia", 30, "TCP 34567 open (XM / Sofia / many generic IPC kits)"),
    8899: ("onvif-alt", 15, "TCP 8899 open (often ONVIF on Hikvision-family devices)"),
    8000: ("vendor-http", 10, "TCP 8000 open (common vendor HTTP / SDK port)"),
    80: ("http", 5, "TCP 80 open (HTTP)"),
    8080: ("http-alt", 5, "TCP 8080 open (alternate HTTP)"),
    443: ("https", 3, "TCP 443 open (HTTPS)"),
}

HTTP_STRONG = [
    (re.compile(r"hikvision|dnvrs-webs|app-webs|dvrdvs|hipcam", re.I), "Hikvision-family HTTP fingerprint"),
    (re.compile(r"dahua|dnvrs", re.I), "Dahua-family HTTP fingerprint"),
    (re.compile(r"amcrest", re.I), "Amcrest HTTP fingerprint"),
    (re.compile(r"reolink", re.I), "Reolink HTTP fingerprint"),
    (re.compile(r"wyze", re.I), "Wyze HTTP fingerprint"),
    (re.compile(r"onvif", re.I), "ONVIF mentioned in an HTTP response"),
]

HTTP_WEAK = [
    (re.compile(r"goahead", re.I), "GoAhead embedded web server (common on cheap IPCs, also used elsewhere)"),
    (re.compile(r"\bwebserver\b", re.I), "Generic 'webserver' banner (seen on some Dahua/Amcrest units)"),
]


def likelihood_for(score: int) -> Likelihood:
    if score >= 70:
        return Likelihood.HIGHLY_LIKELY
    if score >= 40:
        return Likelihood.LIKELY
    if score >= 20:
        return Likelihood.POSSIBLE
    return Likelihood.UNLIKELY


def name_matches(text: str | None) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    for pattern in CAMERA_NAME_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            hits.append(pattern)
    return hits


def vendor_weight(hit: VendorHit | None) -> tuple[int, str] | None:
    if hit is None:
        return None
    if hit.role == "camera":
        return 50, f"MAC OUI {hit.prefix} is registered to {hit.name} (camera / surveillance vendor)"
    if hit.role == "mixed":
        return 15, (f"MAC OUI {hit.prefix} is registered to {hit.name}, which ships cameras and other products")
    return 5, (f"MAC OUI {hit.prefix} is registered to {hit.name} (generic IoT chipset / platform; weak alone)")


def score_device(
    finding: DeviceFinding,
    vendor: VendorHit | None = None,
) -> DeviceFinding:
    reasons: list[Reason] = list(finding.reasons)
    total = 0

    def add(code: str, detail: str, weight: int) -> None:
        nonlocal total
        if weight == 0:
            return
        reasons.append(Reason(code=code, detail=detail, weight=weight))
        total += weight

    vw = vendor_weight(vendor)
    if vendor is not None:
        finding.vendor_id = vendor.vendor_id
        finding.vendor_name = vendor.name
        finding.vendor_role = vendor.role
    if vw:
        add("oui", vw[1], vw[0])

    if finding.randomized_mac:
        add(
            "randomized-mac",
            "MAC is locally administered (often randomized); vendor lookup does not apply",
            0,
        )

    for port in sorted(set(finding.open_ports)):
        if port in CAMERA_PORTS:
            _code, weight, detail = CAMERA_PORTS[port]
            add(f"port-{port}", detail, weight)

    for service in finding.services:
        sl = service.lower()
        if "onvif" in sl:
            add("onvif", f"Discovered via ONVIF / WS-Discovery ({service})", 40)
        elif "rtsp" in sl:
            add("mdns-rtsp", f"Advertised an RTSP service ({service})", 40)
        elif "axis-video" in sl:
            add("axis-video", f"Advertised an Axis video service ({service})", 40)
        elif "ssdp" in sl or "upnp" in sl:
            add("ssdp", f"SSDP / UPnP advertisement ({service})", 10)

    for fp in finding.http_fingerprints:
        matched = False
        for pattern, label in HTTP_STRONG:
            if pattern.search(fp):
                add("http-fingerprint", f"{label}: {fp[:120]}", 25)
                matched = True
                break
        if matched:
            continue
        for pattern, label in HTTP_WEAK:
            if pattern.search(fp):
                add("http-banner", f"{label}: {fp[:120]}", 8)
                break

    name_sources = [finding.hostname or "", " ".join(finding.services)]
    if any(name_matches(src) for src in name_sources):
        blob = " ".join(s for s in name_sources if s)
        add("name", f"Hostname or service name looks camera-related: {blob[:160]}", 20)

    finding.reasons = reasons
    finding.score = max(0, min(100, total))
    finding.likelihood = likelihood_for(finding.score)
    return finding
