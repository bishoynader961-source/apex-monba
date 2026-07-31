<#
.SYNOPSIS
    PharmacyPro Client Installer — automated HWID setup and license activation.

.DESCRIPTION
    Downloads (or locates) the pharmacy-hwid.exe binary, installs it to a
    standard directory, generates a hardware fingerprint, activates a license
    key against the live server, and verifies the offline token.

.PARAMETER Key
    License key to activate. If omitted, the script will prompt for it.

.PARAMETER InstallDir
    Installation directory. Defaults to ~\AppData\Local\PharmacyPro.

.PARAMETER Server
    API server URL. Defaults to https://inventory1app1nn.pythonanywhere.com/api.

.PARAMETER LocalBinary
    Path to a local pharmacy-hwid.exe to install instead of downloading.

.EXAMPLE
    .\install-client.ps1
    .\install-client.ps1 -Key "PHARM-XXXX-XXXX-XXXX"
    .\install-client.ps1 -LocalBinary ".\pharmacy-hwid.exe"
#>

param(
    [string]$Key,
    [string]$InstallDir = "$env:LOCALAPPDATA\PharmacyPro",
    [string]$Server = "https://inventory1app1nn.pythonanywhere.com/api",
    [string]$LocalBinary
)

$ErrorActionPreference = "Stop"

# ── Helpers ────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host ""
    Write-Host "[$Step] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor DarkGray
}

# ── Banner ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host "  PharmacyPro Client Installer" -ForegroundColor White
Write-Host "  HWID Binding + License Activation" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White

# ── Step 1: Locate or download binary ─────────────────────────────────

Write-Step "1/5" "Locating pharmacy-hwid.exe..."

$exePath = $null

# Check local binary flag
if ($LocalBinary -and (Test-Path $LocalBinary)) {
    $exePath = Resolve-Path $LocalBinary
    Write-Ok "Using local binary: $exePath"
}
# Check if already installed
elseif (Test-Path "$InstallDir\pharmacy-hwid.exe") {
    $exePath = "$InstallDir\pharmacy-hwid.exe"
    Write-Ok "Found existing installation: $exePath"
}
# Check if in current directory
elseif (Test-Path ".\pharmacy-hwid.exe") {
    $exePath = (Resolve-Path ".\pharmacy-hwid.exe").Path
    Write-Ok "Found in current directory: $exePath"
}
# Download from GitHub releases
else {
    Write-Info "Binary not found locally. Downloading from GitHub..."

    $releaseUrl = "https://github.com/inventory1app1NN/pharmacy-hwid/releases/latest/download/pharmacy-hwid-x86_64-pc-windows-msvc.exe"
    $downloadPath = Join-Path $env:TEMP "pharmacy-hwid.exe"

    try {
        # Follow redirects for "latest" release
        $response = Invoke-WebRequest -Uri $releaseUrl -UseBasicParsing -MaximumRedirection 5 -ErrorAction Stop
        [System.IO.File]::WriteAllBytes($downloadPath, $response.Content)
        $exePath = $downloadPath
        Write-Ok "Downloaded to: $downloadPath"
    }
    catch {
        Write-Fail "Download failed: $_"
        Write-Host ""
        Write-Host "  Manual options:" -ForegroundColor Yellow
        Write-Host "  1. Download from: https://github.com/inventory1app1NN/pharmacy-hwid/releases" -ForegroundColor Yellow
        Write-Host "  2. Run: .\install-client.ps1 -LocalBinary .\pharmacy-hwid.exe" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

# ── Step 2: Install binary ────────────────────────────────────────────

Write-Step "2/5" "Installing to $InstallDir..."

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Ok "Created directory: $InstallDir"
}

$installedExe = Join-Path $InstallDir "pharmacy-hwid.exe"
Copy-Item $exePath $installedExe -Force
Write-Ok "Installed: $installedExe"

# Add to PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$InstallDir", "User")
    $env:PATH = "$env:PATH;$InstallDir"
    Write-Ok "Added to user PATH"
}

# ── Step 3: Generate HWID ─────────────────────────────────────────────

Write-Step "3/5" "Generating hardware fingerprint..."

try {
    $hwidOutput = & $installedExe gen-hwid 2>&1
    $hwid = ($hwidOutput | Select-String "HWID: (.+)").Matches.Groups[1].Value.Trim()
    Write-Ok "HWID: $hwid"
}
catch {
    Write-Fail "Failed to generate HWID: $_"
    exit 1
}

# ── Step 4: License activation ────────────────────────────────────────

Write-Step "4/5" "Activating license..."

# Prompt for key if not provided
if (-not $Key) {
    Write-Host ""
    $Key = Read-Host "  Enter your license key (PHARM-XXXX-XXXX-XXXX)"
    $Key = $Key.Trim()
}

if (-not $Key) {
    Write-Fail "No license key provided."
    exit 1
}

Write-Info "Key  : $Key"
Write-Info "HWID : $hwid"
Write-Info "Server: $Server"
Write-Host ""

try {
    $activateOutput = & $installedExe activate --key $Key --server $Server 2>&1
    $activateOutput | ForEach-Object { Write-Info $_ }

    # Check for success
    if ($activateOutput -match "ACTIVATED") {
        Write-Ok "License activated successfully"
    }
    elseif ($activateOutput -match "offline token") {
        Write-Ok "Offline token cached"
    }
    else {
        Write-Info "Activation response received (see above)"
    }
}
catch {
    Write-Fail "Activation failed: $_"
    Write-Host ""
    Write-Host "  Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - Verify your license key is correct" -ForegroundColor Yellow
    Write-Host "  - Check your internet connection" -ForegroundColor Yellow
    Write-Host "  - Contact support if the issue persists" -ForegroundColor Yellow
    exit 1
}

# ── Step 5: Verify offline token ──────────────────────────────────────

Write-Step "5/5" "Verifying offline environment..."

try {
    $verifyOutput = & $installedExe verify-token --cached 2>&1
    $verifyOutput | ForEach-Object { Write-Info $_ }

    if ($verifyOutput -match "Valid.*:.*true") {
        Write-Ok "Offline token verified — ready for use"
    }
    else {
        Write-Info "Token verification completed (see output above)"
    }
}
catch {
    Write-Info "Token verification skipped (non-critical)"
}

# ── Summary ────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Binary    : $installedExe"
Write-Host "  HWID      : $hwid"
Write-Host "  Key       : $Key"
Write-Host "  Token     : ~/.license_token"
Write-Host ""
Write-Host "  Commands:" -ForegroundColor Yellow
Write-Host "    pharmacy-hwid validate --key $Key" -ForegroundColor White
Write-Host "    pharmacy-hwid verify-token --cached" -ForegroundColor White
Write-Host "    pharmacy-hwid health" -ForegroundColor White
Write-Host ""
Write-Host "  Offline token expires in 7 days." -ForegroundColor DarkGray
Write-Host "  Re-run this script or run 'pharmacy-hwid validate' to renew." -ForegroundColor DarkGray
Write-Host ""
