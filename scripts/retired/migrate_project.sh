#!/bin/bash

# EmberEye Project Migration Script
# This script prepares the project for migration to another system

set -e  # Exit on error

PROJECT_NAME="EmberEye"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MIGRATION_DIR="${PROJECT_NAME}_migration_${TIMESTAMP}"
EXCLUDE_PATTERNS="--exclude=.venv --exclude=__pycache__ --exclude=*.pyc --exclude=.git --exclude=build --exclude=dist --exclude=*.log --exclude=users.db --exclude=.DS_Store --exclude=logo.iconset"

echo "=================================="
echo "EmberEye Project Migration Script"
echo "=================================="
echo ""

# Create migration directory
echo "Creating migration package..."
mkdir -p "$MIGRATION_DIR"

# Copy project files
echo "Copying project files..."
rsync -av $EXCLUDE_PATTERNS \
    --exclude="$MIGRATION_DIR" \
    ./ "$MIGRATION_DIR/"

# Create requirements.txt with exact versions
echo "Generating requirements.txt..."
pip freeze | grep -E "PyQt5|opencv-python|numpy|bcrypt|websockets|psutil|onvif-zeep|wsdiscovery" > "$MIGRATION_DIR/requirements_exact.txt"

# Create setup instructions
cat > "$MIGRATION_DIR/MIGRATION_GUIDE.md" << 'EOF'
# EmberEye Migration Guide

## System Requirements
- macOS 11.0 or later (for packaged app)
- Python 3.9+ (for development)
- 4GB RAM minimum
- Camera/RTSP stream access permissions

## Migration Steps

### Option 1: Run Packaged App (Recommended)
1. Copy the `dist/EmberEye.app` to the Applications folder
2. Right-click and select "Open" (first time only to bypass Gatekeeper)
3. Grant camera permissions when prompted

### Option 2: Development Setup
1. Install Python 3.9 or later
2. Create virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate  # On Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python main.py
   ```

## Default Credentials
- **Admin**: admin / password
- **User 1**: ratna / ratna
- **User 2**: s3micro / s3micro

## Configuration Files
- `stream_config.json` - Camera stream configuration
- `users.db` - User database (auto-created on first run)

## Building Packaged App
To rebuild the macOS app bundle:
```bash
# Clean previous builds
rm -rf build dist

