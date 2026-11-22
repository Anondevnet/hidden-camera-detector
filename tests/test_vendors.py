from __future__ import annotations

import pytest

from hcd.vendors import (
    is_locally_administered,
    lookup_mac,
    mac_hex,
    normalize_mac,
    prefix_index,
    registry_meta,
    vendor_records,
)


def test_normalize_and_hex() -> None:
    assert normalize_mac("c0-56-e3-01-02-03") == "C0:56:E3:01:02:03"
    assert mac_hex("c0:56:e3:01:02:03") == "C056E3010203"
    with pytest.raises(ValueError):
        normalize_mac("c0:56:e3")


def test_randomized_mac() -> None:
    # Second-least-significant bit of the first octet marks locally administered.
    assert is_locally_administered("02:00:00:00:00:01")
    assert not is_locally_administered("00:11:22:33:44:55")


def test_hikvision_and_dahua_prefixes() -> None:
    hik = lookup_mac("C0:56:E3:AA:BB:CC")
    assert hik is not None
    assert hik.vendor_id == "hikvision"
    assert hik.role == "camera"
    dahua = lookup_mac("90-02-a9-00-00-01")
    assert dahua is not None
    assert dahua.vendor_id == "dahua"


def test_espressif_is_generic_iot() -> None:
    hit = lookup_mac("EC:FA:BC:11:22:33")
    assert hit is not None
    assert hit.vendor_id == "espressif"
    assert hit.role == "generic_iot"


def test_unknown_and_randomized_do_not_match() -> None:
    assert lookup_mac("00:11:22:33:44:55") is None
    # Locally administered addresses can still be looked up if someone asks,
    # but the first octet is usually not an IEEE assignment. 02:00:00 is not bundled.
    assert lookup_mac("02:00:00:00:00:01") is None


def test_registry_is_labelled_ieee_snapshot() -> None:
    meta = registry_meta()
    assert "IEEE" in meta["registry"]
    assert meta["url"].startswith("https://standards-oui.ieee.org/")
    vendors = vendor_records()
    names = {v["id"] for v in vendors}
    for expected in {"hikvision", "dahua", "reolink", "wyze", "amcrest", "ring", "blink"}:
        assert expected in names
    assert len(prefix_index()) >= 200
