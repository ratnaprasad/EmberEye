from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FrameData:
    """Shared frame payload passed into analytics."""

    frame_id: str
    source_id: str
    timestamp: float
    image: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SensorReading:
    """Normalized sensor reading for fused analytics pipelines."""

    sensor_type: str
    source_id: str
    timestamp: float
    value: Any
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalyticResult:
    """Runtime output emitted by an analytic."""

    analytic_id: str
    success: bool
    payload: dict[str, Any] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalyticMetadata:
    """Descriptor metadata loaded from an analytics package."""

    analytic_id: str
    name: str
    version: str
    module_name: str
    entry_class: str = "Analytic"
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    execution_hints: dict[str, Any] = field(default_factory=dict)
    required_license: str | None = None
    assets_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
