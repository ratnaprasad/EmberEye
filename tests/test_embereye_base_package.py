from embereye_base import (
    AnalyticMetadata,
    AnalyticPlugin,
    AnalyticResult,
    FrameData,
    LicenseManager,
    PluginManager,
    validate_eapkg,
)


def test_embereye_base_top_level_exports_are_available():
    assert AnalyticMetadata is not None
    assert AnalyticPlugin is not None
    assert AnalyticResult is not None
    assert FrameData is not None
    assert LicenseManager is not None
    assert PluginManager is not None
    assert callable(validate_eapkg)