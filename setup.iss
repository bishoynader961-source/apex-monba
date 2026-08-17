; Inno Setup script for the PharmacyPro edge kiosk installer (Phase 4).
; Build outputs expected (produced by `next build` + `next export`/standalone copy):
;   - .next\standalone\**            -> {app}\.next\standalone
;   - backend_fastapi\**             -> {app}\backend_fastapi
;   - bin\nssm\nssm.exe              -> {app}\bin\nssm
;   - bin\caddy\caddy.exe            -> {app}\bin\caddy
;   - bin\sqlite3\sqlite3.exe        -> {app}\bin\sqlite3
;   - venv\** (bundled Python)       -> {app}\venv
;   - Caddyfile, requirements-freeze.txt, install.ps1

#define MyAppName "PharmacyPro Kiosk"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PharmacyPro"

[Setup]
AppId={{E9132C8B-1F4A-4C9B-9C2D-7A6B5E4D3C2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=PharmacyPro-Kiosk-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: ".\.next\standalone\*"; DestDir: "{app}\.next\standalone"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".\backend_fastapi\*"; DestDir: "{app}\backend_fastapi"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".\venv\*"; DestDir: "{app}\venv"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".\Caddyfile"; DestDir: "{app}"; Flags: ignoreversion
Source: ".\requirements-freeze.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: ".\install.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Bootstrap Windows services (backend -> frontend -> caddy) via NSSM.
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install.ps1"" -InstallDir ""{app}"""; StatusMsg: "Registering kiosk services..."; Flags: runhidden

[UninstallRun]
; Best-effort service teardown on uninstall.
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""$n='{app}\bin\nssm\nssm.exe'; & $n stop PharmacyCaddy; & $n stop PharmacyFrontend; & $n stop PharmacyBackend; & $n remove PharmacyCaddy confirm; & $n remove PharmacyFrontend confirm; & $n remove PharmacyBackend confirm"""; Flags: runhidden
