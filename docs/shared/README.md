# 🔥 Ember Eye Command Center

**Advanced Thermal Vision & Fire Detection System with Real-time YOLO Detection, Sensor Fusion, and PFDS Integration**

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/license-Private-red.svg)]()

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Release Notes](#release-notes)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Testing](#testing)
- [Usage Guide](#usage-guide)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

Ember Eye is a sophisticated command center application for real-time thermal vision monitoring, fire detection, and automated response coordination. It combines multiple sensor inputs with AI-powered vision detection to provide comprehensive safety monitoring.

### What It Does

- **Real-time Thermal Monitoring**: Multi-camera thermal vision with hot spot detection
- **AI Fire Detection**: YOLOv8-based fire, smoke, and flame detection
- **Sensor Fusion**: Combines thermal, gas, smoke, and flame sensors for accurate threat assessment
- **PFDS Integration**: Automated Pre-action Fire Detection System control
- **Anomaly Tracking**: Historical anomaly logging with thermal ROI extraction
- **Modern UI**: Clean, professional interface with compact header and responsive design

## ✨ Key Features

### 1. **Modern UI Header** (Latest Feature)
- Forced modern layout with "Ember Eye Command Center" branding
- Compact 50px header visible by default
- Enhanced Settings (⚙ SETTINGS) and Profile (👤 PROFILE) buttons
- Inline Group/Grid dropdowns for quick access
- Maximized window for full workspace utilization

### 2. **Thermal Vision & Anomalies**
- Real-time thermal frame analysis with ROI extraction
- Anomaly detection and historical tracking
- Configurable severity classification (Critical, High, Medium, Low)
- Frame-by-frame thermal data with timestamps
- JSON-based anomaly persistence

### 3. **YOLO Training Interface**
- Interactive frame ingestion with similarity detection
- Multi-class training support with hierarchical taxonomy
- Training progress tracking with real-time updates
- Model versioning and rollback capability
- Manual frame selection with de-duplication

### 4. **Master Class Configuration**
- Hierarchical class/subclass taxonomy management
- Dynamic class loading with UI dialog
- Supports nested classifications (e.g., person:adult, vehicle:car)
- Runtime taxonomy updates without restart

### 5. **Sensor Fusion Engine**
- Multi-source data fusion (thermal, gas, smoke, flame, vision)
- Configurable thresholds and weights
- Confidence scoring with alarm triggering
- Hot cell tracking with decay time
- Freeze-on-alarm capability

### 6. **Debug Toggle System**
- Runtime debug enable/disable
- Conditional debug printing
- Performance-friendly logging
- No restart required

### 7. **Enhanced Error Handling**
- Global TCP callback wrapper with thread safety
- Fallback methods for missing attributes
- Comprehensive None guards
- Graceful degradation

### 8. **License Validation** (Dev Mode)
- License key validation system
- Dev-mode bypass for development
- Renewal dialogs and grace periods

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Ember Eye Command Center                    │
│                    (PyQt5 Main Window)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  VIDEOWALL  │ │  ANOMALIES  │ │   DEVICES   │
│    Tab      │ │     Tab     │ │     Tab     │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
       ┌───────────────┴───────────────┐
       │                               │
       ▼                               ▼
┌─────────────┐              ┌──────────────────┐
│   Vision    │              │  TCP Sensor      │
│  Detector   │◄────────────►│     Server       │
│  (YOLO)     │              │  (Port 4888)     │
└──────┬──────┘              └────────┬─────────┘
       │                              │
       │         ┌────────────────────┘
       │         │
       ▼         ▼
┌──────────────────────────┐
│    Sensor Fusion         │
│  (Multi-source merger)   │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│    PFDS Manager          │
│  (Fire suppression)      │
└──────────────────────────┘
```

### Component Overview

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Main Window** | UI orchestration | PyQt5 |
| **Video Widget** | RTSP stream display | OpenCV, QThread |
| **Vision Detector** | Fire/smoke detection | YOLOv8, Ultralytics |
| **TCP Server** | Sensor data ingestion | asyncio/threading |
| **Sensor Fusion** | Multi-sensor analysis | NumPy |
| **PFDS Manager** | Fire system control | TCP commands |
| **Anomalies Manager** | Thermal data logging | JSON persistence |
| **WebSocket Client** | Real-time updates | websockets |
| **Metrics Server** | Prometheus endpoint | HTTP server |

## 🏷 Release Notes

- Product versioning policy: [VERSIONING_POLICY.md](d:/EE/EmberEye/docs/VERSIONING_POLICY.md)
- Release notes index: [releases/README.md](d:/EE/EmberEye/docs/releases/README.md)
- Current stable release: [releases/RELEASE_NOTES_2026-03-19.md](d:/EE/EmberEye/docs/releases/RELEASE_NOTES_2026-03-19.md)

## 📦 Installation

### Prerequisites

- **Python**: 3.12+ (3.12 recommended)
- **OS**: macOS, Linux, or Windows
- **RAM**: 4GB minimum, 8GB recommended
- **GPU**: Optional (for YOLO acceleration)

### 1. Clone Repository

```bash
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye
```

### 2. Create Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Download YOLO Models

```bash
# Models should be placed in models/ directory
# - yolov8n_fire.pt (fire detection)
# - fire_detection.pt (smoke/flame detection)
```

### 5. Configure Environment

```bash
# Optional: Skip license check for development
export SKIP_LICENSE_CHECK=true
```

## 🚀 Quick Start

### Start the Application

```bash
python main.py
```

The application will:
1. Initialize crash logger
2. Start TCP sensor server (port 4888)
3. Load YOLO models
4. Connect WebSocket client
5. Start metrics server (port 9090)
6. Launch UI in maximized modern layout

### Start the TCP Simulator (Separate Terminal)

```bash
python simulators/tcp_sensor_simulator_v3.py
```

This generates synthetic sensor data for testing.

### Access Metrics

```bash
# Prometheus metrics endpoint
curl http://localhost:9090/metrics
```

## ⚙️ Configuration

### Stream Configuration (`stream_config.json`)

```json
{
    "groups": ["Default"],
    "streams": [
        {
            "loc_id": "demo_room",
            "name": "Demo Room (Simulator)",
            "url": "rtsp://127.0.0.1:8554/demo",
            "group": "Default"
        }
    ],
    "tcp_port": 4888,
    "thermal_calibration": {
        "signed": true,
        "scale": 0.01,
        "offset": 0.0
    },
    "tcp_mode": "async"
}
```

### Master Classes (`master_classes.json`)

```json
{
    "person": {
        "subclasses": ["adult", "child", "worker"]
    },
    "vehicle": {
        "subclasses": ["car", "truck", "forklift"]
    },
    "fire": {
        "subclasses": ["open_flame", "smoldering", "spark"]
    }
}
```

### Sensor Fusion Thresholds

Access via: **Settings → Sensor Configuration**

- Temperature threshold: 40°C
- Gas PPM threshold: 400
- Smoke threshold: 25%
- Flame threshold: 25%
- Min sources: 2

## 🧪 Testing

### Unit Tests

```bash
# Run complete test suite
python test_embereye_suite.py

# Run specific tests
python test_ai_sensor_components.py
python test_ui_integration.py
```

### Integration Testing

```bash
# Terminal 1: Start simulator
python simulators/tcp_sensor_simulator_v3.py

# Terminal 2: Start application
python main.py

# Terminal 3: Send test commands
python test_send_commands.py
```

### Load Testing

```bash
# Test TCP sensor throughput
python tcp_sensor_load_test.py

# Test camera stream performance
python camera_stream_load_test.py
```

## 📖 Usage Guide

### Adding Streams

1. Click **Settings** (⚙ SETTINGS)
2. Select **🎥 Configure Streams**
3. Add stream details:
   - Location ID (unique)
   - Name
   - RTSP URL or camera index
   - Group assignment
4. Click **Save**

### Training YOLO Models

1. Navigate to **ANOMALIES** tab
2. Click **Ingest Frames** section
3. Select class from dropdown
4. Choose video file or camera
5. Review frames (similarity detection removes duplicates)
6. Click **Start Training**
7. Monitor progress in real-time

### Configuring Master Classes

1. Click **Settings** (⚙ SETTINGS)
2. Select **📚 Class & Subclass Manager**
3. Add/edit classes and subclasses
4. Click **Save and Close**
5. Classes update immediately (no restart needed)

### Viewing Anomalies

1. Navigate to **ANOMALIES** tab
2. View captured thermal anomalies as thumbnails
3. Filter by severity or timestamp
4. Export anomaly data via JSON

### Managing PFDS Devices

1. Click **Settings** (⚙ SETTINGS)
2. Select **🔥 PFDS Devices → Add Device**
3. Enter device details:
   - Location ID
   - IP address
   - Port
4. Devices auto-trigger on alarm events

## 📚 API Documentation

### Main Window API

```python
from main_window import BEMainWindow

# Initialize
window = BEMainWindow(theme_manager=None)

# Add stream
window.config['streams'].append({
    'loc_id': 'cam01',
    'name': 'Camera 1',
    'url': 'rtsp://192.168.1.100:554/stream',
    'group': 'Default'
})

# Update grid
window.update_rtsp_grid()
```

### Sensor Fusion API

```python
from sensor_fusion import SensorFusion

fusion = SensorFusion(
    temp_threshold=40.0,
    gas_ppm_threshold=400,
    smoke_threshold_pct=25.0,
    flame_threshold_pct=25.0
)

result = fusion.fuse(
    temp=45.0,
    gas_ppm=450,
    smoke_pct=30.0,
    flame_pct=20.0,
    vision_score=0.85
)

# result = {'alarm': True, 'confidence': 0.92, 'sources_triggered': 4}
```

### Anomalies Manager API

```python
from anomalies import AnomaliesManager, AnomalyRecord

manager = AnomaliesManager(base_dir='./anomalies')

# Add anomaly
record = AnomalyRecord(
    timestamp=time.time(),
    anomaly_type='high_temperature',
    severity='critical',
    location='zone_a',
    sensor_values={'temp': 65.5}
)
manager.add_anomaly(record)

# Retrieve recent
recent = manager.get_recent_anomalies(count=10)
```

### YOLO Trainer API

```python
from anomalies import YOLOTrainer

trainer = YOLOTrainer(model_base_path='./models/yolo_training')

# Add frames
trainer.add_training_frame(frame, annotations={
    'boxes': [[x, y, w, h]],
    'labels': ['fire'],
    'class_name': 'fire'
})

# Start training
trainer.start_training(epochs=50, batch_size=16, imgsz=640)

# Get progress
progress = trainer.get_progress()
# {'epoch': 10, 'total_epochs': 50, 'loss': 0.234}
```

## 🔧 Development

### Project Structure

```
EmberEye/
├── main.py                      # Application entry point
├── main_window.py               # Main UI (2894 lines)
├── video_widget.py              # Video stream display
├── embereye_base/core/vision_detector.py           # YOLO detection
├── sensor_fusion.py             # Multi-sensor fusion
├── tcp_sensor_server.py         # TCP data ingestion
├── pfds_manager.py              # Fire system control
├── anomalies.py                 # Thermal anomalies (245 lines)
├── debug_config.py              # Debug toggle (21 lines)
├── master_class_config.py       # Class taxonomy (66 lines)
├── master_class_config_dialog.py # Class config UI (153 lines)
├── stream_config.json           # Stream configuration
├── requirements.txt             # Dependencies
├── models/                      # YOLO models
├── docs/                        # Documentation
├── tests/                       # Test files
└── logs/                        # Application logs
```

### Adding New Features

1. Create feature module in root directory
2. Import in `main_window.py`
3. Add UI elements in `initUI()` or relevant tab
4. Connect signals/slots
5. Add configuration to `stream_config.json` if needed
6. Write tests
7. Update documentation

### Debugging

Enable debug mode:

```python
from debug_config import set_debug_enabled, debug_print

set_debug_enabled(True)
debug_print("Debug message")  # Only prints if enabled
```

## 🐛 Troubleshooting

### Common Issues

**1. AttributeError: 'NoneType' object has no attribute 'start'**

✅ Fixed with comprehensive None guards. If you still see this:
- Check if services are initialized
- Verify `__init__` completed successfully

**2. RTSP Connection Refused**

```
Connection to tcp://127.0.0.1:8554 failed: Connection refused
```

Solution: Start RTSP simulator or configure valid camera URLs

**3. TCP Server Port Already in Use**

```
OSError: [Errno 48] Address already in use
```

Solution:
```bash
lsof -ti:4888 | xargs kill -9
```

**4. YOLO Model Not Found**

```
FileNotFoundError: [Errno 2] No such file or directory: 'models/yolov8n_fire.pt'
```

Solution: Download models and place in `models/` directory

**5. License Validation Error**

Solution: Set environment variable
```bash
export SKIP_LICENSE_CHECK=true
```

### Log Files

- **Application**: `logs/crash.log`
- **TCP Debug**: `logs/tcp_debug.log`
- **Vision Debug**: `logs/vision_debug.log`
- **Performance**: `logs/performance_report.json`

## 📊 Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Startup Time | ~3-5 seconds |
| Frame Processing | 30 FPS (1080p) |
| TCP Throughput | 1000 packets/sec |
| Memory Usage | 300-500 MB |
| CPU Usage | 15-30% (single core) |

### Optimization Tips

1. Use async TCP mode for better throughput
2. Reduce grid size (2×2) for lower resource usage
3. Disable numeric thermal grid if not needed
4. Use smaller YOLO models (yolov8n vs yolov8x)
5. Limit anomaly retention to 7 days

## 📝 Recent Updates (Dec 20, 2025)

### ✅ Completed Features

- **Modern UI Header**: Forced modern layout with enhanced branding
- **Restored Features**: Anomalies, YOLO Training, Debug Toggle, Master Class Config
- **Enhanced Error Handling**: Comprehensive fallbacks and None guards
- **GitHub Integration**: Private repository created
- **Documentation**: Complete README with usage guide

### 🔄 In Progress

- X-ray effect features (auto-hide UI)
- End-to-end testing validation
- Advanced resource management

## 🤝 Contributing

This is a private repository. Contact the maintainer for access.

## 📄 License

Private - All rights reserved

## 👥 Authors

- **Developer**: Ratna Prasad Kakani
- **Organization**: LABY

## 📧 Support

For issues or questions, please contact the development team.

---

**Built with ❤️ using Python, PyQt5, and YOLOv8**
