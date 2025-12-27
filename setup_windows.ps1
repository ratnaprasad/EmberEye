param(
    [string]$InstallPath = "C:\EmberEye",
    [switch]$Force = $false
)

# ============================================================================
# EmberEye v1.0.0-beta - Automated Windows Setup Script
# ============================================================================
# This script:
# 1. Checks/installs prerequisites (Python 3.12+, Git, PyInstaller)
# 2. Clones EmberEye repository
# 3. Sets up virtual environment
# 4. Installs dependencies
# 5. Runs verification tests
# 6. Logs all errors for troubleshooting
# ============================================================================

# Global settings
$LogFile = "$InstallPath\setup_log_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').txt"
$ErrorsFile = "$InstallPath\setup_errors_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').txt"
$WarningsFile = "$InstallPath\setup_warnings_$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').txt"
$PYTHON_MIN_VERSION = "3.12"
$PYTHON_RECOMMENDED_VERSION = "3.12.0"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    
    # Console output
    switch ($Level) {
        "ERROR"   { Write-Host $LogMessage -ForegroundColor Red }
        "WARNING" { Write-Host $LogMessage -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $LogMessage -ForegroundColor Green }
        "INFO"    { Write-Host $LogMessage -ForegroundColor Cyan }
    }
    
    # File logging
    Add-Content -Path $LogFile -Value $LogMessage
    
    if ($Level -eq "ERROR") {
        Add-Content -Path $ErrorsFile -Value $LogMessage
    }
    elseif ($Level -eq "WARNING") {
        Add-Content -Path $WarningsFile -Value $LogMessage
    }
}

function Test-CommandExists {
    param([string]$Command)
    try {
        $null = & $Command --version 2>$null
        return $true
    } catch {
        return $false
    }
}

function Get-CommandVersion {
    param([string]$Command)
    try {
        $version = & $Command --version 2>&1 | Select-Object -First 1
        return $version.Trim()
    } catch {
        return "Unknown"
    }
}

function Compare-Versions {
    param(
        [string]$Current,
        [string]$Required
    )
    
    # Extract version numbers only
    $currentMatch = [regex]::Match($Current, '\d+\.\d+')
    $requiredMatch = [regex]::Match($Required, '\d+\.\d+')
    
    if (-not $currentMatch.Success -or -not $requiredMatch.Success) {
        return $false
    }
    
    $currentVersion = [version]$currentMatch.Value
    $requiredVersion = [version]$requiredMatch.Value
    
    return $currentVersion -ge $requiredVersion
}

# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

function Initialize-Setup {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║      EmberEye v1.0.0-beta - Automated Windows Setup           ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Log "======== EmberEye Setup Started ========"
    Write-Log "Installation Path: $InstallPath"
    Write-Log "PowerShell Version: $($PSVersionTable.PSVersion)"
    Write-Log "OS Version: $(Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption)"
    
    # Create installation directory
    if (-not (Test-Path $InstallPath)) {
        Write-Log "Creating installation directory: $InstallPath"
        New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    }
}

function Check-Python {
    Write-Log "Checking Python installation..."
    
    if (Test-CommandExists "python") {
        $pythonVersion = Get-CommandVersion "python"
        Write-Log "Python found: $pythonVersion"
        
        # Check version requirement
        if (Compare-Versions -Current $pythonVersion -Required $PYTHON_MIN_VERSION) {
            Write-Log "Python version meets requirement ($PYTHON_MIN_VERSION+)" "SUCCESS"
            return $true
        } else {
            Write-Log "Python version is below requirement (need $PYTHON_MIN_VERSION, found $pythonVersion)" "WARNING"
            return $false
        }
    } else {
        Write-Log "Python not found in PATH" "WARNING"
        return $false
    }
}

function Install-Python {
    Write-Log "Attempting to install Python 3.12..." "INFO"
    Write-Host ""
    Write-Host "⚠️  Python 3.12+ is required but not installed." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please download and install Python from:" -ForegroundColor Yellow
    Write-Host "  📥 https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "✅ IMPORTANT: During installation, CHECK:" -ForegroundColor Yellow
    Write-Host "    ☑️  'Add Python to PATH'" -ForegroundColor Green
    Write-Host ""
    Write-Host "After installation, run this script again." -ForegroundColor Yellow
    Write-Host ""
    Write-Log "Manual Python installation required"
    
    return $false
}

function Check-Git {
    Write-Log "Checking Git installation..."
    
    if (Test-CommandExists "git") {
        $gitVersion = Get-CommandVersion "git"
        Write-Log "Git found: $gitVersion" "SUCCESS"
        return $true
    } else {
        Write-Log "Git not found in PATH" "WARNING"
        return $false
    }
}

