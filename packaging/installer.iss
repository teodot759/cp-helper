; Inno Setup 6 script for C++ Helper.
; Build the app first (packaging\build-windows.ps1), then run ISCC.exe on this
; file. Per-user install, no admin prompt, no bundled compiler.

#define AppName "C++ Helper"
#define AppVersion "0.1.0"
#define AppExe "CppHelper.exe"

[Setup]
AppId={{C2E9A6F4-1B7D-4A3E-8F52-6D0B7C1E9A44}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=C++ Helper
DefaultDirName={localappdata}\Programs\CppHelper
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=CppHelper-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExe}

[Files]
Source: "..\dist\CppHelper\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
