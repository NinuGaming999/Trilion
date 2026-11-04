; Inno Setup script: wraps the fast-starting onedir build into ONE Trilion-Setup.exe
[Setup]
AppId=TrilionBetaCommandCenter
AppName=Trilion Beta
AppVersion=0.7.1-beta.1
AppPublisher=NinuGaming
DefaultDirName={autopf}\Trilion Beta
DefaultGroupName=Trilion Beta
OutputDir=..\dist
OutputBaseFilename=Trilion-Beta-Setup
SetupIconFile=..\assets\trilion.ico
UninstallDisplayIcon={app}\Trilion.exe
Compression=lzma2/ultra64
LZMAUseSeparateProcess=yes
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\Trilion\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Trilion Beta"; Filename: "{app}\Trilion.exe"
Name: "{group}\Trilion Beta"; Filename: "{app}\Trilion.exe"

[Run]
Filename: "{app}\Trilion.exe"; Description: "Launch Trilion Beta"; Flags: nowait postinstall skipifsilent
