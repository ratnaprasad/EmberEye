"""Auto-updater stub for EmberEye Windows distribution.

Checks GitHub releases for newer versions and prompts user to download.
Minimal implementation without automatic download (user downloads manually).

Future enhancements:
- Add background download with progress bar
- Integrate WinSparkle for native Windows updates
- Add signature verification for downloaded files
"""
import os
import sys
import json
import urllib.request
import urllib.error
from packaging import version as pkg_version

# Current version (update on each release)
CURRENT_VERSION = "1.0.0-beta"

# GitHub release API endpoint
GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_OWNER = "your-org"  # TODO: Update with actual GitHub org/user
GITHUB_REPO = "EmberEye"   # TODO: Update with actual repo name


def get_latest_version():
    """Fetch latest release version from GitHub."""
    url = GITHUB_API.format(owner=GITHUB_OWNER, repo=GITHUB_REPO)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EmberEye-Updater'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            tag = data.get('tag_name', '').lstrip('v')
            download_url = None
            for asset in data.get('assets', []):
                if asset['name'].endswith('.zip') and 'Windows' in asset['name']:
                    download_url = asset['browser_download_url']
                    break
            return tag, download_url
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"[UPDATE] Version check failed: {e}")
        return None, None


def check_for_updates(silent=False):
    """Check if newer version available. Returns (needs_update, latest_version, download_url)."""
    if not silent:
        print(f"[UPDATE] Current version: {CURRENT_VERSION}")
        print(f"[UPDATE] Checking for updates...")
    
    latest, download_url = get_latest_version()
    if not latest:
        if not silent:
            print("[UPDATE] Could not check for updates (offline or API error)")
        return False, None, None
    
    try:
        needs_update = pkg_version.parse(latest) > pkg_version.parse(CURRENT_VERSION)
    except Exception as e:
        print(f"[UPDATE] Version comparison error: {e}")
        return False, None, None
    
    if needs_update:
        if not silent:
            print(f"[UPDATE] New version available: {latest}")
            print(f"[UPDATE] Download: {download_url}")
        return True, latest, download_url
    else:
        if not silent:
            print(f"[UPDATE] You have the latest version ({CURRENT_VERSION})")
        return False, None, None


def prompt_update(latest_version, download_url):
    """Show update notification with download link."""
    try:
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Update Available")
        msg.setText(f"EmberEye {latest_version} is available!")
        msg.setInformativeText(
            f"You are currently running version {CURRENT_VERSION}.\n\n"
            f"Download the latest version from:\n{download_url}"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        msg.exec_()
    except ImportError:
        # Fallback to console
        print(f"\n{'='*60}")
        print(f"UPDATE AVAILABLE: EmberEye {latest_version}")
        print(f"Current version: {CURRENT_VERSION}")
        print(f"Download: {download_url}")
        print(f"{'='*60}\n")


def auto_check_updates_background():
    """Background thread-safe update check (call on app startup)."""
    import threading
    
    def check():
        needs_update, latest, url = check_for_updates(silent=True)
        if needs_update:
            print(f"[UPDATE] Background check: {latest} available")
            # Store in config or trigger notification
            try:
                with open('.update_available', 'w') as f:
                    json.dump({'version': latest, 'url': url}, f)
            except Exception:
                pass
    
    thread = threading.Thread(target=check, daemon=True)
    thread.start()


if __name__ == '__main__':
    # Manual check
    needs_update, latest, url = check_for_updates()
    if needs_update:
        prompt_update(latest, url)
