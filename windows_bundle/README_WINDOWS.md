# EmberEye Windows ZIP-Based Build

This guide explains how to use a ZIP-based bundle to build the EmberEye Windows EXE on a Windows machine.

## Prerequisites
- Windows 10/11
- Python 3.11 installed and on PATH (`python --version` shows 3.11.x)
- Internet access to install dependencies
- Optional: Visual C++ Build Tools for compiling native wheels, if needed

## ZIP Bundle Layout
Place all project files in a single folder, including:
- Project root with `main.py`, `EmberEye.spec`, `requirements.txt`
- `stream_config.json` (created if missing)
- Resolver files `ip_loc_map.db` or `ip_loc_map.json` (created if missing)
- `windows_bundle/setup_windows_complete.bat` (this script)

## Build Steps (Windows)
1. Extract the ZIP to a local folder (e.g., `C:\EmberEye`).
2. Open `cmd` and navigate to the extracted folder.
3. Run:
   ```bat
   windows_bundle\setup_windows_complete.bat
   ```
4. On success, the EXE will be in `dist\EmberEye\` or `dist\EmberEye.exe`.

## Running the App
- Double-click the generated EXE or run from `cmd`.
- Logs are created under `logs\`.
- TCP server uses `tcp_port` from `stream_config.json` (default 9001 if file is created).

## Troubleshooting
- "Python not found": Install Python 3.11 and ensure it’s on PATH.
- Build fails on native packages: Install Visual C++ Build Tools (Build Tools for Visual Studio).
- Missing resources: Ensure `EmberEye.spec` includes `stream_config.json`, resolver files, and `logs/` as datas.
- Port conflicts: Edit `stream_config.json` to set a free `tcp_port`.

## Notes
- The script creates `.venv` and installs dependencies isolated from system Python.
- If `EmberEye.spec` is missing, a fallback one-file build from `main.py` is used with required datas.
- For IP→Loc mappings, the resolver persists to `ip_loc_map.db` or `ip_loc_map.json` in the app folder.
