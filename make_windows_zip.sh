#!/bin/bash
# EmberEye Windows ZIP Packaging Script
# Creates a portable ZIP bundle ready for transfer to Windows machine

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Define output
OUTPUT_DIR="EmberEye_Windows_Bundle"
ZIP_NAME="EmberEye_Windows_Bundle_$(date +%Y%m%d_%H%M%S).zip"

echo "================================================"
echo "EmberEye Windows ZIP Packager"
echo "================================================"
echo ""

# Clean previous bundle
if [ -d "$OUTPUT_DIR" ]; then
  echo "Cleaning previous bundle directory..."
  rm -rf "$OUTPUT_DIR"
fi

# Create output directory
echo "Creating bundle directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy essential Python source files
echo "Copying Python source files..."
cp -v *.py "$OUTPUT_DIR/" 2>/dev/null || true

# Copy spec file
if [ -f "EmberEye.spec" ]; then
  echo "Copying PyInstaller spec..."
  cp -v EmberEye.spec "$OUTPUT_DIR/"
fi

# Copy requirements
if [ -f "requirements.txt" ]; then
  echo "Copying requirements.txt..."
  cp -v requirements.txt "$OUTPUT_DIR/"
fi

# Copy config files (create defaults if missing)
echo "Copying/creating configuration files..."
if [ -f "stream_config.json" ]; then
  cp -v stream_config.json "$OUTPUT_DIR/"
else
  echo '{"groups":["Default"],"streams":[],"tcp_port":9001}' > "$OUTPUT_DIR/stream_config.json"
  echo "  Created default stream_config.json"
fi

# Copy resolver files (create empty if missing)
if [ -f "ip_loc_map.json" ]; then
  cp -v ip_loc_map.json "$OUTPUT_DIR/"
else
  echo '{}' > "$OUTPUT_DIR/ip_loc_map.json"
  echo "  Created empty ip_loc_map.json"
fi

if [ -f "ip_loc_map.db" ]; then
  cp -v ip_loc_map.db "$OUTPUT_DIR/"
fi

# Copy resources
echo "Copying resource files..."
if [ -f "logo.png" ]; then
  cp -v logo.png "$OUTPUT_DIR/"
fi

if [ -f "logo.icns" ]; then
  cp -v logo.icns "$OUTPUT_DIR/"
fi

if [ -d "images" ]; then
  echo "Copying images directory..."
  cp -r images "$OUTPUT_DIR/"
fi

# Create logs directory
mkdir -p "$OUTPUT_DIR/logs"
echo "Created logs directory"

# Copy Windows bundle files
if [ -d "windows_bundle" ]; then
  echo "Copying Windows bundle directory..."
  cp -r windows_bundle "$OUTPUT_DIR/"
else
  echo "WARNING: windows_bundle directory not found"
fi

# Copy documentation
echo "Copying documentation..."
if [ -f "README.md" ]; then
  cp -v README.md "$OUTPUT_DIR/"
fi

if [ -f "TEST_COVERAGE_SUMMARY.md" ]; then
  cp -v TEST_COVERAGE_SUMMARY.md "$OUTPUT_DIR/"
fi

# Create a quick start guide for Windows
cat > "$OUTPUT_DIR/QUICK_START_WINDOWS.txt" << 'EOF'
EmberEye Windows Quick Start
============================

Prerequisites:
- Windows 10/11
- Python 3.11 installed and on PATH
- Internet connection for downloading dependencies

Build Steps:
1. Extract this ZIP to a local folder (e.g., C:\EmberEye)
2. Open Command Prompt (cmd)
3. Navigate to the folder: cd C:\EmberEye
4. Run the build script: windows_bundle\setup_windows_complete.bat
5. Wait for the build to complete (may take 5-10 minutes)
6. Find the EXE in: dist\EmberEye\ or dist\EmberEye.exe

Running the App:
- Double-click EmberEye.exe or run from cmd
- Default TCP server port: 9001 (configurable in stream_config.json)
- Logs are created in logs\ directory
- User database: users.db (auto-created on first run)
- Default credentials: admin / admin (change on first login)

Troubleshooting:
- "Python not found": Install Python 3.11 and ensure it's on PATH
- Build fails: Install Visual C++ Build Tools if native packages fail
- Port conflicts: Edit stream_config.json to change tcp_port
- Missing resources: Check EmberEye.spec includes all required datas

For detailed instructions, see windows_bundle\README_WINDOWS.md
EOF

echo "Created QUICK_START_WINDOWS.txt"

# Create bundle info file
cat > "$OUTPUT_DIR/BUNDLE_INFO.txt" << EOF
EmberEye Windows Bundle
=======================
Created: $(date)
Source: $(hostname)
Bundle contents: Python sources, spec file, resources, Windows build scripts

Files included:
- All .py source files
- EmberEye.spec (PyInstaller specification)
- requirements.txt (Python dependencies)
- stream_config.json (application configuration)
- ip_loc_map.json (IP to location resolver)
- logo.png, images/ (UI resources)
- logs/ (log directory)
- windows_bundle/ (Windows build scripts and documentation)

To build on Windows:
1. Extract to local folder
2. Run: windows_bundle\setup_windows_complete.bat
3. Find EXE in dist\ directory

For issues or questions, see windows_bundle\README_WINDOWS.md
EOF

echo "Created BUNDLE_INFO.txt"

# Create the ZIP
echo ""
echo "Creating ZIP archive: $ZIP_NAME"
if command -v zip &> /dev/null; then
  zip -r "$ZIP_NAME" "$OUTPUT_DIR" -x "*.pyc" -x "*__pycache__*" -x "*.git*" -x "*build/*" -x "*dist/*" -x "*.venv/*"
else
  echo "WARNING: 'zip' command not found, trying tar..."
  tar -czf "${ZIP_NAME%.zip}.tar.gz" "$OUTPUT_DIR" --exclude="*.pyc" --exclude="*__pycache__*" --exclude="*.git*" --exclude="*build/*" --exclude="*dist/*" --exclude="*.venv/*"
  ZIP_NAME="${ZIP_NAME%.zip}.tar.gz"
fi

# Calculate size
if [ -f "$ZIP_NAME" ]; then
  ZIP_SIZE=$(du -h "$ZIP_NAME" | cut -f1)
  echo ""
  echo "================================================"
  echo "SUCCESS!"
  echo "================================================"
  echo "Bundle created: $ZIP_NAME"
  echo "Size: $ZIP_SIZE"
  echo ""
  echo "Next steps:"
  echo "1. Copy $ZIP_NAME to your Windows machine"
  echo "2. Extract the archive"
  echo "3. Follow instructions in QUICK_START_WINDOWS.txt"
  echo ""
  echo "Or run the build directly:"
  echo "  cd EmberEye_Windows_Bundle"
  echo "  windows_bundle\\setup_windows_complete.bat"
  echo "================================================"
else
  echo "ERROR: Failed to create ZIP archive"
  exit 1
fi

# Optional: cleanup bundle directory
read -p "Delete temporary bundle directory? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  rm -rf "$OUTPUT_DIR"
  echo "Cleaned up temporary directory"
fi
