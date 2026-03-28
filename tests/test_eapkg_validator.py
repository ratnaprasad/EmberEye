import json
import zipfile
from pathlib import Path

from embereye_base.core.marketplace import validate_eapkg


def _build_eapkg(
    tmp_path: Path,
    *,
    metadata: dict | None = None,
    include_metadata: bool = True,
    include_module_init: bool = True,
    include_analytic_impl: bool = True,
    filename: str = "sample_guard-1.0.0.eapkg",
) -> Path:
    package_path = tmp_path / filename
    payload = {
        "analytic_id": "sample_guard",
        "name": "Sample Guard",
        "version": "1.0.0",
        "module_name": "sample_guard",
        "entry_class": "Analytic",
        "description": "Sample package used by validator tests.",
        "dependencies": [],
        "execution_hints": {"trigger": "every_n_frames", "value": 5},
        "required_license": "sample_guard",
    }
    if metadata:
        payload.update(metadata)

    with zipfile.ZipFile(package_path, "w") as archive:
        if include_metadata:
            archive.writestr("metadata.json", json.dumps(payload, indent=2))
        if include_module_init:
            archive.writestr("sample_guard/__init__.py", "from .analytic import Analytic\n")
        if include_analytic_impl:
            archive.writestr(
                "sample_guard/analytic.py",
                "class Analytic:\n    pass\n",
            )

    return package_path


def test_validate_eapkg_accepts_valid_package(tmp_path):
    package_path = _build_eapkg(tmp_path)

    result = validate_eapkg(package_path)

    assert result.is_valid is True
    assert result.errors == []
    assert result.metadata is not None
    assert result.metadata.analytic_id == "sample_guard"
    assert result.metadata.module_name == "sample_guard"
    assert result.metadata.required_license == "sample_guard"


def test_validate_eapkg_rejects_missing_metadata(tmp_path):
    package_path = _build_eapkg(tmp_path, include_metadata=False)

    result = validate_eapkg(package_path)

    assert result.is_valid is False
    assert result.metadata is None
    assert "metadata.json is missing from the package root." in result.errors


def test_validate_eapkg_rejects_missing_module_files(tmp_path):
    package_path = _build_eapkg(tmp_path, include_analytic_impl=False)

    result = validate_eapkg(package_path)

    assert result.is_valid is False
    assert result.metadata is not None
    assert "Missing analytic implementation file: sample_guard/analytic.py" in result.errors


def test_validate_eapkg_rejects_missing_required_metadata_fields(tmp_path):
    package_path = _build_eapkg(tmp_path, metadata={"module_name": ""})

    result = validate_eapkg(package_path)

    assert result.is_valid is False
    assert result.metadata is None
    assert "metadata.json missing required field(s): module_name" in result.errors


def test_validate_eapkg_rejects_wrong_extension(tmp_path):
    package_path = _build_eapkg(tmp_path, filename="sample_guard-1.0.0.zip")

    result = validate_eapkg(package_path)

    assert result.is_valid is False
    assert result.metadata is None
    assert result.errors == ["Package must use the .eapkg extension."]
