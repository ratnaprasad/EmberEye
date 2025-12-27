@echo off
echo ============================================
echo EmberEye - NumPy Fix for Windows
echo ============================================
echo.
echo This script fixes numpy installation issues
echo by using pre-built binary wheels.
echo.

call venv\Scripts\activate.bat

echo Uninstalling existing numpy...
pip uninstall -y numpy

echo.
echo Installing numpy with pre-built wheel...
pip install numpy --only-binary :all:

if errorlevel 1 (
    echo.
    echo Trying alternative: download from PyPI wheels...
    pip install --find-links https://download.pytorch.org/whl/torch_stable.html numpy
)

if errorlevel 1 (
    echo.
    echo ERROR: NumPy installation failed.
    echo.
    echo Try these alternatives:
    echo 1. Use conda environment: setup_windows_conda.bat
    echo 2. Download wheel manually from:
    echo    https://pypi.org/project/numpy/#files
    echo    Then: pip install downloaded_file.whl
    echo.
) else (
    echo.
    echo NumPy installed successfully!
    echo.
)

pause
