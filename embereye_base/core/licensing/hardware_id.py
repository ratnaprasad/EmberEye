from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import uuid
from pathlib import Path


def _read_first_line(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value if value and value.lower() != "none" else ""
    except OSError:
        return ""


def _safe_run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    output = (result.stdout or "").strip()
    return output


def _get_linux_machine_identifier() -> str:
    for candidate in (
        Path("/sys/class/dmi/id/product_uuid"),
        Path("/sys/class/dmi/id/board_serial"),
        Path("/etc/machine-id"),
    ):
        value = _read_first_line(candidate)
        if value:
            return value
    return ""


def _get_macos_machine_identifier() -> str:
    output = _safe_run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
    for line in output.splitlines():
        if "IOPlatformUUID" in line and '"' in line:
            return line.split('"')[-2].strip()
    return ""


def _get_windows_machine_identifier() -> str:
    output = _safe_run(["wmic", "csproduct", "get", "uuid"])
    lines = [line.strip() for line in output.splitlines() if line.strip() and line.strip().lower() != "uuid"]
    if lines:
        return lines[0]
    return ""


def _get_platform_machine_identifier() -> str:
    resolvers = {
        "linux": _get_linux_machine_identifier,
        "darwin": _get_macos_machine_identifier,
        "windows": _get_windows_machine_identifier,
    }
    resolver = resolvers.get(platform.system().lower())
    if resolver is None:
        return ""
    return resolver()


def get_hardware_id_components() -> dict[str, str]:
    machine_identifier = _get_platform_machine_identifier()
    mac_address = f"{uuid.getnode():012x}"
    hostname = platform.node().strip()
    system = platform.system().strip()

    return {
        "system": system,
        "hostname": hostname,
        "machine_identifier": machine_identifier,
        "mac_address": mac_address,
    }


def get_hardware_id() -> str:
    override = os.environ.get("EMBEREYE_HARDWARE_ID", "").strip()
    if override:
        return override

    components = get_hardware_id_components()
    seed = "|".join(
        [
            components.get("system", ""),
            components.get("hostname", ""),
            components.get("machine_identifier", ""),
            components.get("mac_address", ""),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()
