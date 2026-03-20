from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from typing import Optional, Dict, Any


class DetectionSource(Enum):
    SMOKE = auto()
    FLAME_ANALOG = auto()
    FLAME_DIGITAL = auto()
    THERMAL = auto()
    VISION = auto()
    GAS = auto()


class SeverityLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Detection:
    source: DetectionSource
    confidence: float
    value: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusionResult:
    alarm: bool
    severity: SeverityLevel
    confidence: float
    primary_source: Optional[DetectionSource]
    detections: list[Detection]
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
