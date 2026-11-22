"""Labelled synthetic frames for tests and the README demo image.

These drawings are *not* photographs of hidden cameras. Metrics computed
against this set only measure whether the blob detector finds the dots we
drew, and must not be cited as real-world accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from hcd.models import GlintDetection
from hcd.vision.annotate import annotate_frame
from hcd.vision.glint import GlintParams, detect_glints, detect_glints_sequence
from hcd.vision.ir import detect_ir_dots


@dataclass(frozen=True)
class LabeledFrame:
    name: str
    frame: np.ndarray
    mode: str
    points: list[tuple[float, float, float]]  # cx, cy, radius
    expect_detect: bool


@dataclass(frozen=True)
class Metrics:
    """Counts from a labelled synthetic set."""

    label: str
    frames: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "label": self.label,
            "frames": self.frames,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
        }


def _background(width: int, height: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, _xx = np.mgrid[0:height, 0:width]
    base = 28 + (yy / max(1, height - 1)) * 22
    noise = rng.normal(0, 6, size=(height, width))
    gray = np.clip(base + noise, 0, 255).astype(np.uint8)
    frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    # A dim "wall fixture" so the scene is not empty.
    cv2.rectangle(frame, (20, height - 70), (110, height - 20), (50, 52, 48), -1)
    return frame


def add_glint(
    frame: np.ndarray,
    cx: int,
    cy: int,
    radius: int = 4,
    color: tuple[int, int, int] = (255, 255, 245),
) -> np.ndarray:
    out = frame.copy()
    # Soft bloom plus a hard core, similar to a lens reflection under a flashlight.
    overlay = out.copy()
    cv2.circle(overlay, (cx, cy), radius + 3, tuple(int(c * 0.55) for c in color), -1, lineType=cv2.LINE_AA)
    cv2.circle(overlay, (cx, cy), radius, color, -1, lineType=cv2.LINE_AA)
    cv2.circle(overlay, (cx, cy), max(1, radius // 2), (255, 255, 255), -1, lineType=cv2.LINE_AA)
    out = cv2.addWeighted(overlay, 0.85, out, 0.15, 0)
    return out


def add_ir_dot(frame: np.ndarray, cx: int, cy: int, radius: int = 3) -> np.ndarray:
    # Phone sensors often render IR LEDs as magenta / violet-white.
    # Draw in BGR with a magenta body (no white core, which would fail a tint check).
    out = frame.copy()
    color = (255, 80, 255)
    cv2.circle(out, (cx, cy), radius + 2, (180, 40, 180), -1, lineType=cv2.LINE_AA)
    cv2.circle(out, (cx, cy), radius, color, -1, lineType=cv2.LINE_AA)
    return out


def add_window(frame: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    out = frame.copy()
    cv2.rectangle(out, (x, y), (x + w, y + h), (245, 245, 240), -1)
    cv2.rectangle(out, (x, y), (x + w, y + h), (200, 200, 190), 2)
    return out


def add_streak(frame: np.ndarray, x: int, y: int, length: int = 80) -> np.ndarray:
    out = frame.copy()
    cv2.line(out, (x, y), (x + length, y + 6), (255, 255, 255), 3, lineType=cv2.LINE_AA)
    return out


def build_fixture_set(width: int = 640, height: int = 480) -> list[LabeledFrame]:
    frames: list[LabeledFrame] = []

    # Positive glints in a dark room, including one next to a large window
    # that must *not* itself be reported as a glint.
    g1 = _background(width, height, seed=1)
    g1 = add_window(g1, 380, 40, 200, 140)
    g1 = add_glint(g1, 160, 210, radius=4)
    g1 = add_glint(g1, 260, 300, radius=5)
    frames.append(
        LabeledFrame(
            "glint_two_dots_plus_window",
            g1,
            "glint",
            [(160, 210, 4), (260, 300, 5)],
            True,
        )
    )

    g2 = add_glint(_background(width, height, seed=2), 400, 180, radius=3)
    frames.append(LabeledFrame("glint_single", g2, "glint", [(400, 180, 3)], True))

    # Negatives: empty room, large window only, long specular streak, huge bright disc.
    frames.append(LabeledFrame("glint_empty", _background(width, height, seed=3), "glint", [], False))
    frames.append(
        LabeledFrame(
            "glint_window_only",
            add_window(_background(width, height, seed=4), 80, 60, 280, 180),
            "glint",
            [],
            False,
        )
    )
    frames.append(
        LabeledFrame(
            "glint_streak",
            add_streak(_background(width, height, seed=5), 120, 200, 120),
            "glint",
            [],
            False,
        )
    )
    huge = _background(width, height, seed=6)
    cv2.circle(huge, (320, 240), 70, (255, 255, 255), -1)
    frames.append(LabeledFrame("glint_huge_disc", huge, "glint", [], False))

    # IR positives and a white-glint negative for the IR path.
    ir1 = add_ir_dot(_background(width, height, seed=7), 200, 190, radius=3)
    ir1 = add_ir_dot(ir1, 230, 205, radius=3)
    frames.append(LabeledFrame("ir_pair", ir1, "ir", [(200, 190, 3), (230, 205, 3)], True))
    frames.append(
        LabeledFrame(
            "ir_single",
            add_ir_dot(_background(width, height, seed=8), 420, 260, radius=4),
            "ir",
            [(420, 260, 4)],
            True,
        )
    )
    frames.append(
        LabeledFrame(
            "ir_ignores_white_window",
            add_window(_background(width, height, seed=9), 80, 60, 280, 180),
            "ir",
            [],
            False,
        )
    )
    return frames


def _match(
    predicted: list[GlintDetection],
    points: list[tuple[float, float, float]],
    tol: float,
) -> tuple[int, int, int]:
    used = set()
    tp = 0
    for det in predicted:
        for index, (x, y, radius) in enumerate(points):
            if index in used:
                continue
            if float(np.hypot(det.x - x, det.y - y)) <= max(tol, radius + 6):
                used.add(index)
                tp += 1
                break
    fn = len(points) - tp
    fp = len(predicted) - tp
    return tp, fp, fn


def evaluate_synthetic(
    fixtures: list[LabeledFrame] | None = None,
    *,
    params: GlintParams | None = None,
    distance_tol: float = 10.0,
) -> dict[str, Metrics]:
    fixtures = fixtures or build_fixture_set()
    groups = {"glint": [f for f in fixtures if f.mode == "glint"], "ir": [f for f in fixtures if f.mode == "ir"]}
    out: dict[str, Metrics] = {}
    for mode, items in groups.items():
        tp = fp = fn = 0
        for item in items:
            if mode == "ir":
                predicted = detect_ir_dots(item.frame, params=params)
            else:
                predicted = detect_glints(item.frame, params=params)
            t, f_p, f_n = _match(predicted, item.points, distance_tol)
            tp += t
            fp += f_p
            fn += f_n
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        out[mode] = Metrics(
            label=f"synthetic-{mode}",
            frames=len(items),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            precision=precision,
            recall=recall,
        )
    return out


def make_demo_image(path: str, *, width: int = 640, height: int = 480) -> tuple[str, list[GlintDetection]]:
    fixtures = {item.name: item for item in build_fixture_set(width, height)}
    item = fixtures["glint_two_dots_plus_window"]
    detections = detect_glints(item.frame)
    annotated = annotate_frame(item.frame, detections)
    caption = "Synthetic demo (not a real room): two drawn glints, one large window that should be ignored"
    cv2.putText(
        annotated,
        caption,
        (12, height - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    cv2.imwrite(path, annotated, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    return path, detections


def temporal_sequence(width: int = 320, height: int = 240, length: int = 8) -> list[np.ndarray]:
    """A glint that persists, plus a one-frame flash that should be dropped."""
    frames: list[np.ndarray] = []
    for i in range(length):
        frame = _background(width, height, seed=20 + i)
        frame = add_glint(frame, 80, 90, radius=4)
        if i == 3:
            frame = add_glint(frame, 200, 160, radius=4)
        frames.append(frame)
    return frames


def detect_temporal_demo(params: GlintParams | None = None) -> list[GlintDetection]:
    cfg = params or GlintParams(persist_frames=3)
    return detect_glints_sequence(temporal_sequence(), params=cfg)
