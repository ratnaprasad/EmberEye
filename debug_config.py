"""
Debug configuration module for EmberEye.
Provides runtime debug toggle functionality.
"""

_debug_enabled = False

def set_debug_enabled(enabled: bool):
    """Enable or disable debug mode at runtime."""
    global _debug_enabled
    _debug_enabled = enabled
    print(f"[DEBUG_CONFIG] Debug mode {'enabled' if enabled else 'disabled'}")

def is_debug_enabled() -> bool:
    """Check if debug mode is currently enabled."""
    return _debug_enabled

def debug_print(*args, **kwargs):
    """Print debug messages only if debug mode is enabled."""
    if _debug_enabled:
        print("[DEBUG]", *args, **kwargs)
