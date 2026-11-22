from __future__ import annotations

from hcd.models import DeviceFinding, Likelihood
from hcd.scoring import score_device
from hcd.vendors import lookup_mac


def test_hikvision_plus_rtsp_is_highly_likely() -> None:
    vendor = lookup_mac("C0:56:E3:01:02:03")
    finding = DeviceFinding(ip="192.168.1.20", mac="C0:56:E3:01:02:03", open_ports=[554, 80])
    scored = score_device(finding, vendor=vendor)
    assert scored.score >= 70
    assert scored.likelihood is Likelihood.HIGHLY_LIKELY
    codes = {reason.code for reason in scored.reasons}
    assert "oui" in codes
    assert "port-554" in codes


def test_espressif_alone_is_weak() -> None:
    vendor = lookup_mac("24:0A:C4:00:00:01")
    finding = DeviceFinding(ip="192.168.1.30", mac="24:0A:C4:00:00:01")
    scored = score_device(finding, vendor=vendor)
    assert scored.score < 20
    assert scored.likelihood is Likelihood.UNLIKELY


def test_hostname_and_onvif_without_oui() -> None:
    finding = DeviceFinding(
        ip="192.168.1.40",
        hostname="Lobby-IPC-04",
        services=["onvif:NetworkVideoTransmitter[onvif]"],
    )
    scored = score_device(finding)
    assert scored.score >= 40
    assert scored.likelihood in {Likelihood.LIKELY, Likelihood.HIGHLY_LIKELY}


def test_http_fingerprint_boosts_generic_host() -> None:
    finding = DeviceFinding(
        ip="192.168.1.50",
        open_ports=[80],
        http_fingerprints=["80: HTTP/1.0 200 OK | Server: Hikvision-Webs"],
    )
    scored = score_device(finding)
    assert scored.score >= 25
    assert any("Hikvision" in reason.detail for reason in scored.reasons)
