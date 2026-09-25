cd /d E:\my progam pharmacy\src-tauri
set SIGN_CERT_PATH=E:\my progam pharmacy\src-tauri\test-cert.pfx
set SIGN_CERT_PASSWORD=test123
set BIN_DIR=E:\my progam pharmacy\src-tauri\binaries\
for %%F in (node-x86_64-pc-windows-msvc.exe backend-x86_64-pc-windows-msvc.exe node-x86_64-pc-windows-gnu.exe backend-x86_64-pc-windows-gnu.exe) do (
  if exist "%BIN_DIR%\%%F" (
    echo [pre-sign] signing %%F
    cmd /c "E:\my progam pharmacy\src-tauri\sign.cmd" "%BIN_DIR%\%%F"
  ) else (
    echo [pre-sign] skip: %%F
  )
)
