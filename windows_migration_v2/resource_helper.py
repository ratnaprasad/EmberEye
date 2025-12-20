"""
Resource path helper for PyInstaller bundled applications
Handles finding resources whether running from source or as packaged app
"""
import os
import sys
from pathlib import Path

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and PyInstaller.
    
    When running from source: uses current directory
    When packaged: uses PyInstaller's temporary extraction directory
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        result = os.path.join(base_path, relative_path)
        print(f"[RESOURCE] Packaged mode - Looking for {relative_path} at: {result}")
    except Exception:
        base_path = os.path.abspath(".")
        result = os.path.join(base_path, relative_path)
        print(f"[RESOURCE] Source mode - Looking for {relative_path} at: {result}")
    
    print(f"[RESOURCE] File exists: {os.path.exists(result)}")
    return result

def get_writable_path(filename):
    """
    Get writable path for user data files (config, database, etc).
    
    When running from source: uses current directory
    When packaged: uses ~/.embereye directory
    """
    if getattr(sys, 'frozen', False):
        # Running as packaged app - use user home directory
        home = os.path.expanduser('~')
        app_dir = os.path.join(home, '.embereye')
        os.makedirs(app_dir, exist_ok=True)
        result = os.path.join(app_dir, filename)
        print(f"[WRITABLE] Packaged mode - Writable path for {filename}: {result}")
    else:
        # Running from source - use current directory
        result = filename
        print(f"[WRITABLE] Source mode - Writable path for {filename}: {result}")
    
    return result

def copy_bundled_resource(filename, dest_path):
    """
    Copy a bundled resource to a writable location if it doesn't exist.
    Useful for initial setup of config files and databases.
    """
    if not os.path.exists(dest_path):
        bundled_path = get_resource_path(filename)
        if os.path.exists(bundled_path):
            import shutil
            shutil.copy2(bundled_path, dest_path)
            print(f"[COPY] Copied {filename} from {bundled_path} to: {dest_path}")
            return True
        else:
            print(f"[COPY] WARNING: Bundled {filename} not found at {bundled_path}")
    else:
        print(f"[COPY] {filename} already exists at {dest_path}, skipping copy")
    return False
