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


def get_workspace_dir():
    """
    Get the workspace root directory for runtime data (annotations, training_data, logs, etc).
    
    When running from source: uses current directory
    When packaged: uses ~/.embereye/workspace directory
    
    This ensures all runtime folders are in a persistent, writable location.
    """
    if getattr(sys, 'frozen', False):
        # Running as packaged app - use user home directory
        home = os.path.expanduser('~')
        app_dir = os.path.join(home, '.embereye', 'workspace')
        os.makedirs(app_dir, exist_ok=True)
        print(f"[WORKSPACE] Packaged mode - Workspace directory: {app_dir}")
        return app_dir
    else:
        # Running from source - use current directory
        workspace = os.path.abspath(".")
        print(f"[WORKSPACE] Source mode - Workspace directory: {workspace}")
        return workspace


def ensure_runtime_folders():
    """
    Create all necessary runtime folders on app startup.
    Returns the workspace directory path.
    
    Creates:
    - annotations/ - for annotation tool output
    - training_data/ - for training datasets
    - training_data/annotations/ - registered training annotations
    - models/ - for YOLO model weights
    - logs/ - for application logs
    - model_versions/ - for trained model versions
    """
    workspace = get_workspace_dir()
    
    folders = [
        'annotations',
        'training_data',
        os.path.join('training_data', 'annotations'),
        'models',
        'logs',
        'model_versions'
    ]
    
    for folder in folders:
        folder_path = os.path.join(workspace, folder)
        os.makedirs(folder_path, exist_ok=True)
        print(f"[FOLDER] Ensured: {folder_path}")
    
    return workspace


def get_data_path(relative_path):
    """
    Get absolute path for runtime data files (annotations, training data, etc).
    
    Args:
        relative_path: Path relative to workspace root (e.g., 'annotations/video', 'training_data')
    
    Returns:
        Absolute path that's writable in both source and packaged modes
    """
    workspace = get_workspace_dir()
    result = os.path.join(workspace, relative_path)
    return result
