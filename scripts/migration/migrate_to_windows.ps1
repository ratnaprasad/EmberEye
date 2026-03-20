# Windows migration and packaging script for EmberEye
param(
    [string]$ProjectPath = (Get-Location).Path,
    [string]$PythonVersion = "3.11"
)

Write-Host "== EmberEye Windows Migration ==" -ForegroundColor Cyan

# 1. Ensure Python is available
Write-Host "Checking Python..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python not found. Please install Python $PythonVersion (64-bit) and rerun." -ForegroundColor Yellow
    exit 1
}

# 2. Create virtual environment
Write-Host "Creating virtual environment..."
$venvPath = Join-Path $ProjectPath ".venv"
python -m venv $venvPath
$env:VIRTUAL_ENV = $venvPath
$env:Path = "$venvPath\\Scripts;" + $env:Path

# 3. Upgrade pip and install dependencies
Write-Host "Installing dependencies..."
python -m pip install --upgrade pip
if (Test-Path (Join-Path $ProjectPath "requirements.txt")) {
    pip install -r (Join-Path $ProjectPath "requirements.txt")
} else {
    Write-Host "requirements.txt not found; installing core packages..." -ForegroundColor Yellow
    pip install pyinstaller PyQt5 passlib
}

# 4. Pre-create runtime files/dirs
Write-Host "Preparing runtime artifacts..."
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectPath "logs") | Out-Null
if (-not (Test-Path (Join-Path $ProjectPath "ip_loc_map.db"))) { New-Item -ItemType File -Force -Path (Join-Path $ProjectPath "ip_loc_map.db") | Out-Null }
if (-not (Test-Path (Join-Path $ProjectPath "ip_loc_map.json"))) { Set-Content -Path (Join-Path $ProjectPath "ip_loc_map.json") -Value "{}" }

# 5. Build with PyInstaller
Write-Host "Building EmberEye.exe..." -ForegroundColor Cyan
Set-Location $ProjectPath
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $ProjectPath "build")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $ProjectPath "dist")
pyinstaller EmberEye.spec

# 6. Output
$exePath = Join-Path $ProjectPath "dist\\EmberEye\\EmberEye.exe"
if (Test-Path $exePath) {
    Write-Host "Build complete: $exePath" -ForegroundColor Green
    Write-Host "Run: `"$exePath`""
} else {
    Write-Host "Build failed. Check PyInstaller logs." -ForegroundColor Red
    exit 1
}
