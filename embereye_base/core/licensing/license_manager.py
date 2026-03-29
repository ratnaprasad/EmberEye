from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QFileSystemWatcher, pyqtSignal

from .hardware_id import get_hardware_id
from .models import LicenseFileData, LicensePayload, LicenseState, LicenseSummary
from .paths import get_license_dir, get_license_public_key_path
from .signature_verifier import verify_license_payload_signature


class LicenseSignals(QObject):
    licenses_changed = pyqtSignal(object)


class LicenseManager:
    """Licensing foundation with optional hardware/signature enforcement."""

    def __init__(
        self,
        licensed_analytics: list[str] | None = None,
        allow_all: bool = True,
        license_dir: str | Path | None = None,
        enforce_hardware_id: bool = False,
        enforce_signature: bool = False,
        enforce_expiry: bool = False,
        public_key_path: str | Path | None = None,
        enable_watcher: bool = False,
    ):
        self._allow_all = allow_all
        self._enforce_hardware_id = enforce_hardware_id
        self._enforce_signature = enforce_signature
        self._enforce_expiry = enforce_expiry
        self._licensed_analytics = set(licensed_analytics or [])
        self._max_devices = 0
        self._current_device_count = 0
        self.hardware_id = get_hardware_id()
        self.license_dir = Path(license_dir).expanduser() if license_dir else get_license_dir()
        self.signals = LicenseSignals()
        self._watcher_enabled = bool(enable_watcher)
        self._watcher: QFileSystemWatcher | None = None
        self.public_key_path = (
            Path(public_key_path).expanduser() if public_key_path else get_license_public_key_path(create_parent=True)
        )
        self._state = LicenseState(
            local_hardware_id=self.hardware_id,
            hardware_id_enforced=self._enforce_hardware_id,
            signature_enforced=self._enforce_signature,
            expiry_enforced=self._enforce_expiry,
            analytics=sorted(self._licensed_analytics),
        )
        if self._watcher_enabled:
            self._init_watcher()

    def refresh_from_directory(self) -> LicenseState:
        summaries: list[LicenseSummary] = []
        mismatched_files: list[str] = []
        signature_issues: list[str] = []
        expiry_issues: list[str] = []
        invalid_files: list[str] = []
        merged_analytics: set[str] = set()
        merged_max_devices = 0

        self.license_dir.mkdir(parents=True, exist_ok=True)

        for license_path in sorted(self.license_dir.glob("*.lic")):
            result = self._process_license_file(license_path)
            if result["invalid"]:
                invalid_files.append(result["invalid"])
            if result["mismatch"]:
                mismatched_files.append(result["mismatch"])
            if result["signature_issue"]:
                signature_issues.append(result["signature_issue"])
            if result["expiry_issue"]:
                expiry_issues.append(result["expiry_issue"])
            if result["summary"] is None:
                continue

            summary = result["summary"]
            assert isinstance(summary, LicenseSummary)
            summaries.append(summary)
            merged_analytics.update(result["analytics"])
            merged_max_devices = max(merged_max_devices, int(result["max_devices"]))

        if not self._allow_all:
            self._licensed_analytics = merged_analytics
        self._max_devices = merged_max_devices
        self._state = LicenseState(
            local_hardware_id=self.hardware_id,
            hardware_id_enforced=self._enforce_hardware_id,
            signature_enforced=self._enforce_signature,
            expiry_enforced=self._enforce_expiry,
            max_devices=merged_max_devices,
            analytics=sorted(merged_analytics),
            loaded_files=summaries,
            mismatched_files=mismatched_files,
            signature_issues=signature_issues,
            expiry_issues=expiry_issues,
            invalid_files=invalid_files,
        )
        self._emit_licenses_changed()
        return self._state

    def connect_licenses_changed(self, callback) -> None:
        self.signals.licenses_changed.connect(callback)

    def disconnect_licenses_changed(self, callback) -> None:
        try:
            self.signals.licenses_changed.disconnect(callback)
        except Exception:
            pass

    def stop_watcher(self) -> None:
        if self._watcher is None:
            return
        try:
            self._watcher.directoryChanged.disconnect(self._on_license_directory_changed)
        except Exception:
            pass
        self._watcher = None

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

    def get_hardware_id(self) -> str:
        return self.hardware_id

    def get_license_summary(self) -> list[LicenseSummary]:
        if self._state.loaded_files:
            return list(self._state.loaded_files)
        return [
            LicenseSummary(
                hardware_id=self.hardware_id,
                max_devices=self._max_devices,
                hardware_match=None,
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

        payload = LicensePayload.from_dict(raw)
        return payload.to_file_data(source_path=license_path)

    def _matches_current_hardware(self, license_data: LicenseFileData) -> bool:
        if not license_data.hardware_id:
            return True
        return license_data.hardware_id == self.hardware_id

    def _evaluate_signature(self, license_data: LicenseFileData) -> tuple[bool, str, str | None]:
        if not license_data.signature:
            if self._enforce_signature:
                return False, "unsigned-development", "missing signature"
            return True, "unsigned-development", None

        if not self.public_key_path.exists():
            if self._enforce_signature:
                return False, "signature-unverified-no-public-key", "public key file not found"
            return True, "signature-unverified-no-public-key", "public key file not found"

        payload = LicensePayload(
            customer=license_data.customer,
            hardware_id=license_data.hardware_id,
            max_devices=license_data.max_devices,
            analytics=list(license_data.analytics),
            expiry=license_data.expiry,
            signature=license_data.signature,
        )
        ok, error = verify_license_payload_signature(payload, license_data.signature, self.public_key_path)
        if ok:
            return True, "signature-verified", None

        if self._enforce_signature:
            return False, "signature-invalid", error
        return True, "signature-invalid-bypassed", error

    def _evaluate_expiry(self, license_data: LicenseFileData) -> tuple[bool, str, str | None]:
        if not license_data.expiry:
            return True, "valid-no-expiry", None

        try:
            expiry_date = datetime.fromisoformat(license_data.expiry).date()
        except ValueError:
            if self._enforce_expiry:
                return False, "invalid-expiry", f"invalid expiry date format: {license_data.expiry}"
            return True, "invalid-expiry-bypassed", f"invalid expiry date format: {license_data.expiry}"

        today = datetime.now(UTC).date()
        if expiry_date >= today:
            return True, "expiry-valid", None

        if self._enforce_expiry:
            return False, "expired", f"license expired on {license_data.expiry}"
        return True, "expired-bypassed", f"license expired on {license_data.expiry}"

    def _process_license_file(self, license_path: Path) -> dict[str, object]:
        result: dict[str, object] = {
            "summary": None,
            "analytics": set(),
            "max_devices": 0,
            "mismatch": None,
            "signature_issue": None,
            "expiry_issue": None,
            "invalid": None,
        }

        try:
            license_data = self._load_license_file(license_path)
        except ValueError as exc:
            result["invalid"] = f"{license_path.name}: {exc}"
            return result

        signature_ok, signature_status, signature_error = self._evaluate_signature(license_data)
        if signature_error:
            result["signature_issue"] = f"{license_path.name}: {signature_error}"
        if not signature_ok and self._enforce_signature:
            result["invalid"] = f"{license_path.name}: {signature_error or 'signature invalid'}"
            return result

        expiry_ok, expiry_status, expiry_error = self._evaluate_expiry(license_data)
        if expiry_error:
            result["expiry_issue"] = f"{license_path.name}: {expiry_error}"
        if not expiry_ok and self._enforce_expiry:
            result["invalid"] = f"{license_path.name}: {expiry_error or 'license expired'}"
            return result

        hardware_match = self._matches_current_hardware(license_data)
        status = signature_status
        if expiry_status in {"expired-bypassed", "invalid-expiry-bypassed"}:
            status = f"{status}-{expiry_status}"

        if not hardware_match:
            mismatch_message = (
                f"{license_path.name}: hardware_id mismatch "
                f"(license={license_data.hardware_id}, local={self.hardware_id})"
            )
            result["mismatch"] = mismatch_message
            if self._enforce_hardware_id:
                result["invalid"] = mismatch_message
                return result
            status = f"{status}-hardware-mismatch-bypassed"

        result["summary"] = LicenseSummary(
            customer=license_data.customer,
            hardware_id=license_data.hardware_id,
            hardware_match=hardware_match,
            max_devices=license_data.max_devices,
            analytics=sorted(license_data.analytics),
            expiry=license_data.expiry,
            status=status,
            source_path=license_path,
        )
        result["analytics"] = set(license_data.analytics)
        result["max_devices"] = license_data.max_devices
        return result

    def _init_watcher(self) -> None:
        self.license_dir.mkdir(parents=True, exist_ok=True)
        watcher = QFileSystemWatcher()
        watcher.addPath(str(self.license_dir))
        watcher.directoryChanged.connect(self._on_license_directory_changed)
        self._watcher = watcher

    def _on_license_directory_changed(self, _path: str) -> None:
        try:
            self.refresh_from_directory()
        except Exception:
            return

    def _emit_licenses_changed(self) -> None:
        try:
            self.signals.licenses_changed.emit(self._state)
        except Exception:
            pass
