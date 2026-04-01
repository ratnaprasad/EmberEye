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
    
    When running from source: searches current directory and parent directories
    When packaged: uses PyInstaller's temporary extraction directory
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        result = os.path.join(base_path, relative_path)
        print(f"[RESOURCE] Packaged mode - Looking for {relative_path} at: {result}")
        print(f"[RESOURCE] File exists: {os.path.exists(result)}")
        return result
    except Exception:
        # Source mode: search current directory and up to 3 parent directories
        current = Path(os.path.abspath("."))
        search_paths = [current] + list(current.parents)[:3]
        
        for base_path in search_paths:
            result = os.path.join(base_path, relative_path)
            if os.path.exists(result):
                print(f"[RESOURCE] Source mode - Found {relative_path} at: {result}")
                return result
        
        # Fallback: return path from current directory even if not found
        result = os.path.join(current, relative_path)
        print(f"[RESOURCE] Source mode - {relative_path} not found, using: {result}")
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


def get_debug_log_paths(filename):
    """Return visible candidate paths for runtime debug logs."""
    paths = []

    primary_path = get_writable_path(filename)
    if primary_path:
        paths.append(primary_path)

    try:
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if exe_dir:
                paths.append(os.path.join(exe_dir, filename))
        else:
            paths.append(os.path.abspath(filename))
    except Exception:
        pass

    unique_paths = []
    seen = set()
    for path in paths:
        norm_path = os.path.normcase(os.path.abspath(path))
        if norm_path in seen:
            continue
        seen.add(norm_path)
        unique_paths.append(path)

    return unique_paths


def append_debug_log(filename, text):
    """Append diagnostic text to all visible debug log locations."""
    written_paths = []
    for log_path in get_debug_log_paths(filename):
        try:
            parent_dir = os.path.dirname(log_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write(text)
            written_paths.append(log_path)
        except Exception:
            continue
    return written_paths

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
        os.path.join('annotations', 'qcapproved'),
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
