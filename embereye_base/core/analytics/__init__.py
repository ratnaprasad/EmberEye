"""Analytics category registry package."""
from .analytic_plugin import AnalyticPlugin
from .models import AnalyticMetadata, AnalyticResult, FrameData, SensorReading
from .analytics_registry import (
    ANALYTICS_REGISTRY,
    ANALYTICS_CATEGORY_NAMES,
    DEFAULT_ANALYTICS_CATEGORY,
    get_category,
    get_display_name,
    get_model_hint,
    get_fusion_cards,
)

__all__ = [
    "AnalyticMetadata",
    "AnalyticPlugin",
    "ANALYTICS_REGISTRY",
    "ANALYTICS_CATEGORY_NAMES",
    "AnalyticResult",
    "DEFAULT_ANALYTICS_CATEGORY",
    "FrameData",
    "SensorReading",
    "get_category",
    "get_display_name",
    "get_model_hint",
    "get_fusion_cards",
]