# Build with PyInstaller
pyinstaller EmberEye.spec
```

The app will be created at `dist/EmberEye.app`

## Important Notes
- Database (`users.db`) is stored in `~/.embereye/` for packaged app
- Stream config is stored in `~/.embereye/` for packaged app
- First run may take longer due to font cache building
- TCP server runs on port 9001 by default (configurable)

## Troubleshooting

### App won't open on macOS
```bash
# Remove quarantine attribute
xattr -cr /Applications/EmberEye.app
```

### Permission errors
Grant camera permissions in System Preferences > Security & Privacy > Camera

### TCP port conflicts
Change port via Settings menu > TCP Server Port

### Missing icon
Icon file is included as `logo.icns` - rebuild if needed:
```bash
./create_icon.sh
```

## File Structure
```
EmberEye/
├── main.py                 # Application entry point
├── main_window.py          # Main window UI
├── ee_loginwindow.py       # Login interface
├── video_widget.py         # Video display widget
├── video_worker.py         # Video capture worker
├── stream_config.py        # Stream configuration
├── database_manager.py     # User database
├── sensor_fusion.py        # Sensor data fusion
├── tcp_sensor_server.py    # TCP sensor server
├── EmberEye.spec          # PyInstaller spec file
├── requirements.txt        # Python dependencies
└── images/                 # UI resources
```

## Support
For issues or questions, contact the development team.
EOF

# Create icon generation script
cat > "$MIGRATION_DIR/create_icon.sh" << 'EOF'
#!/bin/bash
# Generate macOS icon from logo.png

if [ ! -f "logo.png" ]; then
    echo "Error: logo.png not found"
    exit 1
fi

echo "Creating icon..."
mkdir -p logo.iconset
sips -z 16 16 logo.png --out logo.iconset/icon_16x16.png
sips -z 32 32 logo.png --out logo.iconset/icon_16x16@2x.png
sips -z 32 32 logo.png --out logo.iconset/icon_32x32.png
sips -z 64 64 logo.png --out logo.iconset/icon_32x32@2x.png
sips -z 128 128 logo.png --out logo.iconset/icon_128x128.png
sips -z 256 256 logo.png --out logo.iconset/icon_128x128@2x.png
sips -z 256 256 logo.png --out logo.iconset/icon_256x256.png
sips -z 512 512 logo.png --out logo.iconset/icon_256x256@2x.png
sips -z 512 512 logo.png --out logo.iconset/icon_512x512.png
sips -z 1024 1024 logo.png --out logo.iconset/icon_512x512@2x.png
iconutil -c icns logo.iconset
rm -rf logo.iconset
echo "Icon created: logo.icns"
EOF
chmod +x "$MIGRATION_DIR/create_icon.sh"

# Create quick start script
cat > "$MIGRATION_DIR/quick_start.sh" << 'EOF'
#!/bin/bash
# Quick start script for development

echo "EmberEye Quick Start"
echo "==================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
if [ ! -f ".venv/installed" ]; then
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    touch .venv/installed
fi

# Run app
echo "Starting EmberEye..."
python main.py
EOF
chmod +x "$MIGRATION_DIR/quick_start.sh"

# Create README
cat > "$MIGRATION_DIR/README.md" << 'EOF'
# EmberEye - Fire Detection and Monitoring System

A comprehensive fire detection and monitoring system using computer vision, thermal imaging, and sensor fusion.

## Features
- Real-time RTSP stream monitoring
- Fire and smoke detection using OpenCV
- Multi-sensor fusion (thermal, gas, flame)
- TCP sensor server for external sensors
- ONVIF camera discovery
- Baseline thermal management
- User authentication and access control

## Quick Start

### Packaged App
1. Open `dist/EmberEye.app`
2. Login with default credentials (see MIGRATION_GUIDE.md)

### Development
```bash
./quick_start.sh
```

## Documentation
See `MIGRATION_GUIDE.md` for detailed setup instructions.

## Version
1.0.0
EOF

# Create version info file
cat > "$MIGRATION_DIR/VERSION.txt" << EOF
EmberEye v1.0.0
Build Date: $(date)
Migration Package: $TIMESTAMP

Features:
- RTSP stream monitoring
- Fire/smoke detection
- Sensor fusion
- TCP sensor server (port 9001)
- ONVIF camera discovery
- User authentication

System Requirements:
- macOS 11.0+
- Python 3.9+ (development)
- 4GB RAM minimum
EOF

# Copy dist folder if it exists
if [ -d "dist/EmberEye.app" ]; then
    echo "Copying packaged app..."
    mkdir -p "$MIGRATION_DIR/dist"
    cp -r dist/EmberEye.app "$MIGRATION_DIR/dist/"
    echo "✓ Packaged app included"
else
    echo "⚠ No packaged app found. Run 'pyinstaller EmberEye.spec' to create it."
fi

# Create archive
echo ""
echo "Creating migration archive..."
tar -czf "${MIGRATION_DIR}.tar.gz" "$MIGRATION_DIR"

# Calculate size
SIZE=$(du -h "${MIGRATION_DIR}.tar.gz" | cut -f1)

echo ""
echo "=================================="
echo "Migration package created!"
echo "=================================="
echo ""
echo "Archive: ${MIGRATION_DIR}.tar.gz"
echo "Size: $SIZE"
echo ""
echo "Contents:"
echo "  ✓ Source code"
echo "  ✓ Configuration files"
echo "  ✓ Migration guide"
echo "  ✓ Setup scripts"
if [ -d "dist/EmberEye.app" ]; then
    echo "  ✓ Packaged application"
fi
echo ""
echo "To migrate to another system:"
echo "1. Copy ${MIGRATION_DIR}.tar.gz to the target system"
echo "2. Extract: tar -xzf ${MIGRATION_DIR}.tar.gz"
echo "3. Follow MIGRATION_GUIDE.md instructions"
echo ""
echo "Cleanup:"
echo "  rm -rf $MIGRATION_DIR  # Remove uncompressed folder"
echo ""
