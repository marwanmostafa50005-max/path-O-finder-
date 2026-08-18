; Inno Setup script for path-O-finder — fully offline installer.
; Build (on the Windows build host, after PyInstaller):
;   iscc installer\installer.iss
; Produces installer\output\path-O-finder-setup-<version>.exe

#define MyAppName "path-O-finder"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Marwan Morsy"
#define MyAppExeName "path-O-finder.exe"

[Setup]
AppId={{7A3F60D1-4B0E-4C9B-9C40-PATHOFINDER1}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=output
OutputBaseFilename=path-O-finder-setup-{#MyAppVersion}
SetupIconFile=pathofinder.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Fully offline: no download plugins, no web setup.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The complete PyInstaller onedir output.
Source: "..\dist\path-O-finder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Third-party licence texts shipped alongside the binaries.
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs
Source: "..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
; Start-menu entry and desktop shortcut, both carrying the multi-resolution icon.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
