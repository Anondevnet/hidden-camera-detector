from __future__ import annotations

import json
from pathlib import Path

from hcd.vision.glint import GlintParams, detect_glints, detect_glints_sequence
from hcd.vision.synthetic import (
    build_fixture_set,
    detect_temporal_demo,
    evaluate_synthetic,
    make_demo_image,
    temporal_sequence,
)


def test_glints_found_and_window_ignored() -> None:
    fixtures = {item.name: item for item in build_fixture_set()}
    item = fixtures["glint_two_dots_plus_window"]
    hits = detect_glints(item.frame)
    assert len(hits) == 2
    for expected_x, expected_y, _radius in item.points:
        assert any(abs(hit.x - expected_x) < 8 and abs(hit.y - expected_y) < 8 for hit in hits)


def test_negative_frames_have_no_glints() -> None:
    for item in build_fixture_set():
        if item.mode != "glint" or item.points:
            continue
        hits = detect_glints(item.frame)
        assert hits == [], item.name


def test_synthetic_metrics_are_perfect_on_this_fixture_set() -> None:
    metrics = evaluate_synthetic()
    glint = metrics["glint"]
    assert glint.true_positives == 3
    assert glint.false_positives == 0
    assert glint.false_negatives == 0
    assert glint.precision == 1.0
    assert glint.recall == 1.0
    # IR is evaluated in test_ir.py; still require the function to return it.
    assert "ir" in metrics


def test_temporal_stability_drops_one_frame_flash() -> None:
    hits = detect_temporal_demo(GlintParams(persist_frames=3))
    assert len(hits) == 1
    assert abs(hits[0].x - 80) < 8
    assert hits[0].frames_seen >= 3
    # Confirm the flash is visible if we do not require persistence.
    frames = temporal_sequence()
    raw = detect_glints(frames[3])
    assert len(raw) == 2
    assert detect_glints_sequence(frames, params=GlintParams(persist_frames=3)) == hits


def test_demo_image_writes_and_annotates(tmp_path: Path) -> None:
    path = tmp_path / "demo.png"
    written, detections = make_demo_image(str(path))
    assert Path(written).is_file()
    assert Path(written).stat().st_size > 1000
    assert len(detections) == 2


def test_metrics_dict_is_jsonable() -> None:
    payload = {key: value.as_dict() for key, value in evaluate_synthetic().items()}
    encoded = json.dumps(payload)
    assert "synthetic-glint" in encoded
