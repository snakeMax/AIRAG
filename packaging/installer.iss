; Inno Setup script for AIRAG. Compiled by tools/build.py:
;   ISCC /DAppVersion=0.2.0 packaging\installer.iss
; Installs per user (no admin prompt) into %LOCALAPPDATA%\Programs\AIRAG.

#define AppName "AIRAG"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "snakeMax"
#define AppURL "https://github.com/snakeMax/AIRAG"
#define AppExe "AIRAG.exe"

[Setup]
AppId={{9B5D3C1E-6F2A-4E8B-A7C4-2D1F0E3B8A6C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=AIRAG-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; AIRAG appears in "Open with" for Markdown, saved articles and exported web pages (it never takes over the default app)
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
ModeTitle=Window mode
ModeSubtitle=How should AIRAG open?
ModeText=You can switch later in Settings → General.
ModeDesktop=Desktop window (recommended) - AIRAG opens in its own window
ModeBrowser=Browser tab + tray icon - AIRAG opens in your web browser and stays in the system tray
AutoStart=Start AIRAG when I sign in to Windows
GetBrowser=Download the headless browser for JavaScript-heavy websites (about 150 MB, can be done later in Settings)
DownloadingBrowser=Downloading the headless browser (this can take a few minutes)...
DataFound=Existing settings and history were found and will be kept:
AppRunning=AIRAG is still running. Close it and click OK to continue.
RemoveData=Also delete your AIRAG settings, search history and library index?
norwegian.ModeTitle=Vindusmodus
norwegian.ModeSubtitle=Hvordan skal AIRAG åpnes?
norwegian.ModeText=Du kan bytte senere under Innstillinger → Generelt.
norwegian.ModeDesktop=Skrivebordsvindu (anbefalt) - AIRAG åpnes i sitt eget vindu
norwegian.ModeBrowser=Nettleserfane + ikon i systemstatusfeltet - AIRAG åpnes i nettleseren
norwegian.AutoStart=Start AIRAG når jeg logger på Windows
norwegian.GetBrowser=Last ned den hodeløse nettleseren for nettsteder som bruker mye JavaScript (ca. 150 MB, kan gjøres senere)
norwegian.DownloadingBrowser=Laster ned den hodeløse nettleseren (dette kan ta noen minutter)...
norwegian.DataFound=Eksisterende innstillinger og historikk ble funnet og beholdes:
norwegian.AppRunning=AIRAG kjører fortsatt. Lukk programmet og klikk OK for å fortsette.
norwegian.RemoveData=Vil du også slette AIRAG-innstillinger, søkehistorikk og bibliotekindeks?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:AutoStart}"; Flags: unchecked
Name: "headless"; Description: "{cm:GetBrowser}"; Flags: unchecked

[InstallDelete]
; remove files from the previous version so stale modules never linger after an update
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\AIRAG\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AIRAG"; ValueData: """{app}\{#AppExe}"" --no-open"; Flags: uninsdeletevalue; Tasks: autostart

; "Open with AIRAG": listed under Open with, never made the default app for these file types
Root: HKA; Subkey: "Software\Classes\AIRAG.Document"; ValueType: string; ValueName: ""; ValueData: "AIRAG article"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AIRAG.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\AIRAG.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "AIRAG"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.md\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".md"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.markdown\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".markdown"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.html\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".html"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.htm\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".htm"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.json\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".json"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.csv\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".csv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.tsv\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".tsv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.xlsx\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".xlsx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.ods\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".ods"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.docx\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".docx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.odt\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".odt"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.rtf\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".rtf"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.pptx\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pptx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.odp\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".odp"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.db\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".db"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.sqlite\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".sqlite"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.txt\OpenWithProgids"; ValueType: string; ValueName: "AIRAG.Document"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".txt"; ValueData: ""

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--install-browser"; StatusMsg: "{cm:DownloadingBrowser}"; Flags: runhidden waituntilterminated; Tasks: headless
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsUpdateRun

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  ModePage: TInputOptionWizardPage;
  DataFound: Boolean;

function HasParam(const P: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), P) = 0 then
      Result := True;
end;

{ Started by AIRAG's own updater: keep the user's choices and relaunch afterwards }
function IsUpdateRun: Boolean;
begin
  Result := HasParam('/AIRAGUPDATE');
end;

function InitializeSetup(): Boolean;
var
  I: Integer;
begin
  Result := True;
  { give a closing AIRAG a few seconds to exit (the updater quits right after starting setup) }
  for I := 1 to 40 do
  begin
    if not CheckForMutexes('AIRAGRunningMutex') then
      Exit;
    Sleep(250);
  end;
  if not WizardSilent then
    while CheckForMutexes('AIRAGRunningMutex') do
      if MsgBox(CustomMessage('AppRunning'), mbConfirmation, MB_OKCANCEL) = IDCANCEL then
      begin
        Result := False;
        Exit;
      end;
end;

procedure InitializeWizard;
begin
  DataFound := DirExists(ExpandConstant('{userappdata}\AIRAG'));
  ModePage := CreateInputOptionPage(wpSelectTasks, CustomMessage('ModeTitle'), CustomMessage('ModeSubtitle'),
    CustomMessage('ModeText'), True, False);
  ModePage.Add(CustomMessage('ModeDesktop'));
  ModePage.Add(CustomMessage('ModeBrowser'));
  if GetPreviousData('UIMode', 'desktop') = 'browser' then
    ModePage.SelectedValueIndex := 1
  else
    ModePage.SelectedValueIndex := 0;
end;

function SelectedMode: String;
begin
  if ModePage.SelectedValueIndex = 1 then
    Result := 'browser'
  else
    Result := 'desktop';
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'UIMode', SelectedMode);
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;
  Result := Result + CustomMessage('ModeTitle') + ':' + NewLine + Space +
    ModePage.CheckListBox.ItemCaption[ModePage.SelectedValueIndex] + NewLine;
  if DataFound then
    Result := Result + NewLine + CustomMessage('DataFound') + NewLine + Space + ExpandConstant('{userappdata}\AIRAG');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not IsUpdateRun then
  begin
    ForceDirectories(ExpandConstant('{userappdata}\AIRAG'));
    SaveStringToFile(ExpandConstant('{userappdata}\AIRAG\pending_ui_mode.txt'), SelectedMode, False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if DirExists(ExpandConstant('{userappdata}\AIRAG')) or DirExists(ExpandConstant('{localappdata}\AIRAG')) then
      if MsgBox(CustomMessage('RemoveData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(ExpandConstant('{userappdata}\AIRAG'), True, True, True);
        DelTree(ExpandConstant('{localappdata}\AIRAG'), True, True, True);
      end;
end;
