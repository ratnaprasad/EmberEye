import copy
from types import MethodType, SimpleNamespace

import main_window as mw
from main_window import BEMainWindow


_METHODS = [
    "_normalize_analytics_category",
    "_normalize_enabled_analytics_categories",
    "_default_fusion_card_selection",
    "_default_fusion_pinned_selection",
    "_normalize_fusion_card_selection",
    "_normalize_fusion_pinned_selection",
    "_load_analytics_banner_preferences",
    "_persist_analytics_banner_preferences",
    "_apply_banner_preferences_to_widgets",
]


def _make_window_like(config):
    win = SimpleNamespace()
    win.config = copy.deepcopy(config)
    win.active_analytics_category = BEMainWindow._normalize_analytics_category(
        win, config.get("active_analytics_category", mw.DEFAULT_ANALYTICS_CATEGORY)
    )

    for method_name in _METHODS:
        setattr(win, method_name, MethodType(getattr(BEMainWindow, method_name), win))

    win._video_widgets = []
    win.get_video_widgets = MethodType(lambda self: list(self._video_widgets), win)
    return win


class _DummyWidget:
    def __init__(self, fusion_data):
        self.fusion_data = dict(fusion_data)
        self.applied_payload = None
        self.update_called = False

    def set_fusion_data(self, payload):
        self.applied_payload = dict(payload)
        self.fusion_data = dict(payload)

    def update(self):
        self.update_called = True


def test_mode_switch_and_manual_cards_persist_across_reload(monkeypatch):
    store = {}

    def _save_config(config):
        store.clear()
        store.update(copy.deepcopy(config))
        return True

    def _load_config():
        return copy.deepcopy(store)

    monkeypatch.setattr(mw.StreamConfig, "save_config", _save_config)
    monkeypatch.setattr(mw.StreamConfig, "load_config", _load_config)

    initial = {
        "active_analytics_category": "fire",
        "enabled_analytics_categories": ["fire"],
        "fusion_banner_mode": "auto",
        "fusion_banner_manual_cards": {"fire": ["global", "thermal"], "ppe": ["global"]},
        "fusion_banner_pinned_cards": {"fire": ["gas"], "ppe": []},
    }

    win = _make_window_like(initial)
    win._load_analytics_banner_preferences()

    win.enabled_analytics_categories = ["fire", "ppe"]
    win.fusion_banner_enabled = True
    win.fusion_banner_mode = "manual"
    win.fusion_banner_manual_cards = {
        "fire": ["gas", "global"],
        "ppe": ["vest", "global"],
    }
    win.fusion_banner_pinned_cards = {
        "fire": ["gas"],
        "ppe": ["vest"],
    }
    win.active_analytics_category = "ppe"

    win._persist_analytics_banner_preferences()

    assert store["fusion_banner_mode"] == "manual"
    assert store["active_analytics_category"] == "ppe"
    assert store["fusion_banner_manual_cards"]["fire"] == ["gas", "global"]
    assert store["fusion_banner_pinned_cards"]["ppe"] == ["vest"]

    reloaded = _make_window_like(mw.StreamConfig.load_config())
    reloaded._load_analytics_banner_preferences()

    assert reloaded.fusion_banner_mode == "manual"
    assert reloaded.fusion_banner_manual_cards["fire"] == ["gas", "global"]
    assert reloaded.fusion_banner_pinned_cards["fire"] == ["gas"]
    assert reloaded.fusion_banner_pinned_cards["ppe"] == ["vest"]


def test_apply_preferences_updates_existing_widget_payloads():
    config = {
        "active_analytics_category": "ppe",
        "enabled_analytics_categories": ["fire", "ppe"],
        "fusion_banner_mode": "manual",
        "fusion_banner_manual_cards": {"fire": ["global"], "ppe": ["vest", "global"]},
        "fusion_banner_pinned_cards": {"fire": ["gas"], "ppe": ["vest"]},
    }

    win = _make_window_like(config)
    win.enabled_analytics_categories = ["fire", "ppe"]
    win.fusion_banner_enabled = True
    win.fusion_banner_mode = "manual"
    win.fusion_banner_manual_cards = {"fire": ["global"], "ppe": ["vest", "global"]}
    win.fusion_banner_pinned_cards = {"fire": ["gas"], "ppe": ["vest"]}
    win.active_analytics_category = "ppe"

    widget = _DummyWidget({"alarm": False, "confidence": 0.6})
    win._video_widgets = [widget]

    win._apply_banner_preferences_to_widgets()

    assert widget.applied_payload is not None
    assert widget.applied_payload["fusion_banner_mode"] == "manual"
    assert widget.applied_payload["fusion_banner_manual_cards"]["ppe"] == ["vest", "global"]
    assert widget.applied_payload["fusion_banner_pinned_cards"]["ppe"] == ["vest"]
    assert widget.applied_payload["analytics_category"] == "ppe"
    assert widget.applied_payload["fusion_display_category"] == "ppe"
