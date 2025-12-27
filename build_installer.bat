@echo off
REM EmberEye v1.0.0-beta - NSIS Installer Builder
REM Creates professional Windows installer (.exe setup file)

echo.
echo ========================================
echo EmberEye - Windows Installer Builder
echo ========================================
echo.

REM Check if NSIS is installed
where makensis >nul 2>&1
if errorlevel 1 (
    echo ERROR: NSIS not found in PATH
    echo.
    echo To create installers, you need NSIS:
    echo Download: https://nsis.sourceforge.io/Download
    echo Install and add to PATH, or run from NSIS folder
    echo.
    echo For now, you can distribute: dist\EmberEye.exe directly
    exit /b 1
)

echo ✓ NSIS found

REM Check if executable was built
if not exist "dist\EmberEye.exe" (
    echo ERROR: dist\EmberEye.exe not found
    echo.
    echo Please run build_windows.bat first to build the executable
    exit /b 1
)

echo ✓ EmberEye.exe found

REM Create installer script
echo [1/3] Creating NSIS installer script...

(
echo ; EmberEye v1.0.0-beta NSIS Installer Script
echo !include "MUI2.nsh"
echo.
echo !define APP_NAME "EmberEye"
echo !define APP_VERSION "1.0.0-beta"
echo !define COMPANY "EmberEye Team"
echo !define APP_PUBLISHER "EmberEye"
echo !define APP_URL "https://github.com/ratnaprasad/EmberEye"
echo.
echo Name "${APP_NAME} ${APP_VERSION}"
echo OutFile "dist\EmberEye-${APP_VERSION}-Setup.exe"
echo InstallDir "$PROGRAMFILES\${APP_NAME}"
echo InstallDirRegKey HKLM "Software\${APP_NAME}" ""
echo.
echo !insertmacro MUI_PAGE_WELCOME
echo !insertmacro MUI_PAGE_DIRECTORY
echo !insertmacro MUI_PAGE_INSTFILES
echo !insertmacro MUI_PAGE_FINISH
echo.
echo !insertmacro MUI_LANGUAGE "English"
echo.
echo Section "Install"
echo   SetOutPath "$INSTDIR"
echo   File "dist\EmberEye.exe"
echo   File "logo.ico" /oname=EmberEye.ico
echo   
echo   ; Create Start Menu shortcuts
echo   CreateDirectory "$SMPROGRAMS\${APP_NAME}"
echo   CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\EmberEye.exe" "" "$INSTDIR\EmberEye.ico"
echo   CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"
echo   
echo   ; Desktop shortcut
echo   CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\EmberEye.exe" "" "$INSTDIR\EmberEye.ico"
echo   
echo   ; Write uninstaller
echo   WriteUninstaller "$INSTDIR\uninstall.exe"
echo   WriteRegStr HKLM "Software\${APP_NAME}" "" "$INSTDIR"
echo SectionEnd
echo.
echo Section "Uninstall"
echo   Delete "$INSTDIR\EmberEye.exe"
echo   Delete "$INSTDIR\EmberEye.ico"
echo   Delete "$INSTDIR\uninstall.exe"
echo   RMDir "$INSTDIR"
echo   
echo   Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
echo   Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
echo   RMDir "$SMPROGRAMS\${APP_NAME}"
echo   
echo   Delete "$DESKTOP\${APP_NAME}.lnk"
echo   
echo   DeleteRegKey HKLM "Software\${APP_NAME}"
echo SectionEnd
) > EmberEye_Installer.nsi

echo [2/3] Building NSIS installer...
makensis EmberEye_Installer.nsi

if errorlevel 1 (
    echo ERROR: NSIS build failed
    exit /b 1
)

echo [3/3] Installer created!
echo.
echo ========================================
echo INSTALLER CREATED
echo ========================================
echo.
echo Setup file: dist\EmberEye-1.0.0-beta-Setup.exe
echo Size: ~900MB
echo.
echo Features:
echo - Automatic GPU detection
echo - Start Menu shortcuts
echo - Desktop shortcut
echo - Uninstaller
echo.
echo Ready for distribution to team!
echo.
echo ========================================
echo.

pause
