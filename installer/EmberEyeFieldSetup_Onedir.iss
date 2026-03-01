; EmberEye Field wizard installer (GPU onedir build)
; Build onedir first:
;   python build_field_onefile.py --mode onedir
; Build installer:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\EmberEyeFieldSetup_Onedir.iss

#define MyAppName "EmberEye Field"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "S3Micro Systems"
#define MyAppExeName "EmberEye-Field-GPU.exe"

[Setup]
AppId={{87D55E96-E9A2-4A5E-8D0E-91809A2A40E8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EmberEye Field
DefaultGroupName=EmberEye Field
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=EmberEyeFieldSetup-GPU
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
Source: "dist\EmberEye-Field-GPU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\logs"

[Icons]
Name: "{autoprograms}\EmberEye Field\EmberEye Field"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\EmberEye Field"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch EmberEye Field"; Flags: nowait postinstall skipifsilent
