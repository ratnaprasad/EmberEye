@echo off
echo ============================================
echo EmberEye - Conda Environment Setup
echo ============================================
echo.

REM Check if conda is available
where conda >nul 2>&1
if errorlevel 1 (
    echo ERROR: Conda not found. Please install Anaconda or Miniconda:
    echo https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo Creating conda environment 'embereye' with Python 3.11...
call conda create -n embereye python=3.11 -y

echo.
echo Activating environment...
call conda activate embereye

echo.
echo Installing dependencies via conda...
call conda install -c conda-forge pyqt numpy opencv pillow matplotlib -y
call conda install -c conda-forge bcrypt cryptography -y

echo.
echo Installing remaining packages via pip...
pip install passlib
pip install pyinstaller==6.16.0
pip install websockets
pip install onvif-zeep
pip install wsdiscovery

echo.
echo ============================================
echo Conda Setup Complete!
echo ============================================
echo.
echo To activate the environment in future:
echo   conda activate embereye
echo.
echo To build the EXE:
echo   pyinstaller EmberEye.spec
echo.
pause
