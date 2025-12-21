# EmberEye Project Structure

## Package Organization

The codebase is organized into the `embereye/` package with clear separation of concerns:

```
embereye/
├── app/           # UI components and dialogs
├── core/          # Core business logic and services
└── utils/         # Shared utilities and helpers
```

### embereye/app/
User interface components, dialogs, and presentation layer:
- `ee_loginwindow.py` - Login UI
- `annotation_tool.py` - Annotation interface
- `master_class_config.py`, `master_class_config_dialog.py` - Class taxonomy management
- `license_dialog.py`, `license_generator.py` - License management
- `password_reset.py`, `setup_wizard.py` - User management wizards
- `model_manager_modal.py` - Model management UI

### embereye/core/
Business logic, services, and domain models:
- `model_versioning.py` - Model lifecycle and versioning
- `training_pipeline.py` - Training orchestration
- `vision_detector.py` - Detection engine and threat classification
- `database_manager.py` - Data persistence
- `sensor_server.py` - Sensor communication
- `threat_rules.py` - Threat classification rules

### embereye/utils/
Shared utilities and cross-cutting concerns:
- `resource_helper.py` - Resource path resolution (dev vs packaged)
- `error_logger.py` - Centralized error logging
- `theme_manager.py` - UI theming
- `crash_logger.py` - Crash reporting
- `metrics.py` - Performance metrics
- `vision_logger.py` - Vision-specific logging
- `camera_stream_simulator.py` - Testing utilities
- `ip_loc_resolver.py` - Network utilities
- `debug_config.py` - Debug configuration

## Backward Compatibility

All moved modules have compatibility shims at their old locations that re-export from the new package:

```python
# Old location: resource_helper.py
"""
Compatibility shim: re-export from embereye.utils.resource_helper
"""
from embereye.utils.resource_helper import *  # noqa
```

This ensures existing imports continue to work without modification.

## Migration Notes

- Entry point: `main.py` (imports updated to use `embereye.*` paths)
- Main application: `main_window.py` (imports updated)
- All other modules use shims for transparent migration

## Best Practices

1. **New code**: Import from `embereye.*` packages directly
2. **Legacy code**: Continues to work via shims
3. **Refactoring**: Gradually update old imports when modifying files

## Future Work

- Move remaining test files to `tests/` directory
- Consider moving dialogs into `embereye/app/dialogs/` subdirectory
- Add `__init__.py` exports for cleaner imports
