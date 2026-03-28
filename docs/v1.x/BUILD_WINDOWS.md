# EmberEye Windows Migration & Packaging Guide

## Overview
This guide finalizes migration of EmberEye to Windows, producing a distributable ZIP containing `EmberEye.exe`, resources, configuration defaults, and logs folder structure.

## 1. Prerequisites (Local Windows Build)
- Windows 10/11 (64-bit)
- Python 3.11 (recommended)
- Visual C++ Build Tools (for bcrypt if wheel fallback fails)
- PowerShell

## 2. Clone Repository
```powershell
git clone https://your-repo/EmberEye.git
cd EmberEye
```

## 3. Create Virtual Environment
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 4. Install Dependencies
```powershell
pip install -r requirements.txt psutil pywin32
```
If `bcrypt` fails to build:
```powershell
pip install bcrypt --only-binary=:all:
```

## 5. Build Executable
Use provided spec:
```powershell
pyinstaller --clean EmberEye_win.spec
```
Or helper script:
```powershell
python build_windows.py
```

## 6. Result
- Output folder: `dist/EmberEye/`
- Main binary: `EmberEye.exe`
- Resources included: `logo.png`, `stream_config.json`, logs/, images/
- Writable user data stored under: `%USERPROFILE%\.embereye` (see `resource_helper.py`)

## 7. Package ZIP
```powershell
Compress-Archive -Path dist/EmberEye/* -DestinationPath EmberEye_Windows.zip -Force
```
Distribute `EmberEye_Windows.zip` to end users.

## 8. First Run Behavior
- Creates `%USERPROFILE%\.embereye` if missing
- Copies bundled `users.db` / config if using resource copy routines
- Launches GUI (PyQt5) without console (change `console=True` in spec to debug)

## 9. Automatic CI Build (GitHub Actions)
Workflow file: `.github/workflows/windows-build.yml` builds and publishes artifact automatically.
Trigger manually:
```text
GitHub → Actions → Windows Build → Run workflow
```
Retrieval:
- Download `EmberEye_Windows.zip` from workflow artifacts

## 10. Common Windows Issues
| Issue | Cause | Fix |
|-------|-------|-----|
| Missing `EmberEye.exe` | PyInstaller failure | Re-run with `--log-level DEBUG` |
| Bcrypt build error | Lacks compiled wheel | Install VC Build Tools / use binary wheel |
| Blank Grafana tab | WebEngine missing codecs | Ensure `PyQtWebEngine` installed |
| Antivirus blocks EXE | New unsigned binary | Submit for whitelisting / sign code |
| Missing DLL (Qt) | PATH interference | Ensure venv active during build |

## 11. Optional: Code Signing (Enterprise)
- Generate code signing certificate (EV recommended)
- Sign after build:
```powershell
signtool sign /tr http://timestamp.digicert.com /fd SHA256 /a dist\EmberEye\EmberEye.exe
```

## 12. Unattended Deployment
```powershell
Expand-Archive -Path EmberEye_Windows.zip -DestinationPath C:\EmberEye -Force
C:\EmberEye\EmberEye.exe
```
Add Scheduled Task (optional):
```powershell
schtasks /Create /SC ONSTART /TN EmberEye /TR "C:\EmberEye\EmberEye.exe" /RL HIGHEST
```

## 13. Updating
```powershell
# Preserve user data (~/.embereye)
Remove-Item C:\EmberEye -Recurse -Force
Expand-Archive -Path EmberEye_Windows.zip -DestinationPath C:\EmberEye -Force
```

## 14. Debug Build
Edit `EmberEye_win.spec` → set `console=True` and rebuild for stdout visibility.

## 15. Performance Notes (Windows)
- Prefer `opencv-python` headless if GUI bounds smaller
- Ensure GPU drivers if adding accelerated inference later
- Use `psutil` for future watchdog metrics

## 16. Folder Layout After Build
```
dist/EmberEye/
  EmberEye.exe
  logo.png
  images/...
  stream_config.json
  logs/ (empty initially)
  PyQt5/*
  (DLLs, Python libs)
```

## 17. Validation Checklist
- [ ] EXE launches without console errors
- [ ] Grafana tab loads (if Grafana reachable)
- [ ] TCP server starts (verify port in status bar)
- [ ] Metrics endpoint reachable (`http://localhost:9090/metrics` if started)
- [ ] Config persisted in `%USERPROFILE%\.embereye`

## 18. Future Enhancements
- Add MSI packaging (WiX Toolset)
- Integrate Sentry for crash telemetry
- Add auto-updater (WinSparkle or custom)

---
**Done. EmberEye Windows migration pipeline ready.**
