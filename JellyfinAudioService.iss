; Inno Setup script - use this if the MSI installer fails with Error 2762.
; No custom actions; just copies files. After install, run "Register Jellyfin Service.bat" as Administrator.

#define MyAppName "JellyfinAudioService"
#define MyAppVersion "1.0.9"
#define MyAppPublisher "Jellyfin Audio Service"
#define MyAppURL "https://github.com/loguefx/Jellyfin_Encoder_Friend"

[Setup]
AppId={{A8FE5A47-9CC3-4817-8E86-ACE0438DA853}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf64}\JellyfinAudioService
DefaultGroupName=Jellyfin Audio Service
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=JellyfinAudioService-setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Install all files from the prepared folder (run build_exe_for_inno.bat first)
Source: "dist\installer_files\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Register Windows Service"; Filename: "{app}\Register Jellyfin Service.bat"; Comment: "Run as Administrator to register the service"
Name: "{group}\Uninstall Service"; Filename: "{app}\manual_uninstall_service.bat"; Comment: "Run as Administrator to remove the service"
Name: "{group}\Web UI"; Filename: "{app}\JellyfinAudioServiceUI.exe"; Comment: "Open web configuration"
Name: "{autodesktop}\Jellyfin Audio Service UI"; Filename: "{app}\JellyfinAudioServiceUI.exe"

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Messages]
FinishedLabel=Installation complete. Remember to run "Register Jellyfin Service.bat" as Administrator from the install folder to register the Windows service.
