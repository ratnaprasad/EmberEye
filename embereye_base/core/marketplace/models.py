from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from embereye_base.core.analytics import AnalyticMetadata


@dataclass(slots=True)
class PackageValidationResult:
    package_path: Path
    is_valid: bool
    metadata: AnalyticMetadata | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalyticDescriptor:
    analytic_id: str
    package_path: Path
    metadata: AnalyticMetadata
    load_status: str = "available"
    license_status: str = "unknown"
    error_message: str | None = None
