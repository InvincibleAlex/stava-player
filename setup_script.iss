; Inno Setup script for STAVA Player

[Setup]
AppId={{6CC2F0A0-0D3A-4F40-94CF-6E3A4E9E56A1}
AppName=STAVA Player
AppVersion=1.0
AppPublisher=STAVA
DefaultDirName={autopf}\STAVA Player
DefaultGroupName=STAVA Player
OutputDir=dist
OutputBaseFilename=STAVA_Player_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=icons\Logo.ico
UninstallDisplayIcon={app}\Stava Player.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\Stava Player\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STAVA Player"; Filename: "{app}\Stava Player.exe"
Name: "{autodesktop}\STAVA Player"; Filename: "{app}\Stava Player.exe"; Tasks: desktopicon
Name: "{group}\Uninstall STAVA Player"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Stava Player.exe"; Description: "Launch STAVA Player"; Flags: nowait postinstall skipifsilent
