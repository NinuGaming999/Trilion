; Inno Setup script: wraps the fast-starting onedir build into ONE Trilion-Setup.exe
[Setup]
AppName=Trilion
AppVersion=0.2.0
AppPublisher=NinuGaming
DefaultDirName={autopf}\Trilion
DefaultGroupName=Trilion
OutputDir=..\dist
OutputBaseFilename=Trilion-Setup
SetupIconFile=..\assets\trilion.ico
UninstallDisplayIcon={app}\Trilion.exe
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\Trilion\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Trilion"; Filename: "{app}\Trilion.exe"
Name: "{group}\Trilion"; Filename: "{app}\Trilion.exe"

[Run]
Filename: "{app}\Trilion.exe"; Description: "Launch Trilion"; Flags: nowait postinstall skipifsilent
