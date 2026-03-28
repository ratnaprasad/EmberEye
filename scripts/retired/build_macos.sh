#!/bin/bash
# EmberEye v1.0.0-beta - macOS App Bundle Builder
# Run on macOS to create .dmg for distribution

set -e

echo ""
echo "========================================"
echo "EmberEye v1.0.0-beta - macOS Builder"
echo "========================================"
echo ""

# Check macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "ERROR: This script requires macOS"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found"
    echo "Install from: https://www.python.org/downloads/macos/"
    exit 1
fi

python3 --version

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[1/6] Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "[2/6] Activating virtual environment..."
source .venv/bin/activate

echo "[3/6] Installing dependencies..."
pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q
pip install PyInstaller -q

# For macOS, ensure PyTorch is installed correctly
echo "[4/6] Installing PyTorch for macOS..."
pip install torch torchvision torchaudio -q

# Build app bundle
echo "[5/6] Building .app bundle (2-5 minutes)..."
pyinstaller \
    --onefile \
    --windowed \
    --name "EmberEye" \
    --icon "logo.icns" \
    --osx-bundle-identifier "com.embereye.app" \
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

# Optional: Sign app (for Notarization)
echo "[6/6] Finalizing app bundle..."
if [ -d "dist/EmberEye.app" ]; then
    # Remove quarantine attribute if present
    xattr -d com.apple.quarantine dist/EmberEye.app 2>/dev/null || true
    
    echo "Creating DMG..."
    hdiutil create \
        -volname "EmberEye" \
        -srcfolder dist/EmberEye.app \
        -ov -format UDZO \
        dist/EmberEye-1.0.0-beta.dmg
    
    echo ""
    echo "========================================"
    echo "macOS APP BUNDLE CREATED"
    echo "========================================"
    echo ""
    echo "DMG file: dist/EmberEye-1.0.0-beta.dmg"
    echo "Size: ~600MB"
    echo ""
    echo "Distribution:"
    echo "1. Users download EmberEye-1.0.0-beta.dmg"
    echo "2. Double-click to mount"
    echo "3. Drag EmberEye.app to Applications"
    echo "4. Launch from Applications"
    echo ""
    echo "GPU Support:"
    echo "  M1/M2/M3: Metal GPU (automatic)"
    echo "  Intel: CPU mode (GPU requires NVIDIA driver)"
    echo ""
    echo "========================================"
    echo ""
else
    echo "ERROR: Build failed"
    exit 1
fi
