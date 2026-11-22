"""Load images or short videos and run glint / IR detection."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from hcd.models import GlintDetection, VisionReport
from hcd.vision.glint import GlintParams, detect_glints, detect_glints_sequence
from hcd.vision.ir import detect_ir_dots, detect_ir_dots_sequence


def decode_image(data: bytes) -> np.ndarray:
    array = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("could not decode image bytes")
    return frame


def load_image(path: str | Path) -> np.ndarray:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"could not read image: {path}")
    return frame


def iter_video_frames(
    source: str | int,
    *,
    max_frames: int = 90,
    step: int = 1,
) -> list[np.ndarray]:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise ValueError(f"could not open video source: {source}")
    frames: list[np.ndarray] = []
    index = 0
    try:
        while len(frames) < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                frames.append(frame)
            index += 1
    finally:
        cap.release()
    if not frames:
        raise ValueError(f"no frames decoded from {source}")
    return frames


def analyze_image(frame: np.ndarray, mode: str = "glint", params: GlintParams | None = None) -> VisionReport:
    detections = detect_ir_dots(frame, params=params) if mode == "ir" else detect_glints(frame, params=params)
    height, width = frame.shape[:2]
    return VisionReport(mode=mode, width=width, height=height, frames=1, detections=detections)


def analyze_frames(
    frames: list[np.ndarray],
    mode: str = "glint",
    params: GlintParams | None = None,
) -> VisionReport:
    if not frames:
        raise ValueError("no frames")
    if mode == "ir":
        detections = detect_ir_dots_sequence(frames, params=params)
    else:
        detections = detect_glints_sequence(frames, params=params)
    height, width = frames[-1].shape[:2]
    return VisionReport(mode=mode, width=width, height=height, frames=len(frames), detections=detections)


def detections_to_dicts(detections: list[GlintDetection]) -> list[dict[str, object]]:
    return [item.model_dump() for item in detections]
