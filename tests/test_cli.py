from __future__ import annotations

import json
from pathlib import Path

import cv2

from hcd.cli import main
from hcd.vision.synthetic import build_fixture_set


def test_vendors_and_mac_lookup(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["vendors", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["vendors"]
    assert main(["vendors", "--mac", "EC:71:DB:00:00:01"]) == 0
    assert "Reolink" in capsys.readouterr().out


def test_demo_and_glint_file(tmp_path: Path, capsys) -> None:
    image = tmp_path / "demo.png"
    report = tmp_path / "metrics.json"
    assert main(["demo", "--out", str(image), "--report", str(report)]) == 0
    capsys.readouterr()
    assert image.is_file()
    metrics = json.loads(report.read_text())
    assert metrics["glint"]["precision"] == 1.0
    raw = tmp_path / "raw.png"
    fixture = next(item for item in build_fixture_set() if item.name == "glint_two_dots_plus_window")
    assert cv2.imwrite(str(raw), fixture.frame)
    out = tmp_path / "annotated.png"
    assert main(["glint", "--file", str(raw), "--out", str(out), "--json"]) == 0
    assert out.is_file()
    vision = json.loads(capsys.readouterr().out)
    assert len(vision["detections"]) == 2


def test_ble_from_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "adv.json"
    path.write_text(json.dumps([{"address": "aa", "name": "Eufy Cam 2"}]), encoding="utf-8")
    assert main(["ble", "--from-json", str(path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["devices"][0]["kind"] == "camera"


def test_help_mentions_consent() -> None:
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "authorized" in buf.getvalue().lower() or "staying" in buf.getvalue().lower()
