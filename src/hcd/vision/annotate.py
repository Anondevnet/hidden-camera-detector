"""Draw detection overlays on a frame."""

from __future__ import annotations

import cv2
import numpy as np

from hcd.models import GlintDetection

_COLORS = {
    "glint": (40, 170, 255),  # amber in BGR
    "ir_dot": (220, 80, 220),  # magenta
}


def annotate_frame(
    frame: np.ndarray,
    detections: list[GlintDetection],
    *,
    label: bool = True,
) -> np.ndarray:
    canvas = frame if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    canvas = canvas.copy()
    for det in detections:
        color = _COLORS.get(det.kind, (0, 220, 255))
        center = (round(det.x), round(det.y))
        radius = max(6, round(det.radius + 3))
        cv2.circle(canvas, center, radius, color, 2, lineType=cv2.LINE_AA)
        if label:
            text = f"{det.kind} {det.score:.2f}"
            if det.frames_seen > 1:
                text += f" x{det.frames_seen}"
            org = (center[0] + radius + 2, max(14, center[1] - radius))
            cv2.putText(
                canvas,
                text,
                org,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
    return canvas
