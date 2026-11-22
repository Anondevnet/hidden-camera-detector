"""Detect small, bright, circular, temporally stable reflections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import cv2
import numpy as np

from hcd.models import GlintDetection

# OpenCV contour arrays are untyped in typical stubs.
Contour = np.ndarray


class _Track(TypedDict):
    det: GlintDetection
    last: int
    seen: int


@dataclass(frozen=True)
class GlintParams:
    min_area: int = 3
    max_area_frac: float = 0.004
    min_circularity: float = 0.62
    min_brightness: float = 200.0
    threshold: int | None = 220
    blur_ksize: int = 3
    persist_frames: int = 3
    match_distance: float = 14.0
    max_aspect: float = 1.6


def _gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _auto_threshold(gray: np.ndarray) -> int:
    """A fixed high cutoff.

    A global percentile is dominated by large bright objects such as windows,
    which then hides the smaller, slightly dimmer lens glints. The area filter
    is what drops the window; the threshold just has to keep compact highlights.
    """
    del gray
    return 220


def _circularity(area: float, perimeter: float) -> float:
    if perimeter <= 0:
        return 0.0
    return float(4.0 * np.pi * area / (perimeter * perimeter))


def detect_glints(
    frame: np.ndarray,
    *,
    params: GlintParams | None = None,
    kind: str = "glint",
    mask: np.ndarray | None = None,
) -> list[GlintDetection]:
    """Return glint candidates in a single BGR or grayscale frame."""
    cfg = params or GlintParams()
    gray = _gray(frame)
    if cfg.blur_ksize and cfg.blur_ksize >= 3:
        k = cfg.blur_ksize | 1
        gray_blur = cv2.GaussianBlur(gray, (k, k), 0)
    else:
        gray_blur = gray

    thresh_val = cfg.threshold if cfg.threshold is not None else _auto_threshold(gray_blur)
    _, binary = cv2.threshold(gray_blur, thresh_val, 255, cv2.THRESH_BINARY)
    if mask is not None:
        binary = cv2.bitwise_and(binary, mask)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape[:2]
    max_area = max(cfg.min_area + 1, int(cfg.max_area_frac * width * height))

    detections: list[GlintDetection] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < cfg.min_area or area > max_area:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        circ = _circularity(area, perimeter)
        if circ < cfg.min_circularity:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        aspect = max(w, h) / max(1, min(w, h))
        if aspect > cfg.max_aspect:
            continue
        if w <= 0 or h <= 0:
            continue
        # Brightness of the contour pixels only. Use a high percentile so a bright
        # core with a dimmer bloom still counts, while ignoring the bounding-box background.
        region = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(region, [contour], -1, 255, -1)
        samples = gray[region == 255]
        if samples.size == 0:
            continue
        brightness = float(np.percentile(samples, 75))
        if brightness < cfg.min_brightness:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        compactness = min(1.0, circ)
        score = float(
            0.45 * compactness
            + 0.35 * min(1.0, (brightness - cfg.min_brightness) / (255 - cfg.min_brightness + 1e-6))
            + 0.20 * (1.0 - min(1.0, aspect - 1.0))
        )
        detections.append(
            GlintDetection(
                x=float(cx),
                y=float(cy),
                radius=float(max(radius, 1.0)),
                circularity=circ,
                brightness=brightness,
                score=score,
                frames_seen=1,
                kind=kind,
                bbox=(int(x), int(y), int(w), int(h)),
            )
        )
    detections.sort(key=lambda item: item.score, reverse=True)
    return detections


def detect_glints_sequence(
    frames: list[np.ndarray],
    *,
    params: GlintParams | None = None,
    kind: str = "glint",
) -> list[GlintDetection]:
    """Keep detections that stay near the same location across enough frames."""
    cfg = params or GlintParams()
    if not frames:
        return []
    if len(frames) == 1 or cfg.persist_frames <= 1:
        return detect_glints(frames[-1], params=cfg, kind=kind)

    tracks: list[_Track] = []
    for index, frame in enumerate(frames):
        hits = detect_glints(frame, params=cfg, kind=kind)
        matched: set[int] = set()
        for hit in hits:
            best_i = _best_track(tracks, hit, cfg.match_distance, matched)
            if best_i is None:
                tracks.append({"det": hit, "last": index, "seen": 1})
                matched.add(len(tracks) - 1)
            else:
                seen = tracks[best_i]["seen"] + 1
                tracks[best_i] = {
                    "det": hit.model_copy(update={"frames_seen": seen}),
                    "last": index,
                    "seen": seen,
                }
                matched.add(best_i)

    last = len(frames) - 1
    stable: list[GlintDetection] = []
    for track in tracks:
        det = track["det"]
        if track["last"] == last and track["seen"] >= cfg.persist_frames:
            stable.append(det)
    stable.sort(key=lambda item: item.score, reverse=True)
    return stable


def _best_track(
    tracks: list[_Track],
    hit: GlintDetection,
    max_distance: float,
    already: set[int],
) -> int | None:
    best_i: int | None = None
    best_d = max_distance
    for index, track in enumerate(tracks):
        if index in already:
            continue
        prev = track["det"]
        dist = float(np.hypot(prev.x - hit.x, prev.y - hit.y))
        if dist <= best_d:
            best_d = dist
            best_i = index
    return best_i
