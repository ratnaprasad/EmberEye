# EmberEye v1.0.0 - Real-Time Thermal & AI Detection System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Platform Support](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-brightgreen.svg)](#installation)

EmberEye is a **production-ready thermal imaging and AI detection framework** that combines real-time thermal video streams with advanced computer vision for intelligent monitoring and threat detection.

## 🎯 Features

- **Multi-Source Thermal Imaging** - Support for multiple thermal camera models (FLIR, ICI, custom TCP)
- **Real-Time AI Detection** - YOLOv8 integration for object, person, and anomaly detection
- **Sensor Fusion** - Combine thermal, visual, and environmental sensors for comprehensive analysis
- **Adaptive GPU/CPU Processing** - Automatic performance optimization based on system resources
- **Enterprise Dashboard** - Real-time monitoring, alerts, and analytics
- **Distributed Architecture** - TCP/WebSocket support for remote device management
- **Cross-Platform** - Native support for Windows, Linux, and macOS
- **Community-Friendly** - MIT licensed, extensible architecture

## 🚀 Quick Start

### System Requirements
- **Python**: 3.12 or higher
- **GPU** (optional): CUDA 12.x for GPU acceleration
- **RAM**: 8GB minimum (16GB recommended)
- **Storage**: 2GB for dependencies

### Installation

