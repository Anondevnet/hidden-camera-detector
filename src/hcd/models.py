"""Shared report types."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Likelihood(StrEnum):
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    HIGHLY_LIKELY = "highly_likely"


class Reason(BaseModel):
    code: str
    detail: str
    weight: int


class DeviceFinding(BaseModel):
    """A host observed on the local network, scored for camera likelihood."""

    ip: str | None = None
    mac: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_role: str | None = None
    hostname: str | None = None
    open_ports: list[int] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    http_fingerprints: list[str] = Field(default_factory=list)
    randomized_mac: bool = False
    score: int = 0
    likelihood: Likelihood = Likelihood.UNLIKELY
    reasons: list[Reason] = Field(default_factory=list)


class BleFinding(BaseModel):
    address: str
    name: str | None = None
    rssi: int | None = None
    manufacturer_id: int | None = None
    manufacturer_label: str | None = None
    kind: str = "unknown"
    score: int = 0
    likelihood: Likelihood = Likelihood.UNLIKELY
    reasons: list[Reason] = Field(default_factory=list)


class GlintDetection(BaseModel):
    x: float
    y: float
    radius: float
    circularity: float
    brightness: float
    score: float
    frames_seen: int = 1
    kind: str = "glint"
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)


class NetworkScanReport(BaseModel):
    cidr: str | None = None
    devices: list[DeviceFinding] = Field(default_factory=list)


class BleScanReport(BaseModel):
    devices: list[BleFinding] = Field(default_factory=list)


class VisionReport(BaseModel):
    mode: str
    width: int
    height: int
    frames: int = 1
    detections: list[GlintDetection] = Field(default_factory=list)
