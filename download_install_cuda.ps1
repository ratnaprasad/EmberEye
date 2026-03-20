# Compatibility wrapper for scripts/windows/download_install_cuda.ps1
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "scripts\windows\download_install_cuda.ps1"

if (-not (Test-Path $target)) {
    Write-Error "Target script not found: $target"
    exit 1
}

& $target @args
