from __future__ import annotations

from hcd.ble.scan import score_advertisement, score_advertisements
from hcd.models import Likelihood


def test_wyze_name_is_likely_camera() -> None:
    finding = score_advertisement("AA:BB:CC:DD:EE:01", name="WYZE_CAMxxxxx")
    assert finding.kind == "camera"
    assert finding.score >= 50
    assert finding.likelihood in {Likelihood.LIKELY, Likelihood.HIGHLY_LIKELY}


def test_tile_name_is_tracker() -> None:
    finding = score_advertisement("AA:BB:CC:DD:EE:02", name="Tile Pro")
    assert finding.kind == "tracker"
    assert finding.score >= 40


def test_apple_manufacturer_alone_is_weak() -> None:
    finding = score_advertisement("AA:BB:CC:DD:EE:03", name="John’s iPhone", manufacturer_id=0x004C)
    assert finding.score < 20
    assert finding.manufacturer_label == "Apple"


def test_score_rows_sorts_by_score() -> None:
    report = score_advertisements(
        [
            {"address": "1", "name": "headphones"},
            {"address": "2", "name": "Reolink Argus"},
        ]
    )
    assert report.devices[0].address == "2"
    assert report.devices[0].kind == "camera"
