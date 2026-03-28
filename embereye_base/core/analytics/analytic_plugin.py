from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import AnalyticMetadata, AnalyticResult, FrameData


class AnalyticPlugin(ABC):
    """Base contract for Phase 2 analytics packages."""

    @abstractmethod
    def get_metadata(self) -> AnalyticMetadata:
        """Return static analytic metadata for registration and display."""

    @abstractmethod
    def configure(self, config: dict[str, Any]) -> None:
        """Apply runtime configuration before analytic execution starts."""

    @abstractmethod
    def process_frame(self, frame: FrameData, context: dict[str, Any] | None = None) -> AnalyticResult:
        """Process a single frame and return a normalized result."""
