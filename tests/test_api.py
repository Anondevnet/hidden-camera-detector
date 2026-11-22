from __future__ import annotations

import cv2
from fastapi.testclient import TestClient

from hcd.api import app
from hcd.vision.synthetic import build_fixture_set

client = TestClient(app)


def test_health_and_index() -> None:
    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "getUserMedia" in page.text or "Start camera" in page.text
    css = client.get("/static/styles.css")
    assert css.status_code == 200


def _png_bytes(frame) -> bytes:  # type: ignore[no-untyped-def]
    ok, encoded = cv2.imencode(".png", frame)
    assert ok
    return encoded.tobytes()


def test_detect_image_json_and_annotated() -> None:
    frame = {item.name: item for item in build_fixture_set()}["glint_two_dots_plus_window"].frame
    files = {"file": ("frame.png", _png_bytes(frame), "image/png")}
    response = client.post("/v1/detect/image", files=files, data={"mode": "glint"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "glint"
    assert len(payload["detections"]) == 2
    annotated = client.post(
        "/v1/detect/image",
        files={"file": ("frame.png", _png_bytes(frame), "image/png")},
        data={"mode": "glint", "annotate": "true"},
    )
    assert annotated.status_code == 200
    assert annotated.headers["content-type"] == "image/png"
    assert len(annotated.content) > 1000


def test_rejects_bad_mode_and_empty() -> None:
    frame = build_fixture_set()[0].frame
    bad = client.post(
        "/v1/detect/image",
        files={"file": ("frame.png", _png_bytes(frame), "image/png")},
        data={"mode": "magic"},
    )
    assert bad.status_code == 400
    empty = client.post(
        "/v1/detect/image",
        files={"file": ("frame.png", b"", "image/png")},
        data={"mode": "glint"},
    )
    assert empty.status_code == 400
