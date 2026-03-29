from types import MethodType, SimpleNamespace

import main_window as mw
from main_window import BEMainWindow


def _make_window_like(config=None):
    config = dict(config or {})
    win = SimpleNamespace()
    win.config = config
    win.marketplace_enabled_analytics = {}
    win.marketplace_analytic_settings = {}
    win.marketplace_plugin_manager = None

    for method_name in (
        "_normalize_marketplace_enabled_analytics",
        "_normalize_marketplace_analytic_settings",
        "_set_marketplace_analytic_enabled",
    ):
        setattr(win, method_name, MethodType(getattr(BEMainWindow, method_name), win))

    return win


def test_normalize_marketplace_enabled_analytics_filters_keys():
    win = _make_window_like()

    result = win._normalize_marketplace_enabled_analytics(
        {"  GAS_GUARD ": 1, "": True, "smoke_guard": 0}
    )

    assert result == {"gas_guard": True, "smoke_guard": False}


def test_normalize_marketplace_analytic_settings_requires_object_values():
    win = _make_window_like()

    result = win._normalize_marketplace_analytic_settings(
        {
            "gas_guard": {"threshold": 10},
            "smoke_guard": [1, 2],
            "": {"x": 1},
        }
    )

    assert result == {"gas_guard": {"threshold": 10}}


def test_set_marketplace_analytic_enabled_persists_licensed_toggle(monkeypatch):
    saved_configs = []
    monkeypatch.setattr(mw.StreamConfig, "save_config", lambda cfg: saved_configs.append(dict(cfg)) or True)

    win = _make_window_like({})
    win.marketplace_plugin_manager = SimpleNamespace(
        descriptors=lambda: [
            SimpleNamespace(
                analytic_id="gas_guard",
                license_status="licensed",
                metadata=SimpleNamespace(name="Gas Guard"),
            )
        ]
    )

    win._set_marketplace_analytic_enabled("gas_guard", True)

    assert win.marketplace_enabled_analytics["gas_guard"] is True
    assert saved_configs
    assert saved_configs[-1]["enabled_marketplace_analytics"]["gas_guard"] is True


def test_set_marketplace_analytic_enabled_blocks_unlicensed(monkeypatch):
    warnings = []
    saved_configs = []

    monkeypatch.setattr(mw.StreamConfig, "save_config", lambda cfg: saved_configs.append(dict(cfg)) or True)
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]) or 0)

    win = _make_window_like({})
    win.marketplace_plugin_manager = SimpleNamespace(
        descriptors=lambda: [
            SimpleNamespace(
                analytic_id="gas_guard",
                license_status="unlicensed",
                metadata=SimpleNamespace(name="Gas Guard"),
            )
        ]
    )

    win._set_marketplace_analytic_enabled("gas_guard", True)

    assert win.marketplace_enabled_analytics["gas_guard"] is False
    assert warnings
    assert "not licensed" in warnings[-1]
    assert saved_configs[-1]["enabled_marketplace_analytics"]["gas_guard"] is False
