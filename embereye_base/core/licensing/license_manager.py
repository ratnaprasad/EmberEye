from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LicenseSummary:
    customer: str = "Development"
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    expiry: str | None = None
    status: str = "development"


class LicenseManager:
    """Temporary Phase 2 license service.

    This is a development-time interface that keeps the Phase 2 plugin and UI
    work unblocked until the full Phase 1 licensing implementation is added.
    """

    def __init__(self, licensed_analytics: list[str] | None = None, allow_all: bool = True):
        self._allow_all = allow_all
        self._licensed_analytics = set(licensed_analytics or [])
        self._max_devices = 0
        self._current_device_count = 0

    def is_analytic_licensed(self, analytic_id: str) -> bool:
        if self._allow_all:
            return True
        return analytic_id in self._licensed_analytics

    def get_max_devices(self) -> int:
        return self._max_devices

    def get_current_device_count(self) -> int:
        return self._current_device_count

    def get_license_summary(self) -> list[LicenseSummary]:
        return [
            LicenseSummary(
                max_devices=self._max_devices,
                analytics=sorted(self._licensed_analytics),
            )
        ]

    def set_licensed_analytics(self, analytic_ids: list[str], allow_all: bool | None = None) -> None:
        self._licensed_analytics = set(analytic_ids)
        if allow_all is not None:
            self._allow_all = allow_all

    def set_device_counts(self, current_device_count: int, max_devices: int) -> None:
        self._current_device_count = current_device_count
        self._max_devices = max_devices
