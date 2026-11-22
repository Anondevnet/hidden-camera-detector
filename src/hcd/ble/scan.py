from __future__ import annotations

from collections.abc import Iterable, Sequence

from hcd.ble.signatures import (
    camera_name_patterns,
    manufacturer_index,
    tracker_name_patterns,
    weak_camera_name_patterns,
)
from hcd.models import BleFinding, BleScanReport, Reason
from hcd.scoring import likelihood_for


def _maybe_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    raise TypeError(f"expected int-like value, got {type(value)!r}")


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def score_advertisement(
    address: str,
    name: str | None = None,
    rssi: int | None = None,
    manufacturer_id: int | None = None,
) -> BleFinding:
    reasons: list[Reason] = []
    total = 0
    kind = "unknown"
    label: str | None = None
    text = name or ""

    for pattern in tracker_name_patterns():
        if text and _contains(text, pattern):
            reasons.append(
                Reason(code="ble-tracker-name", detail=f"Advertised name looks like a tracker: {name}", weight=40)
            )
            total += 40
            kind = "tracker"
            break

    strong_hit = False
    for pattern in camera_name_patterns():
        if text and _contains(text, pattern):
            reasons.append(
                Reason(
                    code="ble-camera-name",
                    detail=f"Advertised name matches a camera brand or product: {name}",
                    weight=50,
                )
            )
            total += 50
            kind = "camera"
            strong_hit = True
            break
    if not strong_hit:
        for pattern in weak_camera_name_patterns():
            if text and _contains(text, pattern):
                reasons.append(
                    Reason(
                        code="ble-name-weak",
                        detail=f"Advertised name contains a generic 'cam' token: {name}",
                        weight=20,
                    )
                )
                total += 20
                kind = "camera" if kind == "unknown" else kind
                break

    makers = manufacturer_index()
    if manufacturer_id is not None and manufacturer_id in makers:
        meta = makers[manufacturer_id]
        label = str(meta["label"])
        maker_kind = str(meta.get("kind") or "mixed")
        note = meta.get("note") or ""
        if maker_kind == "tracker" or (kind == "tracker"):
            weight = 25 if maker_kind == "tracker" else 10
            reasons.append(
                Reason(
                    code="ble-mfr",
                    detail=f"Manufacturer ID {manufacturer_id:#06x} is {label}. {note}".strip(),
                    weight=weight,
                )
            )
            total += weight
            if maker_kind == "tracker" and kind == "unknown":
                kind = "tracker"
        elif kind == "camera":
            reasons.append(
                Reason(
                    code="ble-mfr",
                    detail=f"Manufacturer ID {manufacturer_id:#06x} is {label}. {note}".strip(),
                    weight=5,
                )
            )
            total += 5
        else:
            reasons.append(
                Reason(
                    code="ble-mfr",
                    detail=(
                        f"Manufacturer ID {manufacturer_id:#06x} is {label} (mixed / common; weak alone). {note}"
                    ).strip(),
                    weight=5,
                )
            )
            total += 5

    finding = BleFinding(
        address=address,
        name=name,
        rssi=rssi,
        manufacturer_id=manufacturer_id,
        manufacturer_label=label,
        kind=kind,
        reasons=reasons,
        score=max(0, min(100, total)),
    )
    finding.likelihood = likelihood_for(finding.score)
    return finding


def score_advertisements(rows: Iterable[dict[str, object]]) -> BleScanReport:
    devices = [
        score_advertisement(
            address=str(row["address"]),
            name=str(row["name"]) if row.get("name") else None,
            rssi=_maybe_int(row.get("rssi")),
            manufacturer_id=_maybe_int(row.get("manufacturer_id")),
        )
        for row in rows
    ]
    devices.sort(key=lambda item: (-item.score, item.address))
    return BleScanReport(devices=devices)


def scan_ble(timeout: float = 8.0) -> BleScanReport:
    """Live adapter scan. Requires the optional `ble` extra (bleak)."""
    try:
        import asyncio

        from bleak import BleakScanner
    except ImportError as exc:
        raise RuntimeError(
            "BLE scanning needs the optional 'ble' extra. Install with: pip install 'hidden-camera-detector[ble]'"
        ) from exc

    async def _run() -> list[dict[str, object]]:
        devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
        rows: list[dict[str, object]] = []
        for address, pair in devices.items():
            device, adv = pair
            mfr_id = None
            if adv.manufacturer_data:
                mfr_id = next(iter(adv.manufacturer_data.keys()))
            rows.append(
                {
                    "address": address,
                    "name": device.name or adv.local_name,
                    "rssi": adv.rssi,
                    "manufacturer_id": mfr_id,
                }
            )
        return rows

    rows = asyncio.run(_run())
    return score_advertisements(rows)


def scan_ble_from_rows(rows: Sequence[dict[str, object]]) -> BleScanReport:
    return score_advertisements(rows)
