# Pharmacy Suite server cleanup / check utility.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\kill-servers.ps1          # kill app servers
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\kill-servers.ps1 -Check   # list only, kill nothing
#
# Safety: node.exe processes are only killed when their command line references this
# project directory, so unrelated node tooling (editors, agents, etc.) is untouched.

param(
    [switch]$Check
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$targetNames = @("node", "backend", "fresh")
$processes = Get-CimInstance Win32_Process | Where-Object { $targetNames -contains ($_.Name -replace '\.exe$','') }

foreach ($proc in $processes) {
    $cmdLine = $proc.CommandLine
    $isOurs = $false

    if ($proc.Name -ieq "backend.exe" -or $proc.Name -ieq "fresh.exe") {
        # App-specific sidecar names: always ours.
        $isOurs = $true
    }
    elseif ($cmdLine -and $cmdLine.ToLower().Contains($projectRoot.ToLower())) {
        # node.exe running from this project.
        $isOurs = $true
    }

    if ($isOurs) {
        if ($Check) {
            Write-Host "FOUND $($proc.Name) pid $($proc.ProcessId) :: $cmdLine"
        }
        else {
            Write-Host "KILLING $($proc.Name) pid $($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not $processes) {
    Write-Host "No matching processes."
}
