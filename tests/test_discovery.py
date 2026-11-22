from __future__ import annotations

from hcd.network.discovery import (
    onvif_probe_xml,
    parse_mdns_browse,
    parse_onvif_probe_match,
    parse_ssdp_response,
    ssdp_search_payload,
)

ONVIF = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
            xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <s:Body>
    <d:ProbeMatches>
      <d:ProbeMatch>
        <d:Types>dn:NetworkVideoTransmitter</d:Types>
        <d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/LobbyCam</d:Scopes>
        <d:XAddrs>http://192.168.1.20:80/onvif/device_service</d:XAddrs>
      </d:ProbeMatch>
    </d:ProbeMatches>
  </s:Body>
</s:Envelope>
"""

SSDP_CAM = """HTTP/1.1 200 OK\r
CACHE-CONTROL: max-age=1800\r
LOCATION: http://192.168.1.20:8080/device.xml\r
SERVER: IPCamera/1.0 UPnP/1.0\r
ST: urn:schemas-upnp-org:device:Basic:1\r
USN: uuid:cam-20::urn:schemas-upnp-org:device:Basic:1\r
"""

SSDP_PRINTER = """HTTP/1.1 200 OK\r
LOCATION: http://192.168.1.5:80/desc.xml\r
SERVER: OS/1.0 UPnP/1.0 Printer/1.0\r
ST: urn:schemas-upnp-org:device:Printer:1\r
USN: uuid:printer-5\r
"""


def test_onvif_probe_is_well_formed() -> None:
    xml = onvif_probe_xml().decode("utf-8")
    assert "NetworkVideoTransmitter" in xml
    assert "schemas.xmlsoap.org/ws/2005/04/discovery" in xml


def test_parse_onvif_probe_match() -> None:
    service = parse_onvif_probe_match(ONVIF, source_ip="192.168.1.99")
    assert service is not None
    assert service.address == "192.168.1.20"
    assert service.port == 80
    assert "onvif" in service.tags
    assert "LobbyCam" in service.details


def test_ssdp_camera_hint_and_printer() -> None:
    cam = parse_ssdp_response(SSDP_CAM, source_ip="192.168.1.20")
    assert cam is not None
    assert cam.address == "192.168.1.20"
    assert "camera-hint" in cam.tags
    printer = parse_ssdp_response(SSDP_PRINTER)
    assert printer is not None
    assert "camera-hint" not in printer.tags


def test_mdns_onvif_and_plain_http() -> None:
    onvif = parse_mdns_browse("_onvif._tcp.local.", "LobbyCam", "192.168.1.20", 80, {})
    assert "onvif" in onvif.tags
    http = parse_mdns_browse("_http._tcp.local.", "Living Room Speaker", "192.168.1.8", 80, {})
    assert "onvif" not in http.tags
    assert "camera-hint" not in http.tags


def test_ssdp_payload_headers() -> None:
    text = ssdp_search_payload().decode("ascii")
    assert "M-SEARCH * HTTP/1.1" in text
    assert 'MAN: "ssdp:discover"' in text
