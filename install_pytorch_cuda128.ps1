# ============================================================================
# Install PyTorch with CUDA 12.8+ Support (for RTX 5070 / Blackwell)
# ============================================================================
# RTX 5070 requires CUDA 12.8+ compiled binaries for sm_120 support
# ============================================================================

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  EmberEye - PyTorch CUDA 12.8+ Installation" -ForegroundColor Cyan
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
    Write-Host ""
    Write-Host "Checking CUDA driver version..." -ForegroundColor Cyan
    $CudaVersion = (& nvidia-smi | Select-String "CUDA Version: ([0-9.]+)").Matches.Groups[1].Value
    if ($CudaVersion) {
        Write-Host "CUDA Driver Version: $CudaVersion" -ForegroundColor Green
        $CudaMajor = [int]($CudaVersion -split '\.')[0]
        $CudaMinor = [int]($CudaVersion -split '\.')[1]
        
        if ($CudaMajor -lt 12 -or ($CudaMajor -eq 12 -and $CudaMinor -lt 8)) {
            Write-Host ""
            Write-Host "WARNING: CUDA driver version $CudaVersion detected" -ForegroundColor Yellow
            Write-Host "RTX 5070 requires CUDA 12.8+ for full support." -ForegroundColor Yellow
            Write-Host "You may need to update your NVIDIA drivers." -ForegroundColor Yellow
            Write-Host ""
        }
    }
}

Write-Host ""
Write-Host "This will attempt to install PyTorch with CUDA 12.8+ support." -ForegroundColor White
Write-Host ""
Write-Host "Note: CUDA 12.8 PyTorch binaries may not be available yet." -ForegroundColor Yellow
Write-Host "If installation fails, you can:" -ForegroundColor Yellow
Write-Host "  1. Use CPU training (automatic fallback)" -ForegroundColor White
Write-Host "  2. Build PyTorch from source with CUDA 12.8" -ForegroundColor White
Write-Host "  3. Wait for official PyTorch CUDA 12.8 binaries" -ForegroundColor White
Write-Host ""

$Confirm = Read-Host "Continue? (y/N)"

if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "Installation cancelled." -ForegroundColor Yellow
    exit 0
}

# Uninstall current PyTorch
Write-Host ""
Write-Host "Uninstalling current PyTorch..." -ForegroundColor Cyan
& pip uninstall torch torchvision torchaudio -y

# Try different CUDA versions in order of preference
$CudaVersions = @("cu128", "cu126", "cu125", "cu124")
$InstallSuccess = $false

foreach ($CudaVer in $CudaVersions) {
    Write-Host ""
    Write-Host "Attempting installation with $CudaVer..." -ForegroundColor Cyan
    
    $IndexUrl = "https://download.pytorch.org/whl/$CudaVer"
    
    Write-Host "Trying index: $IndexUrl" -ForegroundColor Yellow
    
    # Try to install
    & pip install torch torchvision torchaudio --index-url $IndexUrl 2>&1 | Tee-Object -Variable InstallOutput
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installation successful with $CudaVer!" -ForegroundColor Green
        $InstallSuccess = $true
        break
    } else {
        Write-Host "$CudaVer not available, trying next version..." -ForegroundColor Yellow
    }
}

if (-not $InstallSuccess) {
    Write-Host ""
    Write-Host "ERROR: All CUDA versions failed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "PyTorch CUDA 12.8+ binaries are not yet available." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Your options:" -ForegroundColor White
    Write-Host "  1. Build PyTorch from source with CUDA 12.8" -ForegroundColor White
    Write-Host "     See: https://github.com/pytorch/pytorch#from-source" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2. Use CPU training (automatic in EmberEye)" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. Wait for official PyTorch release with RTX 50 support" -ForegroundColor White
    Write-Host "     Monitor: https://github.com/pytorch/pytorch/releases" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  4. Check community builds:" -ForegroundColor White
    Write-Host "     https://github.com/pytorch/pytorch/issues" -ForegroundColor Cyan
    Write-Host ""
    
    # Reinstall fallback version
    Write-Host "Reinstalling PyTorch CUDA 12.4 as fallback..." -ForegroundColor Yellow
    & pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    
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

# Check CUDA and supported architectures
$CudaAvailable = & python -c "import torch; print(torch.cuda.is_available())" 2>&1
$CudaVersion = & python -c "import torch; print(torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A')" 2>&1

Write-Host "CUDA available: $CudaAvailable" -ForegroundColor Green
Write-Host "CUDA version (PyTorch): $CudaVersion" -ForegroundColor Green

# Check supported compute capabilities
Write-Host ""
Write-Host "Checking supported compute capabilities..." -ForegroundColor Cyan
& python -c "import torch; print('Supported:', torch.cuda.get_arch_list() if torch.cuda.is_available() else 'N/A')" 2>&1

if ($CudaAvailable -eq "True") {
    # Suppress warnings for this check
    $env:PYTORCH_CUDA_ALLOC_CONF = "expandable_segments:True"
    
    $GpuName = & python -c "import torch; import warnings; warnings.filterwarnings('ignore'); print(torch.cuda.get_device_name(0))" 2>&1
    $GpuCap = & python -c "import torch; import warnings; warnings.filterwarnings('ignore'); cap = torch.cuda.get_device_capability(0); print(f'sm_{cap[0]}{cap[1]}')" 2>&1
    
    Write-Host ""
    Write-Host "GPU detected: $GpuName" -ForegroundColor Green
    Write-Host "GPU compute capability: $GpuCap" -ForegroundColor Green
    
    # Check if GPU is supported
    $ArchList = & python -c "import torch; import warnings; warnings.filterwarnings('ignore'); print(','.join(torch.cuda.get_arch_list()))" 2>&1
    
    if ($ArchList -match "sm_120") {
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host "  SUCCESS! RTX 5070 (sm_120) is now supported!" -ForegroundColor Green
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "EmberEye Studio will now use GPU acceleration." -ForegroundColor Cyan
        Write-Host "Restart EmberEye Studio to see 'Device: 0' in the status bar." -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Yellow
        Write-Host "  WARNING: sm_120 still not supported" -ForegroundColor Yellow
        Write-Host "==============================================================" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Supported architectures: $ArchList" -ForegroundColor Yellow
        Write-Host "Your GPU (sm_120) is not in this list." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "This PyTorch build does not yet support RTX 5070." -ForegroundColor Yellow
        Write-Host "EmberEye will automatically use CPU training." -ForegroundColor Cyan
    }
} else {
    Write-Host ""
    Write-Host "WARNING: CUDA not available after installation." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
