; EmberEye Field wizard installer
; Build onefile first:
;   python build_field_onefile.py
; Build installer:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\EmberEyeFieldSetup.iss

#define MyAppName "EmberEye Field"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "S3Micro Systems"
#define MyAppExeName "EmberEye-Field-OneFile.exe"

[Setup]
AppId={{7C5E4E22-7D22-41AD-8925-2D0613A0B6A7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EmberEye Field
DefaultGroupName=EmberEye Field
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=EmberEyeFieldSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=logo.ico
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "simulators\*"; DestDir: "{app}\simulators"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "stream_config.example.json"; DestDir: "{app}"; DestName: "stream_config.json"; Flags: ignoreversion
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "users.db"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{app}\logs"

[Icons]
Name: "{autoprograms}\EmberEye Field\EmberEye Field"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\EmberEye Field"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch EmberEye Field"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    Log('Installing EmberEye Field with GPU-first runtime (CPU fallback enabled in app startup).');
  end;
end;
