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
class LicensePayload:
    customer: str
    hardware_id: str = ""
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    expiry: str | None = None
    signature: str | None = None

    def signing_payload_dict(self) -> dict[str, str | int | list[str] | None]:
        return {
            "customer": self.customer,
            "hardware_id": self.hardware_id,
            "max_devices": self.max_devices,
            "analytics": list(self.analytics),
            "expiry": self.expiry,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "LicensePayload":
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

        return cls(
            customer=customer,
            hardware_id=str(raw.get("hardware_id") or ""),
            max_devices=max_devices,
            analytics=[str(item).strip() for item in analytics if str(item).strip()],
            expiry=(str(raw["expiry"]) if raw.get("expiry") else None),
            signature=(str(raw["signature"]) if raw.get("signature") else None),
        )

    def to_file_data(self, source_path: Path | None = None, status: str | None = None) -> LicenseFileData:
        return LicenseFileData(
            customer=self.customer,
            hardware_id=self.hardware_id,
            max_devices=self.max_devices,
            analytics=list(self.analytics),
            expiry=self.expiry,
            signature=self.signature,
            source_path=source_path,
            status=status or ("unsigned-development" if not self.signature else "signature-unverified"),
        )


@dataclass(slots=True)
class LicenseSummary:
    customer: str = "Development"
    hardware_id: str = ""
    hardware_match: bool | None = None
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    expiry: str | None = None
    status: str = "development"
    source_path: Path | None = None


@dataclass(slots=True)
class LicenseState:
    local_hardware_id: str = ""
    hardware_id_enforced: bool = False
    signature_enforced: bool = False
    expiry_enforced: bool = False
    max_devices: int = 0
    analytics: list[str] = field(default_factory=list)
    loaded_files: list[LicenseSummary] = field(default_factory=list)
    mismatched_files: list[str] = field(default_factory=list)
    signature_issues: list[str] = field(default_factory=list)
    expiry_issues: list[str] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
