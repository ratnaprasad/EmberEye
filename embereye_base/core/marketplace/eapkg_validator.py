from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from embereye_base.core.analytics import AnalyticMetadata

from .models import PackageValidationResult


_SAFE_ID_RE = re.compile(r"[^a-z0-9_]+")


def _normalize_analytic_id(name: str) -> str:
    normalized = _SAFE_ID_RE.sub("_", str(name).strip().lower()).strip("_")
    return normalized or "analytic"


def validate_eapkg(package_path: str | Path) -> PackageValidationResult:
    package = Path(package_path)
    result = PackageValidationResult(package_path=package, is_valid=False)

    if not package.exists():
        result.errors.append("Package file does not exist.")
        return result
    if package.suffix.lower() != ".eapkg":
        result.errors.append("Package must use the .eapkg extension.")
        return result

    try:
        with ZipFile(package) as archive:
            names = set(archive.namelist())
            if "metadata.json" not in names:
                result.errors.append("metadata.json is missing from the package root.")
                return result

            try:
                metadata_raw = json.loads(archive.read("metadata.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                result.errors.append(f"metadata.json is invalid: {exc}")
                return result

            try:
                metadata = _build_metadata(metadata_raw)
            except ValueError as exc:
                result.errors.append(str(exc))
                return result

            result.metadata = metadata
            module_name = metadata.module_name.strip("/")
            module_init = f"{module_name}/__init__.py"
            module_impl = f"{module_name}/analytic.py"

            if module_init not in names:
                result.errors.append(f"Missing module entrypoint file: {module_init}")
            if module_impl not in names:
                result.errors.append(f"Missing analytic implementation file: {module_impl}")

            if result.errors:
                return result

            result.is_valid = True
            return result
    except BadZipFile:
        result.errors.append("Package is not a valid ZIP archive.")
        return result


def _build_metadata(raw: Mapping[str, object]) -> AnalyticMetadata:
    if not isinstance(raw, Mapping):
        raise ValueError("metadata.json must contain a JSON object at the root")

    name = str(raw.get("name") or "").strip()
    version = str(raw.get("version") or "").strip()
    module_name = str(raw.get("module_name") or "").strip()

    missing = []
    if not name:
        missing.append("name")
    if not version:
        missing.append("version")
    if not module_name:
        missing.append("module_name")
    if missing:
        raise ValueError(f"metadata.json missing required field(s): {', '.join(missing)}")

    analytic_id = str(raw.get("analytic_id") or _normalize_analytic_id(name))
    dependencies = [str(item) for item in raw.get("dependencies", [])]
    execution_hints = raw.get("execution_hints", {})
    if not isinstance(execution_hints, dict):
        raise ValueError("metadata.json field 'execution_hints' must be an object")

    return AnalyticMetadata(
        analytic_id=analytic_id,
        name=name,
        version=version,
        module_name=module_name,
        entry_class=str(raw.get("entry_class") or "Analytic"),
        description=str(raw.get("description") or ""),
        dependencies=dependencies,
        execution_hints=execution_hints,
        required_license=(str(raw["required_license"]) if raw.get("required_license") else None),
        assets_path=(str(raw["assets_path"]) if raw.get("assets_path") else None),
        extra={key: value for key, value in raw.items() if key not in {
            "analytic_id",
            "name",
            "version",
            "module_name",
            "entry_class",
            "description",
            "dependencies",
            "execution_hints",
            "required_license",
            "assets_path",
        }},
    )
