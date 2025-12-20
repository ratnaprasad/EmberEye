"""Build MSI installer using WiX Toolset (Windows only).

Prerequisites:
  1. Build EXE first: python build_windows.py
  2. Install WiX Toolset v3: https://wixtoolset.org/releases/
  3. Ensure candle.exe and light.exe are in PATH

Usage:
  python build_msi.py

Output: EmberEye.msi
"""
import os
import subprocess
import sys
import shutil

WXS_FILE = 'EmberEye.wxs'
HARVESTED_FILE = 'harvested.wxs'
OBJ_DIR = 'obj'
MSI_OUTPUT = 'EmberEye.msi'


def check_wix():
    """Verify WiX toolset installed."""
    try:
        result = subprocess.run(['candle.exe', '-?'], capture_output=True, text=True)
        if result.returncode == 0:
            print("[INFO] WiX Toolset found")
            return True
    except FileNotFoundError:
        pass
    print("[ERROR] WiX Toolset not found. Install from https://wixtoolset.org/releases/")
    print("[ERROR] Ensure candle.exe and light.exe are in PATH")
    return False


def harvest_files():
    """Use heat.exe to auto-generate file list from dist/EmberEye."""
    if not os.path.isdir('dist/EmberEye'):
        print("[ERROR] dist/EmberEye not found. Run 'python build_windows.py' first.")
        sys.exit(1)
    
    print("[HARVEST] Generating file list from dist/EmberEye...")
    cmd = [
        'heat.exe', 'dir', 'dist/EmberEye',
        '-cg', 'HarvestedFiles',
        '-gg', '-sfrag', '-srd',
        '-dr', 'INSTALLFOLDER',
        '-out', HARVESTED_FILE
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[ERROR] File harvesting failed")
        sys.exit(1)
    print(f"[HARVEST] Generated {HARVESTED_FILE}")
    return True


def merge_wxs():
    """Merge harvested files into main WXS (manual step reminder)."""
    print("\n" + "="*60)
    print("MANUAL STEP REQUIRED:")
    print(f"  1. Open {HARVESTED_FILE}")
    print(f"  2. Copy <ComponentGroup Id='HarvestedFiles'> content")
    print(f"  3. Paste into {WXS_FILE} under ProductComponents")
    print(f"  4. Press ENTER when done...")
    print("="*60)
    input()


def build_msi():
    """Compile WXS to MSI."""
    os.makedirs(OBJ_DIR, exist_ok=True)
    
    # Step 1: Compile WXS to WIXOBJ
    print("[BUILD] Compiling WXS...")
    candle_cmd = ['candle.exe', WXS_FILE, '-out', f'{OBJ_DIR}/EmberEye.wixobj']
    result = subprocess.run(candle_cmd)
    if result.returncode != 0:
        print("[ERROR] Compilation failed")
        sys.exit(1)
    
    # Step 2: Link WIXOBJ to MSI
    print("[BUILD] Linking MSI...")
    light_cmd = [
        'light.exe', f'{OBJ_DIR}/EmberEye.wixobj',
        '-out', MSI_OUTPUT,
        '-ext', 'WixUIExtension'
    ]
    result = subprocess.run(light_cmd)
    if result.returncode != 0:
        print("[ERROR] Linking failed")
        sys.exit(1)
    
    if os.path.exists(MSI_OUTPUT):
        size_mb = os.path.getsize(MSI_OUTPUT) / (1024 * 1024)
        print(f"\n[SUCCESS] MSI created: {MSI_OUTPUT} ({size_mb:.1f} MB)")
        print(f"[TEST] Install with: msiexec /i {MSI_OUTPUT} /l*v install.log")
        return True
    return False


def main():
    if not check_wix():
        sys.exit(1)
    
    print("\n=== EmberEye MSI Builder ===\n")
    
    # Step 1: Harvest files
    if not harvest_files():
        sys.exit(1)
    
    # Step 2: Manual merge (or automate with XML parsing)
    print("\n[INFO] For automated merge, enhance this script to parse/inject XML")
    print("[INFO] Skipping manual merge for now, assuming WXS is pre-configured")
    # merge_wxs()  # Uncomment for manual workflow
    
    # Step 3: Build MSI
    if build_msi():
        print("\n=== Build Complete ===")
        print(f"Distribute: {MSI_OUTPUT}")
    else:
        print("\n=== Build Failed ===")
        sys.exit(1)


if __name__ == '__main__':
    main()
