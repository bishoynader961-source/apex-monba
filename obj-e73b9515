@echo off
setlocal enabledelayedexpansion
set SIGN_CERT_PATH=E:\my progam pharmacy\src-tauri\test-cert.pfx
set SIGN_CERT_PASSWORD=test123
set TAURI_WINDOWS_SIGNTOOL_PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe
set BIN_DIR=E:\my progam pharmacy\src-tauri\binaries\
for %%F in (node-x86_64-pc-windows-msvc.exe backend-x86_64-pc-windows-msvc.exe) do (
  if exist "%BIN_DIR%\%%F" (
    echo [pre-sign] signing %%F
    call "E:\my progam pharmacy\src-tauri\sign.cmd" "%BIN_DIR%\%%F"
  ) else (
    echo [pre-sign] skip (not found): %%F
  )
)
echo done
