from __future__ import annotations

import json
from pathlib import Path

from .models import LicenseFileData, LicenseState, LicenseSummary
from .paths import get_license_dir


class LicenseManager:
    """Development-safe licensing foundation.

    The manager establishes shared models, path conventions, and merge behavior
    for `.lic` files. Signature verification is intentionally deferred until
    the full Phase 1 RSA implementation is added.
    """

    def __init__(
        self,
        licensed_analytics: list[str] | None = None,
        allow_all: bool = True,
        license_dir: str | Path | None = None,
    ):
        self._allow_all = allow_all
        self._licensed_analytics = set(licensed_analytics or [])
        self._max_devices = 0
        self._current_device_count = 0
        self.license_dir = Path(license_dir).expanduser() if license_dir else get_license_dir()
        self._state = LicenseState(
            analytics=sorted(self._licensed_analytics),
        )

    def refresh_from_directory(self) -> LicenseState:
        summaries: list[LicenseSummary] = []
        invalid_files: list[str] = []
        merged_analytics: set[str] = set()
        merged_max_devices = 0

        self.license_dir.mkdir(parents=True, exist_ok=True)

        for license_path in sorted(self.license_dir.glob("*.lic")):
            try:
                license_data = self._load_license_file(license_path)
            except ValueError as exc:
                invalid_files.append(f"{license_path.name}: {exc}")
                continue

            merged_analytics.update(license_data.analytics)
            merged_max_devices = max(merged_max_devices, license_data.max_devices)
            summaries.append(
                LicenseSummary(
                    customer=license_data.customer,
                    max_devices=license_data.max_devices,
                    analytics=sorted(license_data.analytics),
                    expiry=license_data.expiry,
                    status=license_data.status,
                    source_path=license_path,
                )
            )

        if not self._allow_all:
            self._licensed_analytics = merged_analytics
        self._max_devices = merged_max_devices
        self._state = LicenseState(
            max_devices=merged_max_devices,
            analytics=sorted(merged_analytics),
            loaded_files=summaries,
            invalid_files=invalid_files,
        )
        return self._state

    def get_license_dir(self) -> Path:
        return self.license_dir

    def is_analytic_licensed(self, analytic_id: str) -> bool:
        if self._allow_all:
            return True
        return analytic_id in self._licensed_analytics

    def get_max_devices(self) -> int:
        return self._max_devices

    def get_current_device_count(self) -> int:
        return self._current_device_count

    def get_license_summary(self) -> list[LicenseSummary]:
        if self._state.loaded_files:
            return list(self._state.loaded_files)
        return [
            LicenseSummary(
                max_devices=self._max_devices,
                analytics=sorted(self._licensed_analytics),
            )
        ]

    def get_invalid_license_files(self) -> list[str]:
        return list(self._state.invalid_files)

    def set_licensed_analytics(self, analytic_ids: list[str], allow_all: bool | None = None) -> None:
        self._licensed_analytics = set(analytic_ids)
        if allow_all is not None:
            self._allow_all = allow_all
        self._state.analytics = sorted(self._licensed_analytics)

    def set_device_counts(self, current_device_count: int, max_devices: int) -> None:
        self._current_device_count = current_device_count
        self._max_devices = max_devices

    def _load_license_file(self, license_path: Path) -> LicenseFileData:
        try:
            raw = json.loads(license_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid license file: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError("license root must be a JSON object")

        customer = str(raw.get("customer") or "").strip()
        if not customer:
            raise ValueError("missing required field: customer")

        max_devices = raw.get("max_devices", 0)
        if not isinstance(max_devices, int):
            raise ValueError("field 'max_devices' must be an integer")

        analytics = raw.get("analytics", [])
        if not isinstance(analytics, list):
            raise ValueError("field 'analytics' must be a list")

        return LicenseFileData(
            customer=customer,
            hardware_id=str(raw.get("hardware_id") or ""),
            max_devices=max_devices,
            analytics=[str(item).strip() for item in analytics if str(item).strip()],
            expiry=(str(raw["expiry"]) if raw.get("expiry") else None),
            signature=(str(raw["signature"]) if raw.get("signature") else None),
            source_path=license_path,
            status=("unsigned-development" if not raw.get("signature") else "signature-unverified"),
        )
