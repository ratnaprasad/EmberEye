# ============================================================================
# Install NVIDIA CUDA 12.8 Toolkit (Runtime Libraries)
# ============================================================================
# This installs the CUDA runtime libraries needed for PyTorch to work
# ============================================================================

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  NVIDIA CUDA 12.8 Toolkit Installation Required" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "PyTorch error: c10.dll initialization failed" -ForegroundColor Red
Write-Host ""
Write-Host "This means NVIDIA CUDA runtime libraries are not installed." -ForegroundColor Yellow
Write-Host ""

Write-Host "Your system has:" -ForegroundColor White
Write-Host "  ✓ NVIDIA Driver: 576.88" -ForegroundColor Green
Write-Host "  ✓ NVIDIA GPU: RTX 5070" -ForegroundColor Green
Write-Host "  ✓ PyTorch: 2.10.0+cu128" -ForegroundColor Green
Write-Host "  ✗ CUDA Toolkit (runtime libraries): NOT INSTALLED" -ForegroundColor Red
Write-Host ""

Write-Host "You need to install NVIDIA CUDA 12.8 Toolkit" -ForegroundColor Yellow
Write-Host ""

Write-Host "Option 1: Install full CUDA Toolkit (recommended)" -ForegroundColor Cyan
Write-Host "  Download: https://developer.nvidia.com/cuda-12-8-0-download-archive" -ForegroundColor White
Write-Host "  Select:" -ForegroundColor White
Write-Host "    - Operating System: Windows" -ForegroundColor White
Write-Host "    - Architecture: x86_64" -ForegroundColor White
Write-Host "    - Version: 12.8" -ForegroundColor White
Write-Host "    - Installer type: exe (local)" -ForegroundColor White
Write-Host "  Then run the installer and select 'CUDA' component" -ForegroundColor White
Write-Host ""

Write-Host "Option 2: Install CUDA Toolkit via Chocolatey (if installed)" -ForegroundColor Cyan
Write-Host "  Run in admin PowerShell:" -ForegroundColor White
Write-Host "    choco install cuda --version=12.8.0" -ForegroundColor Gray
Write-Host ""

Write-Host "Option 3: Quick install via conda (if you use conda)" -ForegroundColor Cyan
Write-Host "  Run:" -ForegroundColor White
Write-Host "    conda install cuda-toolkit -c nvidia" -ForegroundColor Gray
Write-Host ""

Write-Host "After installing CUDA Toolkit:" -ForegroundColor Yellow
Write-Host "  1. Restart your computer" -ForegroundColor White
Write-Host "  2. Restart EmberEye Studio" -ForegroundColor White
Write-Host "  3. The status bar should show 'Device: 0' (GPU)" -ForegroundColor White
Write-Host ""

Write-Host "Verify installation after restart:" -ForegroundColor Cyan
Write-Host "  nvcc --version" -ForegroundColor Gray
Write-Host ""

Write-Host "Reference:" -ForegroundColor Cyan
Write-Host "  CUDA Toolkit: https://developer.nvidia.com/cuda-downloads" -ForegroundColor White
Write-Host "  CUDA 12.8: https://developer.nvidia.com/cuda-12-8-0-download-archive" -ForegroundColor White
Write-Host ""

Write-Host "Press any key to open CUDA download link..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Open download link
Start-Process "https://developer.nvidia.com/cuda-12-8-0-download-archive"

Write-Host ""
Write-Host "Opening CUDA 12.8 download page in your browser..." -ForegroundColor Green
