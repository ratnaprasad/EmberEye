import json
import zipfile
from pathlib import Path

from import_analytics_dialog import import_analytics_packages, next_available_target_path


def _build_eapkg(
    package_path: Path,
    *,
    analytic_id: str = "sample_guard",
    include_metadata: bool = True,
    include_module_init: bool = True,
    include_analytic_impl: bool = True,
):
    payload = {
        "analytic_id": analytic_id,
        "name": "Sample Guard",
        "version": "1.0.0",
        "module_name": analytic_id,
        "entry_class": "Analytic",
        "description": "Sample package used by import dialog tests.",
        "dependencies": [],
        "execution_hints": {"trigger": "every_n_frames", "value": 5},
        "required_license": analytic_id,
    }

    with zipfile.ZipFile(package_path, "w") as archive:
        if include_metadata:
            archive.writestr("metadata.json", json.dumps(payload, indent=2))
        if include_module_init:
            archive.writestr(f"{analytic_id}/__init__.py", "from .analytic import Analytic\n")
        if include_analytic_impl:
            archive.writestr(f"{analytic_id}/analytic.py", "class Analytic:\n    pass\n")


def test_next_available_target_path_appends_suffix(tmp_path):
    base = tmp_path / "sample_guard.eapkg"
    base.write_text("occupied", encoding="utf-8")

    next_path = next_available_target_path(base)

    assert next_path.name == "sample_guard_1.eapkg"


def test_import_analytics_packages_imports_valid_and_skips_invalid(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()

    _build_eapkg(source / "valid.eapkg", analytic_id="valid")
    _build_eapkg(source / "invalid.eapkg", analytic_id="invalid", include_analytic_impl=False)

    result = import_analytics_packages(source, target, show_progress=False)

    assert result.discovered == 2
    assert result.imported == 1
    assert result.failed == 1
    assert (target / "valid.eapkg").exists()
    assert any("invalid.eapkg" in item for item in result.failures)


def test_import_analytics_packages_handles_duplicate_filenames(tmp_path):
    source = tmp_path / "source"
    source.mkdir(parents=True)

    nested = source / "nested"
    nested.mkdir(parents=True)

    _build_eapkg(source / "dup.eapkg", analytic_id="dup_one")
    _build_eapkg(nested / "dup.eapkg", analytic_id="dup_two")

    target = tmp_path / "target"

    result = import_analytics_packages(source, target, show_progress=False)

    assert result.discovered == 2
    assert result.imported == 2
    assert result.failed == 0
    assert (target / "dup.eapkg").exists()
    assert (target / "dup_1.eapkg").exists()


def test_import_analytics_packages_no_candidates(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()

    result = import_analytics_packages(source, target, show_progress=False)

    assert result.discovered == 0
    assert result.imported == 0
    assert result.failed == 0
