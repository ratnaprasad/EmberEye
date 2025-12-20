#!/usr/bin/env python3
"""
EmberEye Multi-Platform Build Script
Builds executables for Windows (.exe), Linux, and macOS
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

def check_pyinstaller():
    """Ensure PyInstaller is installed"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installed")

def prepare_database():
    """Ensure users.db exists with all three users"""
    import sqlite3
    from passlib.hash import bcrypt
    
    db_path = Path('users.db')
    print(f"\n📦 Preparing database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            dob TEXT,
            secret_question1 TEXT,
            secret_answer1 TEXT,
            secret_question2 TEXT,
            secret_answer2 TEXT,
            secret_question3 TEXT,
            secret_answer3 TEXT,
            failed_attempts INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0
        )
    ''')
    
    # Create license table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license (
            key TEXT PRIMARY KEY,
            used INTEGER DEFAULT 0
        )
    ''')
    
    users = [
        ('admin', 'password', 'Admin', 'User'),
        ('ratna', 'ratna', 'Ratna', 'Prasad'),
        ('s3micro', 's3micro', 'S3', 'Micro')
    ]
    
    for username, password, first_name, last_name in users:
        password_hash = bcrypt.hash(password)
        cursor.execute('SELECT username FROM users WHERE username = ?', (username,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (username, password_hash, first_name, last_name, failed_attempts, locked)
                VALUES (?, ?, ?, ?, 0, 0)
            ''', (username, password_hash, first_name, last_name))
            print(f"  ✓ Created user: {username}")
        else:
            cursor.execute('''
                UPDATE users SET password_hash = ?, first_name = ?, last_name = ?, failed_attempts = 0, locked = 0
                WHERE username = ?
            ''', (password_hash, first_name, last_name, username))
            print(f"  ✓ Updated user: {username}")
    
    conn.commit()
    conn.close()
    print("✓ Database ready with users: admin, ratna, s3micro")

def create_spec_file():
    """Create PyInstaller spec file with all resources"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('logo.png', '.'),
        ('users.db', '.'),
        ('stream_config.json', '.'),
    ],
    hiddenimports=[
        'passlib.handlers.bcrypt',
        'passlib.hash',
        'bcrypt',
        'cv2',
        'numpy',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'websockets',
        'asyncio',
        'resource_helper',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Use COLLECT for macOS (onedir) to properly include data files
if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='EmberEye',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='EmberEye',
    )
    
    app = BUNDLE(
        coll,
        name='EmberEye.app',
        icon='logo.png',
        bundle_identifier='com.s3micro.embereye',
        info_plist={
            'CFBundleName': 'EmberEye',
            'CFBundleDisplayName': 'EmberEye',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': 'True',
            'NSCameraUsageDescription': 'EmberEye needs camera access to capture live video for fire, smoke, and thermal hazard detection.',
        },
    )
else:
    # Onefile for Windows/Linux
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='EmberEye',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
'''
    
    with open('EmberEye_installer.spec', 'w') as f:
        f.write(spec_content)
    print("✓ Created PyInstaller spec file")

def ensure_resources():
    """Ensure all required resource files exist"""
    print("\n📦 Checking resources...")
    
    # Check database
    if not Path('users.db').exists():
        print("  ✗ users.db not found, will be created by prepare_database()")
    else:
        print("  ✓ users.db exists")
    
    # Check logo
    if not Path('logo.png').exists():
        print("  ✗ logo.png not found, creating it...")
        from PIL import Image, ImageDraw
        import math
        
        size = 200
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        colors = ['#FF4500', '#FF6347', '#FF7F50', '#FFA500', '#FFD700']
        center_x, center_y = size // 2, size // 2
        
        draw.ellipse([60, 80, 140, 160], fill='#FF6347', outline='#FF4500', width=3)
        draw.ellipse([80, 50, 120, 90], fill='#FF7F50', outline='#FF4500', width=2)
        draw.ellipse([92, 62, 98, 68], fill='#FFD700')
        draw.ellipse([102, 62, 108, 68], fill='#FFD700')
        draw.polygon([(100, 75), (90, 85), (110, 85)], fill='#FFA500', outline='#FF4500')
        
        wing_left = [(60, 100), (20, 80), (30, 120), (60, 130)]
        draw.polygon(wing_left, fill='#FF7F50', outline='#FF4500', width=2)
        wing_right = [(140, 100), (180, 80), (170, 120), (140, 130)]
        draw.polygon(wing_right, fill='#FF7F50', outline='#FF4500', width=2)
        
        tail1 = [(100, 160), (80, 190), (90, 185)]
        tail2 = [(100, 160), (100, 195), (100, 190)]
        tail3 = [(100, 160), (120, 190), (110, 185)]
        draw.polygon(tail1, fill='#FFA500', outline='#FF4500', width=2)
        draw.polygon(tail2, fill='#FFD700', outline='#FF4500', width=2)
        draw.polygon(tail3, fill='#FFA500', outline='#FF4500', width=2)
        
        for i in range(8):
            angle = i * (360 / 8)
            rad = math.radians(angle)
            x = center_x + int(70 * math.cos(rad))
            y = center_y + int(70 * math.sin(rad))
            flame_color = colors[i % len(colors)]
            draw.ellipse([x-8, y-8, x+8, y+8], fill=flame_color + '80')
        
        img.save('logo.png', 'PNG')
        print("  ✓ Created logo.png")
    else:
        print("  ✓ logo.png exists")
    
    # Check stream config
    if not Path('stream_config.json').exists():
        print("  ⚠ stream_config.json not found, will be created on first run")
    else:
        print("  ✓ stream_config.json exists")

def build_executable():
    """Build the executable using PyInstaller"""
    print("\n🔨 Building EmberEye executable...")
    print(f"Platform: {sys.platform}")
    
    # Clean previous builds
    for path in ['build', 'dist']:
        if Path(path).exists():
            shutil.rmtree(path)
            print(f"  ✓ Cleaned {path}/")
    
    # Build
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        'EmberEye_installer.spec'
    ]
    
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("✗ Build failed!")
        print(result.stderr)
        return False
    
    print("✓ Build completed successfully!")
    return True

def create_readme():
    """Create README for distribution"""
    readme = """# EmberEye Fire Detection System

## Pre-configured Users

The application comes with three pre-configured users:

1. **admin** / password
   - Administrator account for system setup
   
2. **ratna** / ratna
   - Standard user account
   
3. **s3micro** / s3micro
   - Demo user account

## Installation

### Windows
- Run `EmberEye.exe`
- No installation required

### Linux (Ubuntu/Debian)
- Make executable: `chmod +x EmberEye`
- Run: `./EmberEye`

### macOS
- Open `EmberEye.app`
- If blocked by security, go to System Preferences > Security & Privacy
- Click "Open Anyway"

## Quick Start

1. Launch EmberEye
2. Login with any of the accounts above
3. Configure camera streams in Settings
4. Start monitoring

## Support

For issues or questions, contact S3 Micro Support.
"""
    
    dist_path = Path('dist')
    if dist_path.exists():
        with open(dist_path / 'README.txt', 'w') as f:
            f.write(readme)
        print("✓ Created README.txt in dist/")

def main():
    """Main build process"""
    print("=" * 60)
    print("EmberEye Multi-Platform Builder")
    print("=" * 60)
    
    # Step 1: Check dependencies
    check_pyinstaller()
    
    # Step 2: Prepare database with all users
    prepare_database()
    
    # Step 3: Ensure resources exist
    ensure_resources()
    
    # Step 4: Create spec file
    create_spec_file()
    
    # Step 5: Build executable
    if build_executable():
        # Step 6: Create documentation
        create_readme()
        
        print("\n" + "=" * 60)
        print("✅ Build Complete!")
        print("=" * 60)
        print(f"\nOutput location: {Path('dist').absolute()}")
        
        if sys.platform == 'darwin':
            print("\nmacOS: EmberEye.app")
        elif sys.platform == 'win32':
            print("\nWindows: EmberEye.exe")
        else:
            print("\nLinux: EmberEye")
        
        print("\nAll users included:")
        print("  • admin/password")
        print("  • ratna/ratna")
        print("  • s3micro/s3micro")
        print("\n💡 To create installers:")
        print("  Windows: Use Inno Setup or NSIS with the .exe")
        print("  macOS: Use 'create-dmg' to create .dmg")
        print("  Linux: Use 'fpm' to create .deb or .rpm")
    else:
        print("\n❌ Build failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
