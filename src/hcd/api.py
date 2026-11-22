"""FastAPI app: JSON detection API plus the phone-friendly web UI."""

from __future__ import annotations

import tempfile
from importlib import resources
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from hcd import __version__
from hcd.vision.annotate import annotate_frame
from hcd.vision.io import analyze_frames, analyze_image, decode_image, iter_video_frames

WEB_DIR = Path(str(resources.files("hcd.web")))

app = FastAPI(
    title="Hidden Camera Detector",
    version=__version__,
    description="Lens-glint / IR detection for authorized spaces, plus a phone-friendly camera page.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    page = WEB_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(500, "web UI is missing from the package")
    return FileResponse(page, media_type="text/html")


@app.get("/health")
@app.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


def _mode(value: str | None) -> str:
    mode = (value or "glint").strip().lower()
    if mode not in {"glint", "ir"}:
        raise HTTPException(400, "mode must be 'glint' or 'ir'")
    return mode


@app.post("/v1/detect/image")
async def detect_image(
    file: UploadFile = File(...),
    mode: str = Form("glint"),
    annotate: bool = Form(False),
) -> Response:
    chosen = _mode(mode)
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    try:
        frame = decode_image(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    report = analyze_image(frame, mode=chosen)
    if annotate:
        annotated = annotate_frame(frame, report.detections)
        ok, encoded = cv2.imencode(".png", annotated)
        if not ok:
            raise HTTPException(500, "failed to encode annotated image")
        return Response(content=encoded.tobytes(), media_type="image/png")
    return JSONResponse(report.model_dump())


@app.post("/v1/detect/video")
async def detect_video(
    file: UploadFile = File(...),
    mode: str = Form("glint"),
    max_frames: int = Form(60),
    annotate: bool = Form(False),
) -> Response:
    chosen = _mode(mode)
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    suffix = Path(file.filename or "clip.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(data)
        handle.flush()
        try:
            frames = iter_video_frames(handle.name, max_frames=max(1, min(max_frames, 180)))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    report = analyze_frames(frames, mode=chosen)
    if annotate:
        annotated = annotate_frame(frames[-1], report.detections)
        ok, encoded = cv2.imencode(".png", annotated)
        if not ok:
            raise HTTPException(500, "failed to encode annotated image")
        return Response(content=encoded.tobytes(), media_type="image/png")
    return JSONResponse(report.model_dump())
