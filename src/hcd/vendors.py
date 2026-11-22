"""Bundled IEEE MA-L (OUI) lookup for camera and IoT vendors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class VendorHit:
    vendor_id: str
    name: str
    role: str
    prefix: str
    note: str | None = None


def normalize_mac(mac: str) -> str:
    hexdigits = "".join(c for c in mac.upper() if c in "0123456789ABCDEF")
    if len(hexdigits) != 12:
        raise ValueError(f"not a 48-bit MAC address: {mac!r}")
    return ":".join(hexdigits[i : i + 2] for i in range(0, 12, 2))


def mac_hex(mac: str) -> str:
    return "".join(c for c in normalize_mac(mac) if c != ":")


def is_locally_administered(mac: str) -> bool:
    first = int(normalize_mac(mac).split(":")[0], 16)
    return bool(first & 0x02)


def is_multicast_mac(mac: str) -> bool:
    first = int(normalize_mac(mac).split(":")[0], 16)
    return bool(first & 0x01)


@lru_cache(maxsize=1)
def _payload() -> dict[str, Any]:
    data = resources.files("hcd.data").joinpath("camera_vendors.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(data)
    return loaded


@lru_cache(maxsize=1)
def prefix_index() -> dict[str, VendorHit]:
    index: dict[str, VendorHit] = {}
    for vendor in _payload()["vendors"]:
        note = vendor.get("note")
        for prefix in vendor["prefixes"]:
            index[prefix.upper()] = VendorHit(
                vendor_id=vendor["id"],
                name=vendor["name"],
                role=vendor["role"],
                prefix=prefix.upper(),
                note=note,
            )
    return index


def vendor_records() -> list[dict[str, Any]]:
    return list(_payload()["vendors"])


def registry_meta() -> dict[str, Any]:
    return dict(_payload()["source"])


def lookup_mac(mac: str) -> VendorHit | None:
    try:
        key = mac_hex(mac)[:6]
    except ValueError:
        return None
    return prefix_index().get(key)