#### Windows (Automated)
1. Download `EmberEye-Setup.zip` from [Releases](https://github.com/ratnaprasad/EmberEye/releases)
2. Extract and run `setup_windows.bat`
3. Follow the prompts (installs Python, Git, dependencies automatically)
4. Launch from desktop shortcut

#### Manual Setup (All Platforms)
```bash
# Clone repository
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

#### Docker
```bash
docker build -t embereye:latest .
docker run -it --gpus all -e DISPLAY=$DISPLAY embereye:latest
```

### Quick Start - Field App with RTSP Simulator

For testing the Field application with simulated camera streams:

#### Automated (One Command)
```batch
# Windows - Starts RTSP simulator + Field app together
start_field.bat
```

This will automatically:
1. Start MediaMTX RTSP server
2. Begin streaming test video (IMG_1318.MOV)
3. Launch EmberEye Field monitoring application

**Stream URL:** `rtsp://localhost:8554/camera1`

#### Manual Steps
```batch
# 1. Start RTSP camera simulator
cd simulators\rtsp
start_camera.bat

# 2. Start Field application (new terminal)
cd ..\..
python embereye-field\main.py
```

#### Stop All Services
```batch
stop_field.bat
```

See [RTSP Simulator Documentation](./simulators/rtsp/README.md) for advanced configuration.

## 📖 Documentation

- [Installation Guide](./docs/INSTALLATION.md)
- [User Guide](./docs/USER_GUIDE.md)
- [API Reference](./docs/API.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [Thermal Camera Integration](./docs/CAMERA_INTEGRATION.md)

## 🔥 Field Alarm Hybrid Flow (Proposed)

This proposal keeps **sensor fusion** and adds **class/subclass rules** on top to maximize accuracy and reduce false alarms. It explicitly includes thermal camera frames, smoke sensor, and flame sensor data.

### Inputs

- **YOLO detections**: class + subclass labels with confidence scores.
- **Thermal camera frames**: 2D temperature grid + thermal max + hot cells.
- **Smoke sensor**: analog percentage threshold.
- **Flame sensor**: analog percentage + digital state.

### Hybrid Decision Flow

```
Camera Frames + YOLO Detections ─┐
										  ├─> Rules Engine ─┐
Thermal Frame Grid ──────────────┘                 │
Smoke + Flame Sensors ─────────────> Sensor Fusion ├─> Final Alarm + Severity
																	│
																	└─> Incident Log (metadata + snapshot)
```

### Sensor Fusion (Physical Threat Signal)

- Uses thermal max, smoke, flame, gas, and optional vision score.
- Alarm when multi-sensor correlation confirms fire risk.
- Immediate alarm on critical smoke or gas thresholds.
- Captures hot cells for thermal overlay.

### Rules Engine (Semantic Threat Signal)

- Uses detected classes/subclasses and context flags.
- Applies Class & Subclass Manager rules for severity.
- Examples:
  - `flame + indoor` → CRITICAL
  - `smoke_heavy + confined_space` → CRITICAL
  - `steam` alone → LOW (no alarm)

### Final Alarm Logic

- **CRITICAL rules** → immediate alarm.
- **HIGH rules** → alarm if fusion confidence is above a minimum (reduces false positives).
- **MEDIUM/LOW rules** → log incident, no alarm.
- **Fusion alarm** always triggers alarm even if YOLO is uncertain.

### Resulting Benefits

- **Highest accuracy** (vision + thermal + sensors).
- **Lower false alarms** (rule filtering + fusion confirmation).
- **Fewer missed fires** (thermal rise before visible flames).
- **Redundancy** if camera or sensors are unavailable.

## 🧭 Camera Tile Display Modes (Proposed)

Each camera tile should have display toggles with consistent behavior in **minimized** and **maximized** layouts.

### Modes

1. **Default** (renamed from "Camera + Fusion Overlay")
	- RGB/visual camera feed.
	- Fusion overlay enabled (alarm state, temp, confidence, hot cells summary).
	- **Default enabled** on app start for all tiles.

2. **Thermal + Fusion Overlay**
	- Thermal camera feed view.
	- Fusion overlay enabled.

3. **Thermal Numeric Grid + Fusion Overlay**
	- Numeric thermal grid values view.
	- Fusion overlay enabled.

### Default Behavior

- **Default mode ON** for all cameras on initial load.
- Mode selection persists while the app is running.
- Toggle behavior is identical in minimized and maximized views.

## 🏗️ Project Structure

```
EmberEye/
├── embereye/              # Core package
│   ├── app/              # PyQt5 UI components
│   ├── core/             # Detection, streaming, sensor logic
│   ├── utils/            # Helpers, logging, configuration
│   └── config/           # Default configurations
├── models/               # Pre-trained AI models
├── tests/                # Test suite
├── simulators/           # Device simulators for testing
├── docs/                 # Documentation
├── main.py              # Application entry point
└── requirements.txt     # Python dependencies
```

## 💻 Usage

### Start the Application
```bash
python main.py
```

### Access Web Dashboard (if enabled)
```
http://localhost:8080
```

### Build Executable (Windows)
```bash
cd EmberEye
.\build_windows.bat
# Output: dist\EmberEye.exe (~1GB)
```

## 🔌 Supported Hardware

### Thermal Cameras
- FLIR AX series
- ICI A-series
- Custom TCP/Ethernet thermal devices
- Video file input (for testing)

### GPU Support
- NVIDIA CUDA 12.x (optimal)
- AMD ROCm (experimental)
- CPU fallback (automatic)

## 🧪 Testing

```bash
# Run tests
cd tests
python -m pytest

# Run specific test
python test_integration.py

# Load tests
python camera_stream_load_test.py
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

**Areas for contribution:**
- 🐛 Bug fixes
- ✨ New camera integrations
- 🎨 UI/UX improvements
- 📖 Documentation
- 🧪 Tests

## 📊 Performance

- **Detection FPS**: 25-60 FPS (GPU-dependent)
- **Latency**: <100ms (with GPU)
- **Memory**: ~800MB base + model size
- **Thermal Stream**: 640x480 @ 30 FPS typical

## 🔒 Security

- No external dependencies on cloud services (fully offline)
- Local-only processing
- Configurable encryption for network data
- Secure credential management

## 📝 License

This project is licensed under the **MIT License** - see [LICENSE](./LICENSE) file for details.

## 💰 Commercial Use

EmberEye is fully available for commercial use under the MIT license. For enterprise support, custom integrations, or premium features:
- 📧 Contact: [enterprise@embereye.dev](mailto:enterprise@embereye.dev)
- 🏢 GitHub Sponsors: [Support the project](https://github.com/sponsors/ratnaprasad)

## 🐛 Issues & Support

- **Bug Reports**: [GitHub Issues](https://github.com/ratnaprasad/EmberEye/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ratnaprasad/EmberEye/discussions)
- **Documentation**: [Docs Folder](./docs)

## 🙏 Acknowledgments

- YOLOv8 by Ultralytics
- PyQt5 community
- Contributors and testers

## 📬 Stay Updated

- ⭐ Star the repository
- 👁️ Watch for releases
- 💬 Join discussions

---

**Made with ❤️ by the EmberEye Team**

[Website](https://embereye.dev) • [Documentation](./docs) • [Issues](https://github.com/ratnaprasad/EmberEye/issues) • [Discussions](https://github.com/ratnaprasad/EmberEye/discussions)
