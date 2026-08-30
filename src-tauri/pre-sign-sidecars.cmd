@echo off
setlocal enabledelayedexpansion
REM Pre-sign Tauri externalBin sidecars so the bundler's verify step passes.
REM Requires SIGN_CERT_PATH + SIGN_CERT_PASSWORD (same vars as sign.cmd).
REM Reuses src-tauri/sign.cmd for identical signing parameters.
REM
REM Signing mutates the binary files on disk. After running this, mark the
REM binaries assume-unchanged so they are NOT committed:
REM   git update-index --assume-unchanged src-tauri/binaries/backend-x86_64-pc-windows-msvc.exe
REM   git update-index --assume-unchanged src-tauri/binaries/node-x86_64-pc-windows-msvc.exe
REM   (repeat for the -gnu variants if you sign them)

if not defined SIGN_CERT_PATH (
  echo [pre-sign] ERROR: SIGN_CERT_PATH not set. Export the .pfx path first.
  exit /b 1
)
if not defined SIGN_CERT_PASSWORD (
  echo [pre-sign] ERROR: SIGN_CERT_PASSWORD not set. Export the .pfx password first.
  exit /b 1
)

set "BIN_DIR=%~dp0binaries"
set "FILES=node-x86_64-pc-windows-msvc.exe backend-x86_64-pc-windows-msvc.exe node-x86_64-pc-windows-gnu.exe backend-x86_64-pc-windows-gnu.exe"

for %%F in (%FILES%) do (
  if exist "%BIN_DIR%\%%F" (
    echo [pre-sign] signing %%F
    cmd /c "%~dp0sign.cmd" "%BIN_DIR%\%%F"
    if errorlevel 1 (
      echo [pre-sign] FAILED on %%F
      exit /b 1
    )
  ) else (
    echo [pre-sign] skip (not found): %%F
  )
)
echo [pre-sign] done.
exit /b 0
