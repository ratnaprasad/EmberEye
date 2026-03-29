import sys
import importlib.util
import zipfile
from pathlib import Path

from embereye_base.core.marketplace import validate_eapkg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STUDIO_DIR = PROJECT_ROOT / "embereye-studio"
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

_EXPORTER_PATH = STUDIO_DIR / "analytics_package_exporter.py"
_EXPORTER_SPEC = importlib.util.spec_from_file_location("studio_analytics_package_exporter", _EXPORTER_PATH)
assert _EXPORTER_SPEC is not None and _EXPORTER_SPEC.loader is not None
_EXPORTER_MODULE = importlib.util.module_from_spec(_EXPORTER_SPEC)
sys.modules[_EXPORTER_SPEC.name] = _EXPORTER_MODULE
_EXPORTER_SPEC.loader.exec_module(_EXPORTER_MODULE)

default_spec_for_version = _EXPORTER_MODULE.default_spec_for_version
export_model_as_eapkg = _EXPORTER_MODULE.export_model_as_eapkg


def test_studio_export_creates_validator_compatible_eapkg(tmp_path):
    model_file = tmp_path / "best.pt"
    model_file.write_bytes(b"dummy-model-bytes")

    classes_file = tmp_path / "master_classes.json"
    classes_file.write_text('{"fire": ["smoke"]}', encoding="utf-8")

    output_file = tmp_path / "studio-export.eapkg"
    spec = default_spec_for_version("v42")

    package_path = export_model_as_eapkg(
        model_path=model_file,
        output_path=output_file,
        spec=spec,
        master_classes_path=classes_file,
    )

    assert package_path.exists()
    result = validate_eapkg(package_path)
    assert result.is_valid is True
    assert result.errors == []
    assert result.metadata is not None
    assert result.metadata.analytic_id == spec.analytic_id
    assert result.metadata.module_name == spec.module_name

    with zipfile.ZipFile(package_path, "r") as archive:
        names = set(archive.namelist())

    assert "metadata.json" in names
    assert f"{spec.module_name}/__init__.py" in names
    assert f"{spec.module_name}/analytic.py" in names
    assert "assets/best.pt" in names
    assert "assets/master_classes.json" in names
