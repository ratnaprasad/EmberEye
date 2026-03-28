from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class LicenseFileData:
    customer: str
    hardware_id: str = ""
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    expiry: str | None = None
    signature: str | None = None
    source_path: Path | None = None
    status: str = "loaded"


@dataclass(slots=True)
class LicenseSummary:
    customer: str = "Development"
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    expiry: str | None = None
    status: str = "development"
    source_path: Path | None = None


@dataclass(slots=True)
class LicenseState:
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    loaded_files: list[LicenseSummary] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
