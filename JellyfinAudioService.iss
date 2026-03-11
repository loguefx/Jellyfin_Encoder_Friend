; Inno Setup script for JellyfinAudioService
; Produces a reliable .exe installer - replaces the broken cx_Freeze bdist_msi.
; Build: ISCC.exe JellyfinAudioService.iss
; The cx_Freeze build must be run first: python setup.py build_exe

#define AppName "JellyfinAudioService"
#define AppVersion "1.0.11"
#define AppPublisher "Jellyfin Audio Service"
#define AppURL "https://github.com/loguefx/Jellyfin_Encoder_Friend"
#define AppExeName "JellyfinAudioService.exe"
; Override BuildDir on the command line: ISCC /DBuildDir="build\exe.win-amd64-3.11"
#ifndef BuildDir
  #define BuildDir "build\exe.win-amd64-3.13"
#endif

[Setup]
AppId={{B2C3D4E5-F6A7-5B6C-9D0E-1F2A3B4C5D6E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf64}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=JellyfinAudioService-{#AppVersion}-win64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
; Clean install: remove old files before installing new ones
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Main executables
Source: "{#BuildDir}\JellyfinAudioService.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\JellyfinAudioServiceUI.exe"; DestDir: "{app}"; Flags: ignoreversion

; Python runtime and frozen libs
Source: "{#BuildDir}\python313.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\lib\*"; DestDir: "{app}\lib"; Flags: ignoreversion recursesubdirs createallsubdirs

; Web UI assets
Source: "{#BuildDir}\static\*";    DestDir: "{app}\static";    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs

; Helper scripts (optional files guarded with Flags: skipifsourcedoesntexist)
Source: "{#BuildDir}\Register Jellyfin Service.bat";  DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\manual_uninstall_service.bat";   DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\frozen_application_license.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Python source files (for reference / Python mode)
Source: "{#BuildDir}\app.py";        DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\service.py";    DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\config.py";     DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\scanner.py";    DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\transcoder.py"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\cache.py";      DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#BuildDir}\backup.py";     DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName} UI"; Filename: "{app}\JellyfinAudioServiceUI.exe"
Name: "{group}\Register Service (Run as Admin)"; Filename: "{app}\Register Jellyfin Service.bat"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
; Stop and remove any existing service installation before files are replaced
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "stop";   Flags: runhidden waituntilterminated; StatusMsg: "Stopping existing service..."; Check: ServiceExists
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; StatusMsg: "Removing existing service..."; Check: ServiceExists

; Register and start the service after install
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing Windows service..."
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "start";   Flags: runhidden nowait; StatusMsg: "Starting service..."; Check: not WizardSilent

[UninstallRun]
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "stop";   Flags: runhidden waituntilterminated; RunOnceId: "StopSvc"
Filename: "{app}\JellyfinAudioService.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSvc"

[Code]
function ServiceExists(): Boolean;
var
  ResultCode: Integer;
begin
  // Returns true if the service is already registered (so we stop/remove before upgrading)
  Result := Exec('sc.exe', 'query JellyfinAudioService', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;
