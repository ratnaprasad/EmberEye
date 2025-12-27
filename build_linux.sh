#!/bin/bash
# EmberEye v1.0.0-beta - Linux DEB Package Builder
# Run on Ubuntu 20.04+ to create .deb package for distribution

set -e  # Exit on error

echo ""
echo "========================================"
echo "EmberEye v1.0.0-beta - Linux DEB Builder"
echo "========================================"
echo ""

# Check OS
if [[ ! -f /etc/debian_version ]]; then
    echo "ERROR: This script requires Debian/Ubuntu"
    echo "Run on: Ubuntu 20.04+, Debian 11+"
    exit 1
fi

echo "✓ Debian/Ubuntu system detected"
echo ""

# Check Python
python3 --version || {
    echo "ERROR: Python 3 not found"
    echo "Install with: sudo apt-get install python3 python3-venv python3-dev"
    exit 1
}

# Install build tools
echo "[1/6] Installing build tools..."
sudo apt-get update -qq
sudo apt-get install -y -qq ruby ruby-dev build-essential libopencv-dev >dev/null 2>&1
sudo gem install -q fpm

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[2/6] Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "[3/6] Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install -q --upgrade pip setuptools wheel
pip install -q -r requirements.txt
pip install -q PyInstaller

# Build executable
echo "[4/6] Building executable (2-5 minutes)..."
pyinstaller \
    --onefile \
    --name embereye \
    --add-data "embereye/resources:embereye/resources" \
    --add-data "embereye/utils:embereye/utils" \
    --add-data "embereye/config:embereye/config" \
    --hidden-import=torch \
    --hidden-import=ultralytics \
    --hidden-import=cv2 \
    --collect-all=ultralytics \
    --collect-all=torch \
    --collect-all=cv2 \
    --distpath dist \
    --buildpath build \
    main.py

# Create DEB directory structure
echo "[5/6] Creating DEB package structure..."
mkdir -p build_deb/embereye/usr/local/bin
mkdir -p build_deb/embereye/usr/share/applications
mkdir -p build_deb/embereye/usr/share/icons/hicolor/256x256/apps

cp dist/embereye build_deb/embereye/usr/local/bin/
chmod +x build_deb/embereye/usr/local/bin/embereye

# Create .desktop file
cat > build_deb/embereye/usr/share/applications/embereye.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=EmberEye
Comment=Advanced thermal object detection system
Exec=embereye
Icon=embereye
Categories=Science;
Terminal=false
EOF

# Copy icon if exists
if [ -f "logo.png" ]; then
    cp logo.png build_deb/embereye/usr/share/icons/hicolor/256x256/apps/embereye.png
fi

# Create post-install script
cat > build_deb/post_install.sh << 'EOF'
#!/bin/bash
# Update desktop database
update-desktop-database /usr/share/applications 2>/dev/null || true
echo "EmberEye installed successfully!"
echo ""
echo "Run with: embereye"
echo "GPU Support:"
echo "  NVIDIA: Automatically detected if CUDA 12.1+ installed"
echo "  AMD: Install ROCm from https://rocmdocs.amd.com/"
echo ""
EOF

chmod +x build_deb/post_install.sh

# Build DEB
echo "[6/6] Building DEB package..."
fpm -s dir \
    -t deb \
    -n embereye \
    -v 1.0.0~beta \
    -C build_deb/embereye \
    --description "EmberEye - Advanced thermal object detection system" \
    --vendor "EmberEye Team" \
    --url "https://github.com/ratnaprasad/EmberEye" \
    --depends "python3.10 | python3.11 | python3.12" \
    --depends "libopencv-core4.5d | libopencv-core4.8 | libopencv-core4.9" \
    --post-install build_deb/post_install.sh \
    --after-install build_deb/post_install.sh \
    -p dist/

echo ""
echo "========================================"
echo "DEB PACKAGE CREATED"
echo "========================================"
echo ""
echo "Package file: dist/embereye_1.0.0~beta_amd64.deb"
echo "Size: ~800MB"
echo ""
echo "Installation:"
echo "  sudo dpkg -i dist/embereye_1.0.0~beta_amd64.deb"
echo "  sudo apt-get install -f  # Install dependencies if needed"
echo ""
echo "Run: embereye"
echo ""
echo "========================================"
echo ""
