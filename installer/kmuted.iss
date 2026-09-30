; KMuted installer (Inno Setup 6). Build with tools/build_installer.py
; or: iscc /DMyAppVersion=0.4.0 installer\kmuted.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "KMuted"
#define MyAppExe "KMuted.exe"
#define MyAppUrl "https://github.com/MarinZXCArtist/KMuted"

[Setup]
AppId={{8F6A3C2E-5B1D-4E7A-9C3F-2D8B7A1E6C54}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}/issues
AppUpdatesURL={#MyAppUrl}/releases
; per-user install: no admin rights needed, updates run silently
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=KMuted-Setup-{#MyAppVersion}
SetupIconFile=..\build\kmuted.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
WizardStyle=modern
WizardSizePercent=110
WizardImageFile=..\build\wizard.bmp
WizardSmallImageFile=..\build\wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ru.DesktopIcon=Создать значок на рабочем столе
en.DesktopIcon=Create a desktop shortcut
ru.AutoStart=Запускать KMuted вместе с Windows
en.AutoStart=Start KMuted with Windows
ru.OpenCable=Открыть страницу VB-Audio Virtual Cable (нужен виртуальный микрофон)
en.OpenCable=Open the VB-Audio Virtual Cable page (the virtual microphone driver)
ru.LaunchApp=Запустить KMuted
en.LaunchApp=Launch KMuted

[Messages]
ru.WelcomeLabel2=Будет установлен [name/ver].%n%nKMuted озвучит ваш текст и отправит его в микрофон — Discord и игры услышат голос.%n%nЯзык программы будет таким же, как язык установки (его можно сменить в настройках).
en.WelcomeLabel2=This will install [name/ver].%n%nKMuted speaks your text into the microphone — Discord and games hear a voice.%n%nThe app will use the same language as this installer (you can change it in Settings).

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "autostart"; Description: "{cm:AutoStart}"; Flags: unchecked

[Files]
Source: "..\dist\KMuted\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KMuted"; ValueData: """{app}\{#MyAppExe}"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall
Filename: "https://vb-audio.com/Cable/"; Description: "{cm:OpenCable}"; Flags: shellexec postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir: String;
begin
  if CurStep = ssPostInstall then
  begin
    { tell KMuted which language was picked in the installer }
    Dir := ExpandConstant('{userappdata}\KMuted');
    ForceDirectories(Dir);
    SaveStringToFile(Dir + '\language.txt', ActiveLanguage, False);
  end;
end;