function Install-Git {
    Write-Log "Attempting to install Git..." "INFO"
    Write-Host ""
    Write-Host "⚠️  Git is required but not installed." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please download and install Git from:" -ForegroundColor Yellow
    Write-Host "  📥 https://git-scm.com/download/win" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Accept all default settings during installation." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installation, run this script again." -ForegroundColor Yellow
    Write-Host ""
    Write-Log "Manual Git installation required"
    
    return $false
}

function Clone-Repository {
    Write-Log "Cloning EmberEye repository..."
    
    $repoPath = Join-Path $InstallPath "EmberEye"
    
    if (Test-Path $repoPath) {
        if ($Force) {
            Write-Log "Repository exists, removing and re-cloning (Force mode)" "WARNING"
            Remove-Item $repoPath -Recurse -Force
        } else {
            Write-Log "Repository already exists at: $repoPath" "SUCCESS"
            return $repoPath
        }
    }
    
    try {
        Write-Host "Cloning repository (this may take a minute)..." -ForegroundColor Cyan
        Push-Location $InstallPath
        
        & git clone https://github.com/ratnaprasad/EmberEye.git 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Repository cloned successfully" "SUCCESS"
            Pop-Location
            return $repoPath
        } else {
            Write-Log "Git clone failed with exit code: $LASTEXITCODE" "ERROR"
            Pop-Location
            return $null
        }
    } catch {
        Write-Log "Error during git clone: $($_.Exception.Message)" "ERROR"
        Pop-Location
        return $null
    }
}

function Setup-VirtualEnvironment {
    param([string]$RepoPath)
    
    Write-Log "Setting up Python virtual environment..."
    
    try {
        Push-Location $RepoPath
        
        $venvPath = Join-Path $RepoPath ".venv"
        
        if (Test-Path $venvPath) {
            Write-Log "Virtual environment already exists" "WARNING"
        } else {
            Write-Host "Creating virtual environment (this may take 1-2 minutes)..." -ForegroundColor Cyan
            & python -m venv .venv 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Virtual environment created successfully" "SUCCESS"
            } else {
                Write-Log "Virtual environment creation failed with exit code: $LASTEXITCODE" "ERROR"
                Pop-Location
                return $false
            }
        }
        
        Pop-Location
        return $true
        
    } catch {
        Write-Log "Error setting up virtual environment: $($_.Exception.Message)" "ERROR"
        Pop-Location
        return $false
    }
}

function Install-Dependencies {
    param([string]$RepoPath)
    
    Write-Log "Installing Python dependencies..."
    
    try {
        Push-Location $RepoPath
        
        # Activate virtual environment
        & .\.venv\Scripts\activate.ps1 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
        
        Write-Host "Upgrading pip, setuptools, and wheel (this may take 1-2 minutes)..." -ForegroundColor Cyan
        & python -m pip install --upgrade pip setuptools wheel 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
        
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Pip upgrade failed with exit code: $LASTEXITCODE" "ERROR"
            Pop-Location
            return $false
        }
        
        Write-Host "Installing project dependencies (this may take 3-5 minutes)..." -ForegroundColor Cyan
        & pip install -r requirements.txt 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Dependencies installed successfully" "SUCCESS"
            Pop-Location
            return $true
        } else {
            Write-Log "Dependency installation failed with exit code: $LASTEXITCODE" "ERROR"
            Pop-Location
            return $false
        }
        
    } catch {
        Write-Log "Error installing dependencies: $($_.Exception.Message)" "ERROR"
        Pop-Location
        return $false
    }
}

function Install-BuildTools {
    param([string]$RepoPath)
    
    Write-Log "Installing build tools (PyInstaller)..."
    
    try {
        Push-Location $RepoPath
        
        Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
        & .\.venv\Scripts\python -m pip install PyInstaller 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Build tools installed successfully" "SUCCESS"
            Pop-Location
            return $true
        } else {
            Write-Log "Build tools installation failed" "WARNING"
            Pop-Location
            return $false
        }
        
    } catch {
        Write-Log "Error installing build tools: $($_.Exception.Message)" "WARNING"
        Pop-Location
        return $false
    }
}

