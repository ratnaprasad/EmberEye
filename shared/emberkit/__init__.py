"""Compatibility exports for shared.emberkit.* imports."""

from embereye.utils.vision_logger import log_debug, log_error
from adaptive_fps import get_controller as get_fps_controller
from metrics import get_metrics

__all__ = [
    "log_debug",
    "log_error",
    "get_fps_controller",
    "get_metrics",
]
