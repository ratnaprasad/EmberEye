# EmberEye Deployment - Folder Structure Guide

## Overview
EmberEye now handles runtime folders correctly for both **source mode** (development) and **packaged mode** (deployed executable).

## Folder Strategy

### Development/Source Mode
When running from source (`python main.py`), all folders are created in the **current working directory**:
```
EmberEye/
├── annotations/          # Annotation tool output
├── training_data/        # Training datasets
│   └── annotations/      # Registered training annotations
├── models/              # YOLO model weights
├── logs/                # Application logs
├── model_versions/      # Trained model versions
├── stream_config.json   # Stream configuration
└── users.db            # User database
```

### Packaged/Executable Mode
When running as a packaged executable, all runtime folders are created in the **user's home directory**:

**Location:** `~/.embereye/workspace/`

```
~/.embereye/
└── workspace/
    ├── annotations/          # Annotation tool output
    ├── training_data/        # Training datasets
    │   └── annotations/      # Registered training annotations
    ├── models/              # YOLO model weights
    ├── logs/                # Application logs
    ├── model_versions/      # Trained model versions
    ├── stream_config.json   # Stream configuration
    └── users.db            # User database
```

## Implementation Details

### Key Files Modified
1. **`resource_helper.py`** - Core path resolution functions:
   - `get_resource_path(path)` - For read-only bundled resources (logo, etc.)
   - `get_writable_path(path)` - For config files (stream_config.json, users.db)
   - `get_data_path(path)` - For runtime data folders (annotations, training_data, etc.)
   - `ensure_runtime_folders()` - Creates all necessary folders on startup

2. **`main.py`** - Initialization:
   - Calls `ensure_runtime_folders()` on app startup
   - Creates all necessary folders before any operations

3. **`main_window.py`** - Training Manager:
   - Uses `get_data_path()` for annotations and training_data paths
   - Properly resolves workspace-relative paths

4. **`annotation_tool.py`** - Annotation Tool:
   - Uses `get_data_path()` for annotations output
   - Saves to correct location in both modes

## PyInstaller Spec File Requirements

Ensure your `.spec` file includes:

```python
# Bundle required data files
datas=[
    ('logo.png', '.'),
    ('models/yolov8n_fire.pt', 'models'),
    ('stream_config.json', '.'),
    ('users.db', '.'),
],

# Exclude unnecessary folders from bundle
pathex=[],
```

## User Experience

### First Run (Packaged)
1. App creates `~/.embereye/workspace/` directory
2. All runtime folders are created automatically
3. Config files are initialized if missing
4. User data persists across app updates

### Data Location
Users can find their data at:
- **macOS/Linux:** `~/.embereye/workspace/`
- **Windows:** `C:\Users\<username>\.embereye\workspace\`

### Benefits
✅ Clean separation of bundled vs. user data
✅ Works without admin/write permissions
✅ Data persists across app updates
✅ Multiple users can have independent data
✅ Easy backup (just copy ~/.embereye folder)

## Testing Checklist

Before deployment, verify:
- [ ] App starts and creates folders in `~/.embereye/workspace/`
- [ ] Annotation tool saves to correct location
- [ ] Training data is found and used correctly
- [ ] Model versions are saved and loaded properly
- [ ] Logs are written to correct location
- [ ] Config changes persist across restarts

## Troubleshooting

**Issue:** App can't create folders
- **Solution:** Check write permissions for user home directory

**Issue:** Old data not found after update
- **Solution:** Check if data exists in old location and migrate to `~/.embereye/workspace/`

**Issue:** Multiple installations interfere
- **Solution:** Each user gets their own `~/.embereye/` folder automatically
