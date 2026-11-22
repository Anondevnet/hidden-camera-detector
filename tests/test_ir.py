from __future__ import annotations

from hcd.vision.ir import detect_ir_dots
from hcd.vision.synthetic import build_fixture_set, evaluate_synthetic


def test_ir_dots_detected() -> None:
    fixtures = {item.name: item for item in build_fixture_set()}
    hits = detect_ir_dots(fixtures["ir_single"].frame)
    assert len(hits) >= 1
    assert all(hit.kind == "ir_dot" for hit in hits)
    x, y, _r = fixtures["ir_single"].points[0]
    assert any(abs(hit.x - x) < 8 and abs(hit.y - y) < 8 for hit in hits)


def test_ir_ignores_white_window() -> None:
    fixtures = {item.name: item for item in build_fixture_set()}
    hits = detect_ir_dots(fixtures["ir_ignores_white_window"].frame)
    assert hits == []


def test_ir_synthetic_metrics() -> None:
    metrics = evaluate_synthetic()["ir"]
    assert metrics.false_positives == 0
    assert metrics.recall == 1.0
    assert metrics.precision == 1.0
    assert metrics.true_positives >= 3
