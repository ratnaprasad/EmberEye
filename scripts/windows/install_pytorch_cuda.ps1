# ============================================================================
# Install PyTorch with CUDA Support
# ============================================================================
# This script replaces CPU-only PyTorch with CUDA-enabled version
# Run this if you have an NVIDIA GPU and want to use it for training
# ============================================================================

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  EmberEye - PyTorch CUDA Installation" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment
$VenvActivate = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run scripts\windows\setup_windows.bat first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& $VenvActivate

# Check current PyTorch installation
Write-Host ""
Write-Host "Checking current PyTorch installation..." -ForegroundColor Cyan
$CurrentPyTorch = & python -c "import torch; print(torch.__version__)" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Current PyTorch version: $CurrentPyTorch" -ForegroundColor Yellow
    
    # Check if CUDA is available
    $CudaAvailable = & python -c "import torch; print(torch.cuda.is_available())" 2>&1
    
    if ($CudaAvailable -eq "True") {
        Write-Host "CUDA is already available! No need to reinstall." -ForegroundColor Green
        Write-Host ""
        & python -c "import torch; print('GPU:', torch.cuda.get_device_name(0))"
        exit 0
    } else {
        Write-Host "CUDA not available. CPU-only version detected." -ForegroundColor Yellow
    }
}

# Check for NVIDIA GPU
Write-Host ""
Write-Host "Checking for NVIDIA GPU..." -ForegroundColor Cyan
$NvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue

if (-not $NvidiaSmi) {
    Write-Host "WARNING: nvidia-smi not found. No NVIDIA GPU detected." -ForegroundColor Yellow
    Write-Host "This script is only for systems with NVIDIA GPUs." -ForegroundColor Yellow
    $Continue = Read-Host "Continue anyway? (y/N)"
    if ($Continue -ne "y" -and $Continue -ne "Y") {
        exit 0
    }
} else {
    Write-Host "NVIDIA GPU detected:" -ForegroundColor Green
    & nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
}

# Confirm installation
Write-Host ""
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Uninstall CPU-only PyTorch" -ForegroundColor White
Write-Host "  2. Install PyTorch with CUDA 13.0 support" -ForegroundColor White
Write-Host "  3. Keep all other packages intact" -ForegroundColor White
Write-Host ""
$Confirm = Read-Host "Proceed with installation? (y/N)"

if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "Installation cancelled." -ForegroundColor Yellow
    exit 0
}

# Uninstall current PyTorch
Write-Host ""
Write-Host "Uninstalling current PyTorch..." -ForegroundColor Cyan
& pip uninstall torch torchvision torchaudio -y

if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: Uninstall had errors, continuing..." -ForegroundColor Yellow
}

# Install PyTorch with CUDA
Write-Host ""
Write-Host "Installing PyTorch with CUDA 13.0 support..." -ForegroundColor Cyan
Write-Host "(This may take several minutes depending on your connection)" -ForegroundColor Yellow
Write-Host ""

& pip install torch==2.11.0+cu130 torchvision==0.26.0+cu130 torchaudio==2.11.0+cu130 --index-url https://download.pytorch.org/whl/cu130

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Installation failed!" -ForegroundColor Red
    Write-Host "Check your internet connection and try again." -ForegroundColor Yellow
    exit 1
}

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Cyan
$NewPyTorch = & python -c "import torch; print(torch.__version__)" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyTorch import failed!" -ForegroundColor Red
    exit 1
}

Write-Host "PyTorch version: $NewPyTorch" -ForegroundColor Green

$CudaAvailable = & python -c "import torch; print(torch.cuda.is_available())" 2>&1
$CudaVersion = & python -c "import torch; print(torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A')" 2>&1

Write-Host "CUDA available: $CudaAvailable" -ForegroundColor Green
Write-Host "CUDA version: $CudaVersion" -ForegroundColor Green

if ($CudaAvailable -eq "True") {
    Remove-Item Env:EMBEREYE_FORCE_CPU -ErrorAction SilentlyContinue
    Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
    $GpuName = & python -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
    $GpuCount = & python -c "import torch; print(torch.cuda.device_count())" 2>&1
    Write-Host "GPU detected: $GpuName" -ForegroundColor Green
    Write-Host "GPU count: $GpuCount" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host "  SUCCESS! PyTorch with CUDA support installed" -ForegroundColor Green
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "EmberEye Studio will now use GPU acceleration for training." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "WARNING: CUDA still not available after installation." -ForegroundColor Yellow
    Write-Host "This could mean:" -ForegroundColor Yellow
    Write-Host "  - Your GPU is not compatible" -ForegroundColor White
    Write-Host "  - NVIDIA drivers need updating" -ForegroundColor White
    Write-Host "  - CUDA runtime is missing" -ForegroundColor White
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
