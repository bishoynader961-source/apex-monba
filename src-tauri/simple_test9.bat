@echo off
setlocal enabledelayedexpansion
set SIGN_CERT_PATH=E:\my progam pharmacy\src-tauri\test-cert.pfx
set SIGN_CERT_PASSWORD=test123
set TAURI_WINDOWS_SIGNTOOL_PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe
set BIN_DIR=E:\my progam pharmacy\src-tauri\binaries\
set FILES=node-x86_64-pc-windows-msvc.exe backend-x86_64-pc-windows-msvc.exe node-x86_64-pc-windows-gnu.exe backend-x86_64-pc-windows-gnu.exe
for %%F in (%FILES%) do call :sign_file "%%F"
goto :done

:sign_file
set "FILE=%~1"
if exist "%BIN_DIR%\%FILE%" (
  echo [pre-sign] signing %FILE%
  call "E:\my progam pharmacy\src-tauri\sign.cmd" "%BIN_DIR%\%FILE%"
) else (
  echo [pre-sign] skip (not found): %FILE%
)
goto :eof

:done
echo done
