from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


_SAFE_ID_RE = re.compile(r"[^a-z0-9_]+")


def _normalize_identifier(value: str, fallback: str = "analytic") -> str:
    normalized = _SAFE_ID_RE.sub("_", str(value).strip().lower()).strip("_")
    return normalized or fallback


@dataclass(slots=True)
class StudioEapkgSpec:
    analytic_id: str
    name: str
    version: str
    module_name: str
    entry_class: str = "Analytic"
    description: str = ""
    required_license: str | None = None
    dependencies: list[str] = field(default_factory=list)
    execution_hints: dict[str, object] = field(default_factory=dict)
    assets_path: str = "assets"


def default_spec_for_version(version_name: str) -> StudioEapkgSpec:
    clean_version = str(version_name).strip() or "v1"
    analytic_id = _normalize_identifier(f"studio_{clean_version}", fallback="studio_analytic")
    module_name = _normalize_identifier(f"analytic_{clean_version}", fallback="studio_analytic")
    return StudioEapkgSpec(
        analytic_id=analytic_id,
        name=f"Studio Model {clean_version}",
        version="1.0.0",
        module_name=module_name,
        description="Auto-generated analytic package exported from EmberEye Studio.",
        required_license=analytic_id,
        execution_hints={"trigger": "every_n_frames", "value": 1},
    )


def export_model_as_eapkg(
    *,
    model_path: str | Path,
    output_path: str | Path,
    spec: StudioEapkgSpec,
    master_classes_path: str | Path | None = None,
) -> Path:
    model_file = Path(model_path)
    destination = Path(output_path)

    if model_file.suffix.lower() != ".pt":
        raise ValueError(f"Expected a .pt model file, got: {model_file.name}")
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")

    if destination.suffix.lower() != ".eapkg":
        destination = destination.with_suffix(".eapkg")

    metadata = {
        "analytic_id": spec.analytic_id,
        "name": spec.name,
        "version": spec.version,
        "module_name": spec.module_name,
        "entry_class": spec.entry_class,
        "description": spec.description,
        "dependencies": spec.dependencies,
        "execution_hints": spec.execution_hints,
        "required_license": spec.required_license,
        "assets_path": spec.assets_path,
        "model_file": f"{spec.assets_path}/best.pt",
    }

    readme = (
        "# EmberEye Analytics Package\n\n"
        f"Analytic: {spec.name}\n"
        f"Analytic ID: {spec.analytic_id}\n"
        f"Version: {spec.version}\n\n"
        "This package was exported from EmberEye Studio and is compatible with\n"
        "the EmberEye Base .eapkg validator.\n"
    )

    module_init = "from .analytic import Analytic\n"
    module_impl = (
        "class Analytic:\n"
        "    def __init__(self):\n"
        "        self.config = {}\n\n"
        "    def get_metadata(self):\n"
        f"        return {{'analytic_id': '{spec.analytic_id}', 'name': '{spec.name}'}}\n\n"
        "    def configure(self, config):\n"
        "        self.config = dict(config or {})\n\n"
        "    def process_frame(self, frame_data):\n"
        "        return {'success': True, 'payload': {}, 'alerts': []}\n"
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, indent=2))
        archive.writestr(f"{spec.module_name}/__init__.py", module_init)
        archive.writestr(f"{spec.module_name}/analytic.py", module_impl)
        archive.writestr("README.md", readme)
        archive.write(model_file, arcname=f"{spec.assets_path}/best.pt")

        if master_classes_path:
            classes_file = Path(master_classes_path)
            if classes_file.exists():
                archive.write(classes_file, arcname=f"{spec.assets_path}/master_classes.json")

    return destination
