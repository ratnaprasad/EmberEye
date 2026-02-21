# Download and install NVIDIA CUDA Toolkit 12.8
# This script downloads CUDA from NVIDIA and installs it

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  NVIDIA CUDA 12.8 Toolkit - Downloading & Installing" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

# CUDA download URL (verify this is the correct version)
$DownloadUrl = "https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/cuda_12.8.0_561.99_windows.exe"
$OutputPath = "C:\temp\cuda_12.8.0_windows.exe"

Write-Host "This will download and install NVIDIA CUDA Toolkit 12.8" -ForegroundColor White
Write-Host "File size: ~3GB" -ForegroundColor Yellow
Write-Host "Estimated time: 10-20 minutes depending on your connection" -ForegroundColor Yellow
Write-Host ""

$Confirm = Read-Host "Continue? (y/N)"
if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Create temp directory
Write-Host ""
Write-Host "Creating temporary directory..." -ForegroundColor Cyan
if (-not (Test-Path "C:\temp")) {
    New-Item -ItemType Directory -Path "C:\temp" -Force | Out-Null
}

# Download CUDA installer
Write-Host "Downloading CUDA 12.8.0 from NVIDIA servers..." -ForegroundColor Cyan
Write-Host "(This may take several minutes)" -ForegroundColor Yellow
Write-Host ""

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$webClient = New-Object System.Net.WebClient
$DownloadSuccess = $false

if (Test-Path $OutputPath) {
    Remove-Item $OutputPath -Force
}

$webClient.DownloadFile($DownloadUrl, $OutputPath)

if (Test-Path $OutputPath) {
    $FileSize = [Math]::Round((Get-Item $OutputPath).Length / 1GB, 2)
    Write-Host ""
    Write-Host "✓ Download complete!" -ForegroundColor Green
    Write-Host "  File: $OutputPath" -ForegroundColor Green
    Write-Host "  Size: ${FileSize}GB" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "Installing CUDA Toolkit..." -ForegroundColor Cyan
    Write-Host "Please note: Installation requires administrator privileges" -ForegroundColor Yellow
    Write-Host "Windows may prompt you for confirmation. Click 'Yes' if prompted." -ForegroundColor Yellow
    Write-Host ""
    
    # Run installer with silent installation
    Write-Host "Starting installation..." -ForegroundColor Yellow
    & $OutputPath -s -noprompt
    
    Write-Host ""
    Write-Host "=============================================================="  -ForegroundColor Green
    Write-Host "✓ CUDA Toolkit installation completed!" -ForegroundColor Green
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "IMPORTANT: You must restart your computer for changes to take effect!" -ForegroundColor Yellow
    Write-Host ""
    
    $RestartNow = Read-Host "Restart computer now? (y/N)"
    if ($RestartNow -eq "y" -or $RestartNow -eq "Y") {
        Write-Host "Restarting computer in 30 seconds..." -ForegroundColor Yellow
        shutdown /r /t 30 /c "CUDA Toolkit installation complete. Restarting..."
        Write-Host "Use 'shutdown /a' in another terminal to cancel restart" -ForegroundColor Gray
    }
} else {
    Write-Host ""
    Write-Host "✗ Download failed! File was not created." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please download CUDA 12.8 manually:" -ForegroundColor Yellow
    Write-Host "  https://developer.nvidia.com/cuda-12-8-0-download-archive" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

