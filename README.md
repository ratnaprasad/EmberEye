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

## 📖 Documentation

- [Installation Guide](./docs/INSTALLATION.md)
- [User Guide](./docs/USER_GUIDE.md)
- [API Reference](./docs/API.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [Thermal Camera Integration](./docs/CAMERA_INTEGRATION.md)

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
