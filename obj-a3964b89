# Master Clean-Room E2E Orchestrator (Spec: Objective 4, Task D)
#
# Drives the entire application lifecycle with zero human intervention:
#   1. Uninstall the existing app (via product code from the registry)
#   2. Wipe all leftover application data/configs (%APPDATA%\PharmacySuite)
#   3. Install the new MSI build
#   4. Launch the installed app (sidecars included)
#   5-6. Playwright (e2e/clean-room.spec.ts) then drives: wizard -> login ->
#        diagnostics export into e2e-artifacts\
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\clean-room-e2e.ps1
# Requires elevation for the uninstall/install steps (msiexec per-machine).

$ErrorActionPreference = "Stop"

$Root       = Split-Path -Parent $PSScriptRoot
$DataDir    = Join-Path $env:APPDATA "PharmacySuite"
$MsiPath    = Join-Path $Root "src-tauri\target\release\bundle\msi\Pharmacy Suite_1.0.0_x64_en-US.msi"
$AppName    = "Pharmacy Suite"
$LogFile    = Join-Path $env:TEMP "pharmacysuite-e2e-msi.log"

if (-not (Test-Path $MsiPath)) { throw "MSI not found: $MsiPath — run 'npm run tauri build' first." }

function Get-PharmacyProductCode {
    $paths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($p in $paths) {
        $key = Get-ItemProperty $p -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*$AppName*" } | Select-Object -First 1
        if ($key) { return $key.PSChildName }
    }
    return $null
}

Write-Host "=== [1/5] Uninstall existing app ==="
$code = Get-PharmacyProductCode
if ($code) {
    Write-Host "Product code: $code"
    $p = Start-Process msiexec.exe -ArgumentList "/x",$code,"/qn","/norestart","/L*v",$LogFile -Wait -PassThru
    Write-Host "Uninstall exit code: $($p.ExitCode)"
} else {
    Write-Host "No installed product found — skipping uninstall."
}

Write-Host "=== [2/5] Wipe application data ==="
if (Test-Path $DataDir) {
    Remove-Item -Recurse -Force $DataDir
    Write-Host "Wiped $DataDir"
} else {
    Write-Host "No data dir present — clean already."
}

Write-Host "=== [3/5] Install fresh MSI ==="
$p = Start-Process msiexec.exe -ArgumentList "/i",("`"$MsiPath`""),"/qn","/norestart","/L*v","$LogFile.install" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "MSI install failed with exit code $($p.ExitCode)" }
Write-Host "Install OK."

Write-Host "=== [4/5] Launch installed app ==="
$Exe = "C:\Program Files\Pharmacy Suite\Pharmacy Suite.exe"
if (-not (Test-Path $Exe)) {
    $Exe = (Get-ChildItem "C:\Program Files*\Pharmacy Suite\*.exe" |
        Where-Object { $_.Name -notlike "*unins*" } | Select-Object -First 1).FullName
}
Start-Process $Exe
Write-Host "Launched: $Exe"

# Wait for the frontend sidecar to answer before handing off to Playwright.
$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 2
    $up = $false
    try { $r = Invoke-WebRequest "http://127.0.0.1:3000/api/v1/setup/status" -UseBasicParsing -TimeoutSec 3; $up = ($r.StatusCode -eq 200) } catch {}
} while (-not $up -and (Get-Date) -lt $deadline)
if (-not $up) { throw "Frontend sidecar on :3000 did not come up within 90s." }
Write-Host "=== [5/5] Sidecar up — run Playwright: npx playwright test e2e/clean-room.spec.ts ==="
