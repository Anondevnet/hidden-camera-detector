"""Load bundled BLE name and manufacturer-id hints."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load_signatures() -> dict[str, Any]:
    text = resources.files("hcd.data").joinpath("ble_signatures.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def camera_name_patterns() -> list[str]:
    data = load_signatures()
    return list(data["camera_name_patterns"])


def weak_camera_name_patterns() -> list[str]:
    return list(load_signatures()["weak_camera_name_patterns"])


def tracker_name_patterns() -> list[str]:
    return list(load_signatures()["tracker_name_patterns"])


def manufacturer_index() -> dict[int, dict[str, Any]]:
    return {int(item["id"]): item for item in load_signatures()["manufacturer_ids"]}
