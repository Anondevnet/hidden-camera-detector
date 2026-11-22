"""IR-LED spotting: small magenta / bright dots, often visible to phone cameras."""

from __future__ import annotations

import cv2
import numpy as np

from hcd.models import GlintDetection
from hcd.vision.glint import GlintParams, detect_glints, detect_glints_sequence


def _magenta_mask(frame: np.ndarray) -> np.ndarray:
    """Pixels that look purple / pink (high red and blue, lower green) or very hot."""
    if frame.ndim != 3:
        gray = frame
        _, mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
        return mask
    bgr = frame.astype(np.int16)
    blue, green, red = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
    magenta = (red > 140) & (blue > 140) & ((red + blue) > (2 * green + 30))
    # Near-white cores are how some phone sensors render IR LEDs.
    hot = (red > 200) & (blue > 200) & (green > 200)
    mask = np.where(magenta | hot, 255, 0).astype(np.uint8)
    # A 2x2 close fills pinholes without erasing a thin ring the way a 3x3 open would.
    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)


def detect_ir_dots(
    frame: np.ndarray,
    *,
    params: GlintParams | None = None,
) -> list[GlintDetection]:
    """Detect IR-style dots in a single frame.

    Night-vision LEDs often show up on phone sensors as compact purple / white
    lights. This path uses a magenta-or-hot mask, then the same small-circle
    filters as lens-glint detection, with slightly looser circularity because
    a cluster of IR LEDs may not be a perfect disc.
    """
    cfg = params or GlintParams(min_circularity=0.50, min_brightness=110.0, threshold=1)
    mask = _magenta_mask(frame)
    # Non-mask pixels become black so brightness is computed on the dots only.
    isolated = cv2.bitwise_and(frame, frame, mask=mask)
    # Use a very low threshold on the isolated image; the mask already picked candidates.
    cfg = GlintParams(
        min_area=cfg.min_area,
        max_area_frac=cfg.max_area_frac,
        min_circularity=cfg.min_circularity,
        min_brightness=cfg.min_brightness,
        threshold=10,
        blur_ksize=cfg.blur_ksize,
        persist_frames=cfg.persist_frames,
        match_distance=cfg.match_distance,
        max_aspect=cfg.max_aspect,
    )
    hits = detect_glints(isolated, params=cfg, kind="ir_dot", mask=mask)
    return hits


def detect_ir_dots_sequence(
    frames: list[np.ndarray],
    *,
    params: GlintParams | None = None,
) -> list[GlintDetection]:
    cfg = params or GlintParams(min_circularity=0.50, min_brightness=110.0, persist_frames=3)
    # Run per-frame IR detection and reuse the glint tracker by wrapping detect_glints
    # would skip the magenta mask, so track manually via detect_glints_sequence on isolated frames.
    isolated: list[np.ndarray] = []
    for frame in frames:
        mask = _magenta_mask(frame)
        isolated.append(cv2.bitwise_and(frame, frame, mask=mask))
    ir_params = GlintParams(
        min_area=cfg.min_area,
        max_area_frac=cfg.max_area_frac,
        min_circularity=cfg.min_circularity,
        min_brightness=cfg.min_brightness,
        threshold=10,
        blur_ksize=cfg.blur_ksize,
        persist_frames=cfg.persist_frames,
        match_distance=cfg.match_distance,
        max_aspect=cfg.max_aspect,
    )
    hits = detect_glints_sequence(isolated, params=ir_params, kind="ir_dot")
    return hits
