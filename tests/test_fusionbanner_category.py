"""
Regression tests for fusionbanner._resolve_display_category() and helpers.

Verifies that the display category is resolved correctly from:
  1. Live window state (widget.window().active_analytics_category) — highest priority
  2. EMBEREYE_ANALYTICS_CATEGORY environment variable — fallback
  3. Per-frame fusion payload keys (fusion_display_category / analytics_category) — last resort
  4. Default "fire" when no source is present

Also covers _normalize_category() and _is_banner_enabled_for_category().
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIELD_UTIL_PATH = os.path.join(PROJECT_ROOT, "embereye-field", "util")
if FIELD_UTIL_PATH not in sys.path:
    sys.path.insert(0, FIELD_UTIL_PATH)

# Import module directly without triggering PyQt6 at import-time for the whole field package
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "fusionbanner",
    os.path.join(FIELD_UTIL_PATH, "fusionbanner.py"),
)
fusionbanner = _ilu.module_from_spec(_spec)

# Stub out PyQt6 so the module can be imported in a headless test environment
import types
_qt_stub = types.ModuleType("PyQt6")
for _sub in ("QtCore", "QtGui", "QtWidgets"):
    _mod = types.ModuleType(f"PyQt6.{_sub}")
    # Provide minimal attributes referenced at module level
    _mod.QRect = MagicMock()
    _mod.QRectF = MagicMock()
    _mod.Qt = MagicMock()
    _mod.QBrush = MagicMock()
    _mod.QColor = MagicMock()
    _mod.QFont = MagicMock()
    _mod.QLinearGradient = MagicMock()
    _mod.QPainterPath = MagicMock()
    _mod.QPen = MagicMock()
    _mod.QRadialGradient = MagicMock()
    setattr(_qt_stub, _sub, _mod)
    sys.modules[f"PyQt6.{_sub}"] = _mod
sys.modules["PyQt6"] = _qt_stub

_spec.loader.exec_module(fusionbanner)

_normalize_category = fusionbanner._normalize_category
_resolve_display_category = fusionbanner._resolve_display_category
_is_banner_enabled_for_category = fusionbanner._is_banner_enabled_for_category


def _make_widget(window_category=None):
    """Return a mock widget whose .window() has active_analytics_category set."""
    widget = MagicMock()
    window = MagicMock()
    if window_category is not None:
        window.active_analytics_category = window_category
    else:
        del window.active_analytics_category  # hasattr returns False
    widget.window.return_value = window
    return widget


class TestNormalizeCategory(unittest.TestCase):
    def test_fire_passthrough(self):
        self.assertEqual(_normalize_category("fire"), "fire")

    def test_ppe_passthrough(self):
        self.assertEqual(_normalize_category("ppe"), "ppe")

    def test_uppercase_normalized(self):
        self.assertEqual(_normalize_category("PPE"), "ppe")
        self.assertEqual(_normalize_category("FIRE"), "fire")

    def test_whitespace_stripped(self):
        self.assertEqual(_normalize_category("  ppe  "), "ppe")

    def test_unknown_defaults_to_fire(self):
        self.assertEqual(_normalize_category("thermal"), "fire")
        self.assertEqual(_normalize_category(""), "fire")
        self.assertEqual(_normalize_category(None), "fire")

    def test_invalid_type_defaults_to_fire(self):
        self.assertEqual(_normalize_category(123), "fire")


class TestResolveDisplayCategory(unittest.TestCase):

    # --- Priority 1: live window state ---

    def test_window_ppe_overrides_payload(self):
        widget = _make_widget("ppe")
        fusion = {"analytics_category": "fire", "fusion_display_category": "fire"}
        self.assertEqual(_resolve_display_category(widget, fusion), "ppe")

    def test_window_fire_overrides_ppe_payload(self):
        widget = _make_widget("fire")
        fusion = {"fusion_display_category": "ppe"}
        self.assertEqual(_resolve_display_category(widget, fusion), "fire")

    def test_window_normalizes_uppercase(self):
        widget = _make_widget("PPE")
        self.assertEqual(_resolve_display_category(widget, {}), "ppe")

    # --- Priority 2: env var (no window attribute) ---

    def test_env_var_ppe_used_when_no_window_attr(self):
        widget = _make_widget(window_category=None)
        with patch.dict(os.environ, {"EMBEREYE_ANALYTICS_CATEGORY": "ppe"}):
            self.assertEqual(_resolve_display_category(widget, {}), "ppe")

    def test_env_var_overrides_payload_when_no_window_attr(self):
        widget = _make_widget(window_category=None)
        fusion = {"analytics_category": "fire"}
        with patch.dict(os.environ, {"EMBEREYE_ANALYTICS_CATEGORY": "ppe"}):
            self.assertEqual(_resolve_display_category(widget, fusion), "ppe")

    # --- Priority 3: fusion payload ---

    def test_fusion_display_category_used_as_fallback(self):
        widget = _make_widget(window_category=None)
        fusion = {"fusion_display_category": "ppe"}
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EMBEREYE_ANALYTICS_CATEGORY", None)
            self.assertEqual(_resolve_display_category(widget, fusion), "ppe")

    def test_analytics_category_used_when_no_fusion_display_key(self):
        widget = _make_widget(window_category=None)
        fusion = {"analytics_category": "ppe"}
        os.environ.pop("EMBEREYE_ANALYTICS_CATEGORY", None)
        self.assertEqual(_resolve_display_category(widget, fusion), "ppe")

    # --- Priority 4: default ---

    def test_default_fire_when_nothing_set(self):
        widget = _make_widget(window_category=None)
        os.environ.pop("EMBEREYE_ANALYTICS_CATEGORY", None)
        self.assertEqual(_resolve_display_category(widget, {}), "fire")

    def test_none_widget_falls_back_gracefully(self):
        os.environ.pop("EMBEREYE_ANALYTICS_CATEGORY", None)
        self.assertEqual(_resolve_display_category(None, {}), "fire")

    def test_window_raises_still_falls_back(self):
        widget = MagicMock()
        widget.window.side_effect = RuntimeError("no window")
        os.environ.pop("EMBEREYE_ANALYTICS_CATEGORY", None)
        self.assertEqual(_resolve_display_category(widget, {"analytics_category": "ppe"}), "ppe")


class TestIsBannerEnabledForCategory(unittest.TestCase):
    def test_enabled_by_default(self):
        self.assertTrue(_is_banner_enabled_for_category({}, "fire"))

    def test_disabled_by_flag(self):
        self.assertFalse(_is_banner_enabled_for_category({"fusion_banner_enabled": False}, "fire"))

    def test_category_not_in_enabled_list(self):
        fusion = {"enabled_analytics_categories": ["fire"]}
        self.assertFalse(_is_banner_enabled_for_category(fusion, "ppe"))

    def test_category_in_enabled_list(self):
        fusion = {"enabled_analytics_categories": ["ppe", "fire"]}
        self.assertTrue(_is_banner_enabled_for_category(fusion, "ppe"))

    def test_empty_enabled_list_allows_all(self):
        fusion = {"enabled_analytics_categories": []}
        self.assertTrue(_is_banner_enabled_for_category(fusion, "fire"))


if __name__ == "__main__":
    unittest.main()
