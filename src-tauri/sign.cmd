@echo off
setlocal
REM Tauri Windows Authenticode signing helper.
REM Invoked via tauri.conf.json -> bundle.windows.signCommand: cmd /c src-tauri/sign.cmd %1
REM Secrets come from ENVIRONMENT VARIABLES (never hardcoded):
REM   SIGN_CERT_PATH      - path to the .pfx / .p12 code-signing certificate
REM   SIGN_CERT_PASSWORD  - password for that certificate
REM   SIGN_TIMESTAMP_URL  - (optional) RFC3161 timestamp server (default DigiCert)
REM   TAURI_WINDOWS_SIGNTOOL_PATH - (optional) explicit path to signtool.exe
REM If the cert env vars are absent (or the cert file is missing) this script
REM exits 0 WITHOUT signing, so unsigned dev builds still succeed. Set the env
REM vars to produce a properly signed release build.

set "CERT=%SIGN_CERT_PATH%"
set "PASS=%SIGN_CERT_PASSWORD%"
set "TS=%SIGN_TIMESTAMP_URL%"
if not defined TS set "TS=http://timestamp.digicert.com"

if not defined CERT goto :noset
if not defined PASS goto :noset
if not exist "%CERT%" (
  echo [sign.cmd] SIGN_CERT_PATH file not found: %CERT% - SKIPPING signing, unsigned build.
  exit /b 0
)
goto :sign

:noset
echo [sign.cmd] SIGN_CERT_PATH/SIGN_CERT_PASSWORD not set - SKIPPING signing, unsigned build.
exit /b 0

:sign
set "SIGNTOOL=%TAURI_WINDOWS_SIGNTOOL_PATH%"
if not defined SIGNTOOL (
  for /f "delims=" %%i in ('where signtool 2^>nul') do set "SIGNTOOL=%%i"
)
if not defined SIGNTOOL (
  if exist "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe" ^
    set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
)
if not defined SIGNTOOL (
  echo [sign.cmd] signtool.exe not found. Install the Windows SDK or set TAURI_WINDOWS_SIGNTOOL_PATH.
  exit /b 1
)

echo [sign.cmd] Signing %1 with %SIGNTOOL% (timestamp: %TS%)
"%SIGNTOOL%" sign /f "%CERT%" /p "%PASS%" /tr "%TS%" /td sha256 /fd sha256 /d "Pharmacy Suite" "%~1"
if errorlevel 1 (
  echo [sign.cmd] signtool failed
  exit /b 1
)
exit /b 0