function Verify-Installation {
    param([string]$RepoPath)
    
    Write-Log "Verifying installation..."
    
    try {
        Push-Location $RepoPath
        
        # Check EmberEye import
        Write-Host "Testing EmberEye import..." -ForegroundColor Cyan
        & .\.venv\Scripts\python -c "import embereye; print('✅ EmberEye imported successfully')" 2>&1 | Tee-Object -FilePath $LogFile -Append
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "EmberEye import test passed" "SUCCESS"
        } else {
            Write-Log "EmberEye import test failed" "WARNING"
        }
        
        # Check GPU/CPU detection
        Write-Host "Checking GPU/CPU detection..." -ForegroundColor Cyan
        & .\.venv\Scripts\python -c "import torch; print('GPU Available: ' + str(torch.cuda.is_available()))" 2>&1 | Tee-Object -FilePath $LogFile -Append
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "GPU/CPU detection check passed" "SUCCESS"
        } else {
            Write-Log "GPU/CPU detection check failed" "WARNING"
        }
        
        # Run smoke tests
        Write-Host "Running smoke tests (this may take 1-2 minutes)..." -ForegroundColor Cyan
        & .\.venv\Scripts\python smoke_test_v1.py 2>&1 | Tee-Object -FilePath $LogFile -Append
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Smoke tests passed" "SUCCESS"
        } else {
            Write-Log "Smoke tests completed with warnings" "WARNING"
        }
        
        Pop-Location
        return $true
        
    } catch {
        Write-Log "Error during verification: $($_.Exception.Message)" "ERROR"
        Pop-Location
        return $false
    }
}

function Create-Shortcuts {
    param([string]$RepoPath)
    
    Write-Log "Creating desktop shortcuts..."
    
    try {
        $pythonExe = Join-Path $RepoPath ".venv\Scripts\python.exe"
        $mainPy = Join-Path $RepoPath "main.py"
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        
        # Create shortcut for running app
        $shell = New-Object -ComObject WScript.Shell
        $shortcutPath = Join-Path $desktopPath "EmberEye.lnk"
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $pythonExe
        $shortcut.Arguments = "`"$mainPy`""
        $shortcut.WorkingDirectory = $RepoPath
        $shortcut.Save()
        
        Write-Log "Desktop shortcut created: $shortcutPath" "SUCCESS"
        
        # Create shortcut for opening repository folder
        $folderShortcutPath = Join-Path $desktopPath "EmberEye (Folder).lnk"
        $folderShortcut = $shell.CreateShortcut($folderShortcutPath)
        $folderShortcut.TargetPath = "explorer.exe"
        $folderShortcut.Arguments = "`"$RepoPath`""
        $folderShortcut.Save()
        
        Write-Log "Folder shortcut created: $folderShortcutPath" "SUCCESS"
        
    } catch {
        Write-Log "Error creating shortcuts: $($_.Exception.Message)" "WARNING"
    }
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

function Main {
    # Initialize
    Initialize-Setup
    
    # Check prerequisites
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 1: Checking Prerequisites" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    $pythonOk = Check-Python
    if (-not $pythonOk) {
        if (-not (Install-Python)) {
            Write-Log "Setup cannot continue without Python" "ERROR"
            exit 1
        }
        exit 0
    }
    
    $gitOk = Check-Git
    if (-not $gitOk) {
        if (-not (Install-Git)) {
            Write-Log "Setup cannot continue without Git" "ERROR"
            exit 1
        }
        exit 0
    }
    
    # Clone repository
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 2: Cloning Repository" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    $repoPath = Clone-Repository
    if (-not $repoPath) {
        Write-Log "Failed to clone repository" "ERROR"
        exit 1
    }
    
    # Setup virtual environment
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 3: Setting Up Virtual Environment" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    if (-not (Setup-VirtualEnvironment $repoPath)) {
        Write-Log "Failed to set up virtual environment" "ERROR"
        exit 1
    }
    
    # Install dependencies
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 4: Installing Dependencies" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    if (-not (Install-Dependencies $repoPath)) {
        Write-Log "Failed to install dependencies" "ERROR"
        exit 1
    }
    
    # Install build tools
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 5: Installing Build Tools" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    Install-BuildTools $repoPath | Out-Null
    
    # Verify installation
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 6: Verifying Installation" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    Verify-Installation $repoPath | Out-Null
    
    # Create shortcuts
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Step 7: Creating Shortcuts" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    Create-Shortcuts $repoPath
    
    # Summary
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║           ✅ SETUP COMPLETED SUCCESSFULLY! ✅                 ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "📍 Installation Location: $repoPath" -ForegroundColor Green
    Write-Host "📊 Log Files:" -ForegroundColor Cyan
    Write-Host "   - Main Log: $LogFile"
    Write-Host "   - Errors:   $ErrorsFile"
    Write-Host "   - Warnings: $WarningsFile"
    Write-Host ""
    Write-Host "🚀 Next Steps:" -ForegroundColor Yellow
    Write-Host "   1. Launch EmberEye from desktop shortcut, or"
    Write-Host "   2. Run: cd $repoPath && .\.venv\Scripts\activate && python main.py"
    Write-Host "   3. To build .exe: Run build_windows.bat"
    Write-Host ""
    
    Write-Log "======== Setup Completed Successfully ========"
}

# Run main function
try {
    Main
} catch {
    Write-Log "FATAL ERROR: $($_.Exception.Message)" "ERROR"
    Write-Log "Stack Trace: $($_.ScriptStackTrace)" "ERROR"
    exit 1
}
