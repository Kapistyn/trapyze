; traPYze-Setup.exe: a familiar Windows installer around install.ps1.
; Built by the release workflow with Inno Setup: iscc /DAppVersion=0.13.0 installer\windows\trapyze.iss
; It installs for the current user only (no administrator), needs the internet,
; and shows a console window with the progress while uv and traPYze install.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E0B8E-6D1B-4E8A-9F3D-1A7B2C4D5E6F}
AppName=traPYze
AppVersion={#AppVersion}
AppVerName=traPYze {#AppVersion}
AppPublisher=traPYze contributors
AppPublisherURL=https://github.com/kapistyn/trapyze
AppSupportURL=https://github.com/kapistyn/trapyze/issues
DefaultDirName={localappdata}\Programs\traPYze-setup
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=traPYze-Setup
SetupIconFile=..\..\src\trapyze\web\static\icon.ico
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName=traPYze
LicenseFile=..\..\LICENSE
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Messages]
WelcomeLabel2=This installs traPYze for you (no administrator needed).%n%nIt needs the internet: it fetches uv, which runs Python for traPYze, and the newest traPYze from GitHub. A window shows the progress; it takes a minute or two.%n%nYour tools, results and vault are never touched, also not when you install again to update.
FinishedLabel=traPYze is installed and opening. Next time, use the traPYze shortcut on your desktop or in the Start menu.

[Files]
Source: "..\install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\uninstall.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\src\trapyze\web\static\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{cmd}"; Parameters: "/c set TRAPYZE_SETUP_EXE=1&& powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"""; StatusMsg: "Installing traPYze; the console window shows the progress..."; Flags: waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"""; Flags: waituntilterminated; RunOnceId: "RemoveTrapyze"
