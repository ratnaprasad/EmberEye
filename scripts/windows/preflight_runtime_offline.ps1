param(
    [switch]$Install,
    [string]$BundlePath = "",
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

function Get-VCppRedistX64 {
    $roots = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )

    $items = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $items += Get-ChildItem $root -ErrorAction SilentlyContinue |
            ForEach-Object {
                try { Get-ItemProperty $_.PSPath } catch { $null }
            } |
            Where-Object {
                if (-not $_) { return $false }
                $hasDisplayName = $_.PSObject.Properties.Name -contains "DisplayName"
                if (-not $hasDisplayName) { return $false }
                return ($_.DisplayName -match "Microsoft Visual C\+\+ 20(15|17|19|22).+Redistributable.+x64")
            }
    }

    if (-not $items -or $items.Count -eq 0) { return $null }

    $best = $items | Sort-Object {
        try { [version]$_.DisplayVersion } catch { [version]"0.0.0.0" }
    } -Descending | Select-Object -First 1

    return [pscustomobject]@{
        Name = $best.DisplayName
        Version = $best.DisplayVersion
        Publisher = $best.Publisher
    }
}

function Get-UcrtStatus {
    $ucrt = Join-Path $env:windir "System32\ucrtbase.dll"
    if (-not (Test-Path $ucrt)) {
        return [pscustomobject]@{
            Present = $false
            Version = $null
            Path = $ucrt
        }
    }

    $ver = (Get-Item $ucrt).VersionInfo.FileVersion
    return [pscustomobject]@{
        Present = $true
        Version = $ver
        Path = $ucrt
    }
}

function Get-KbStatus {
    param([string[]]$KbIds)

    $installed = @()
    foreach ($kb in $KbIds) {
        $id = $kb.Trim().ToUpperInvariant()
        if ($id -eq "") { continue }
        $hit = Get-HotFix -Id $id -ErrorAction SilentlyContinue
        $installed += [pscustomobject]@{
            Kb = $id
            Installed = [bool]$hit
        }
    }
    return $installed
}

function Ensure-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "Run this script as Administrator."
    }
}

function Install-VcppFromBundle {
    param([string]$Base)

    $installer = Join-Path $Base "vc_redist.x64.exe"
    if (-not (Test-Path $installer)) {
        throw "Missing VC++ installer: $installer"
    }

    Write-Info "Installing VC++ redistributable from $installer"
    $proc = Start-Process -FilePath $installer -ArgumentList "/install /quiet /norestart" -Wait -PassThru
    if ($proc.ExitCode -notin @(0, 1638, 3010)) {
        throw "VC++ installer failed with exit code $($proc.ExitCode)"
    }

    if ($proc.ExitCode -eq 3010) {
        Write-Warn "VC++ install requested reboot (3010)."
    }
}

function Install-KbMsuFromBundle {
    param([string]$Base)

    $kbFolder = Join-Path $Base "kb"
    if (-not (Test-Path $kbFolder)) {
        Write-Info "No KB folder found at $kbFolder (skipping KB install)."
        return
    }

    $msus = Get-ChildItem $kbFolder -Filter "*.msu" -File -ErrorAction SilentlyContinue | Sort-Object Name
    if (-not $msus -or $msus.Count -eq 0) {
        Write-Info "No .msu files found in $kbFolder (skipping KB install)."
        return
    }

    foreach ($msu in $msus) {
        Write-Info "Installing KB package: $($msu.Name)"
        $proc = Start-Process -FilePath "wusa.exe" -ArgumentList "`"$($msu.FullName)`" /quiet /norestart" -Wait -PassThru
        if ($proc.ExitCode -notin @(0, 3010, 2359302)) {
            throw "KB install failed for $($msu.Name) with exit code $($proc.ExitCode)"
        }
        if ($proc.ExitCode -eq 2359302) {
            Write-Info "$($msu.Name) already installed/not applicable (2359302)."
        }
        if ($proc.ExitCode -eq 3010) {
            Write-Warn "$($msu.Name) requested reboot (3010)."
        }
    }
}

# Optional list of KBs to verify (customize for your org image baseline)
$kbTargets = @("KB2999226")

$result = [ordered]@{
    Host = $env:COMPUTERNAME
    Timestamp = (Get-Date).ToString("s")
    VCpp = $null
    UCRT = $null
    Kb = @()
    Ready = $false
}

try {
    if ($Install) {
        Ensure-Admin
        if ([string]::IsNullOrWhiteSpace($BundlePath)) {
            throw "-Install requires -BundlePath (folder containing vc_redist.x64.exe)"
        }

        $resolvedBundle = (Resolve-Path $BundlePath).Path
        Install-VcppFromBundle -Base $resolvedBundle
        Install-KbMsuFromBundle -Base $resolvedBundle
    }

    $vc = Get-VCppRedistX64
    $ucrt = Get-UcrtStatus
    $kbs = Get-KbStatus -KbIds $kbTargets

    $result.VCpp = $vc
    $result.UCRT = $ucrt
    $result.Kb = $kbs

    if ($vc) {
        Write-Ok "VC++ Redistributable detected: $($vc.Name) ($($vc.Version))"
    } else {
        Write-Err "VC++ Redistributable (x64) not found"
    }

    if ($ucrt.Present) {
        Write-Ok "UCRT detected: $($ucrt.Path) ($($ucrt.Version))"
    } else {
        Write-Err "UCRT missing: $($ucrt.Path)"
    }

    foreach ($kb in $kbs) {
        if ($kb.Installed) {
            Write-Ok "$($kb.Kb) installed"
        } else {
            Write-Warn "$($kb.Kb) not detected"
        }
    }

    $result.Ready = [bool]($vc -and $ucrt.Present)

    if ($Json) {
        $result | ConvertTo-Json -Depth 6
    }

    if ($result.Ready) {
        Write-Ok "Runtime preflight PASSED"
        exit 0
    }

    Write-Err "Runtime preflight FAILED"
    exit 2
}
catch {
    Write-Err $_.Exception.Message
    if ($Json) {
        $result | ConvertTo-Json -Depth 6
    }
    exit 1
}
