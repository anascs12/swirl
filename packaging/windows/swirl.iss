; Inno Setup script: builds dist\SwirlSetup-<version>.exe from dist\swirl\
; iscc /DVersion=0.1.0 packaging\windows\swirl.iss
#ifndef Version
  #define Version "0.1.0"
#endif

[Setup]
AppId={{6F2D5C51-6C5B-4E2B-9B2A-5B9C1C7F2A11}
AppName=Swirl
AppVersion={#Version}
AppPublisher=Swirl
DefaultDirName={autopf}\Swirl
DefaultGroupName=Swirl
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=SwirlSetup-{#Version}
SetupIconFile=swirl.ico
UninstallDisplayIcon={app}\swirl.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\swirl\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Swirl Studio"; Filename: "{app}\swirl.exe"
Name: "{group}\Swirl Bubble"; Filename: "{app}\swirl.exe"; Parameters: "--bubble"
Name: "{autodesktop}\Swirl Studio"; Filename: "{app}\swirl.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "contextmenu"; Description: "Add ""Convert with Swirl"" to the right-click menu"; Flags: checkedonce

[Run]
Filename: "{app}\swirl.exe"; Parameters: "--install"; Flags: runhidden; Tasks: contextmenu
Filename: "{app}\swirl.exe"; Description: "Open Swirl Studio"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\swirl.exe"; Parameters: "--uninstall"; Flags: runhidden; RunOnceId: "RemoveContextMenu"
