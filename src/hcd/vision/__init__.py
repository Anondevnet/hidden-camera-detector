"""Lens-glint and IR-dot detection on images and video."""

from hcd.vision.annotate import annotate_frame
from hcd.vision.glint import GlintParams, detect_glints, detect_glints_sequence
from hcd.vision.ir import detect_ir_dots

__all__ = [
    "GlintParams",
    "annotate_frame",
    "detect_glints",
    "detect_glints_sequence",
    "detect_ir_dots",
]
