#Requires -Version 5.1
<#
  Edge kiosk deployment bootstrap (Phase 4).
  Registers three NSSM services in dependency order so the stack comes up as:
    caddy  ->  backend  ->  frontend
  Each service depends on the one to its left, so stopping/starting is ordered.
  Run from an elevated PowerShell prompt after setup.iss has placed files.
#>
param(
    [string]$InstallDir = "C:\PharmacyPro",
    [string]$PythonExe  = "C:\PharmacyPro\venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$bin      = Join-Path $InstallDir "bin"
$caddy    = Join-Path $bin "caddy\caddy.exe"
$backend  = Join-Path $InstallDir "backend_fastapi"
$license  = Join-Path $InstallDir "archive"
$frontend = Join-Path $InstallDir ".next\standalone"
$logDir   = Join-Path $InstallDir "logs"
$nssm     = Join-Path $bin "nssm\nssm.exe"

if (-not (Test-Path $nssm)) { throw "NSSM not found at $nssm" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Register-Service {
    param($Name, $Exe, $Args, $Depends)
    & $nssm install $Name $Exe @Args | Out-Null
    & $nssm set $Name AppStdout (Join-Path $logDir "$Name.log") | Out-Null
    & $nssm set $Name AppStderr (Join-Path $logDir "$Name.err.log") | Out-Null
    & $nssm set $Name AppRotateFiles 1 | Out-Null
    & $nssm set $Name Start SERVICE_AUTO_START | Out-Null
    if ($Depends) { & $nssm set $Name DependOnService $Depends | Out-Null }
}

# 1) License Backend (Flask/Gunicorn isolated process for key generation)
Register-Service -Name "PharmacyLicense" -Exe $PythonExe `
    -Args @("-m", "gunicorn", "server_app:app", "--bind", "127.0.0.1:5000", "--workers", "1") `
    -Depends $null
& $nssm set PharmacyLicense AppDirectory $license | Out-Null

# 2) Backend (single worker — required for the in-process Lamport lock)
Register-Service -Name "PharmacyBackend" -Exe $PythonExe `
    -Args @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1") `
    -Depends "PharmacyLicense"
# point working directory to backend
& $nssm set PharmacyBackend AppDirectory $backend | Out-Null

# 3) Frontend (Next.js standalone server)
Register-Service -Name "PharmacyFrontend" -Exe (Join-Path $frontend "server.js") `
    -Args @() -Depends "PharmacyBackend"
& $nssm set PharmacyFrontend AppDirectory $frontend | Out-Null
& $nssm set PharmacyFrontend AppEnvironmentExtra "PORT=3000" "HOSTNAME=127.0.0.1" | Out-Null

# 3) Reverse proxy (loopback TLS termination)
Register-Service -Name "PharmacyCaddy" -Exe $caddy `
    -Args @("run", "--config", (Join-Path $InstallDir "Caddyfile"), "--adapter", "caddyfile") `
    -Depends "PharmacyFrontend"
& $nssm set PharmacyCaddy AppDirectory $InstallDir | Out-Null

Write-Host "Registered PharmacyLicense -> PharmacyBackend -> PharmacyFrontend -> PharmacyCaddy."
Write-Host "Start with: nssm start PharmacyLicense; nssm start PharmacyBackend; nssm start PharmacyFrontend; nssm start PharmacyCaddy"
