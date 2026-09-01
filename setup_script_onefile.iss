; Inno Setup script for STAVA Player (onefile build)

[Setup]
AppId={{A1CC3AA9-4079-4A96-8C13-42E8B6C5C4D7}
AppName=STAVA Player
AppVersion=1.0
AppPublisher=STAVA
DefaultDirName={autopf}\STAVA Player
DefaultGroupName=STAVA Player
OutputDir=dist
OutputBaseFilename=STAVA_Player_OneFile_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=icons\Logo.ico
UninstallDisplayIcon={app}\Stava Player OneFile.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\Stava Player OneFile.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\STAVA Player"; Filename: "{app}\Stava Player OneFile.exe"
Name: "{autodesktop}\STAVA Player"; Filename: "{app}\Stava Player OneFile.exe"; Tasks: desktopicon
Name: "{group}\Uninstall STAVA Player"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Stava Player OneFile.exe"; Description: "Launch STAVA Player"; Flags: nowait postinstall skipifsilent
