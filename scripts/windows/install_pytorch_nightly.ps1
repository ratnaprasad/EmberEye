# ============================================================================
# Install PyTorch Nightly Build (for newest GPUs like RTX 5070)
# ============================================================================
# This script installs the latest PyTorch nightly build which may have
# support for newer GPU architectures (sm_120/compute capability 12.0)
# ============================================================================

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  EmberEye - PyTorch Nightly Installation" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment
$VenvActivate = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run setup_windows.ps1 first." -ForegroundColor Yellow
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
}

# Check for NVIDIA GPU
Write-Host ""
Write-Host "Checking for NVIDIA GPU..." -ForegroundColor Cyan
$NvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue

if ($NvidiaSmi) {
    Write-Host "NVIDIA GPU detected:" -ForegroundColor Green
    & nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader
}

Write-Host ""
Write-Host "WARNING: PyTorch nightly builds are experimental!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Nightly builds may:" -ForegroundColor White
Write-Host "  - Have bugs or instability" -ForegroundColor White
Write-Host "  - Change APIs without warning" -ForegroundColor White
Write-Host "  - Not be production-ready" -ForegroundColor White
Write-Host ""
Write-Host "Use only if you need cutting-edge GPU support." -ForegroundColor Yellow
Write-Host ""

$Confirm = Read-Host "Install PyTorch nightly? (y/N)"

if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "Installation cancelled." -ForegroundColor Yellow
    exit 0
}

# Uninstall current PyTorch
Write-Host ""
Write-Host "Uninstalling current PyTorch..." -ForegroundColor Cyan
& pip uninstall torch torchvision torchaudio -y

# Install PyTorch nightly with CUDA
Write-Host ""
Write-Host "Installing PyTorch nightly with CUDA support..." -ForegroundColor Cyan
Write-Host "(This may take 10-15 minutes depending on your connection)" -ForegroundColor Yellow
Write-Host ""

& pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu124

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Installation failed!" -ForegroundColor Red
    Write-Host "Attempting fallback to stable CUDA version..." -ForegroundColor Yellow
    & pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
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

# Check CUDA and supported architectures
$CudaAvailable = & python -c "import torch; print(torch.cuda.is_available())" 2>&1
$CudaVersion = & python -c "import torch; print(torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A')" 2>&1

Write-Host "CUDA available: $CudaAvailable" -ForegroundColor Green
Write-Host "CUDA version: $CudaVersion" -ForegroundColor Green

# Check supported compute capabilities
Write-Host ""
Write-Host "Checking supported compute capabilities..." -ForegroundColor Cyan
& python -c "import torch; print('Supported:', torch.cuda.get_arch_list() if torch.cuda.is_available() else 'N/A')" 2>&1

if ($CudaAvailable -eq "True") {
    $GpuName = & python -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
    $GpuCap = & python -c "import torch; cap = torch.cuda.get_device_capability(0); print(f'sm_{cap[0]}{cap[1]}')" 2>&1
    
    Write-Host ""
    Write-Host "GPU detected: $GpuName" -ForegroundColor Green
    Write-Host "GPU compute capability: $GpuCap" -ForegroundColor Green
    
    # Check if GPU is supported
    $IsSupported = & python -c "import torch; cap = torch.cuda.get_device_capability(0); cap_str = f'sm_{cap[0]}{cap[1]}'; print(cap_str in torch.cuda.get_arch_list())" 2>&1
    
    if ($IsSupported -eq "True") {
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host "  SUCCESS! Your GPU is now supported!" -ForegroundColor Green
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "EmberEye Studio will now use GPU acceleration." -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Yellow
        Write-Host "  WARNING: GPU still not fully supported" -ForegroundColor Yellow
        Write-Host "==============================================================" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Your RTX 5070 (compute capability 12.0) is very new." -ForegroundColor Yellow
        Write-Host "PyTorch nightly may not have full support yet." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Options:" -ForegroundColor White
        Write-Host "  1. Use CPU training (automatic fallback)" -ForegroundColor White
        Write-Host "  2. Wait for official PyTorch support" -ForegroundColor White
        Write-Host "  3. Check PyTorch forums for updates" -ForegroundColor White
        Write-Host ""
        Write-Host "The app will automatically use CPU until GPU is supported." -ForegroundColor Cyan
    }
} else {
    Write-Host ""
    Write-Host "WARNING: CUDA still not available." -ForegroundColor Yellow
    Write-Host "Will use CPU training." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
