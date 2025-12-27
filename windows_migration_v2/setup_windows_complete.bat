@echo off
echo ============================================
echo EmberEye Windows Setup - Complete Installation
echo ============================================
echo.

REM Check Python version
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11 from python.org
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing dependencies with pre-built wheels...
pip install PyQt5 --only-binary :all:
pip install numpy --only-binary :all:
pip install opencv-python --only-binary :all:
pip install Pillow --only-binary :all:
pip install bcrypt --only-binary :all:
pip install passlib --only-binary :all:
pip install cryptography==41.0.7 --only-binary :all:
pip install pyinstaller==6.16.0
pip install websockets
pip install onvif-zeep
pip install wsdiscovery
pip install matplotlib

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo To activate the environment in future sessions:
echo   venv\Scripts\activate
echo.
echo To build the EXE:
echo   pyinstaller EmberEye.spec
echo.
pause
