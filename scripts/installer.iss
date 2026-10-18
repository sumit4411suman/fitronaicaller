; Inno Setup 6 script for SELL AGENT. Compile: ISCC /DAppVersion=0.1.0 scripts\installer.iss
; Input : dist\SellAgent\  (PyInstaller one-folder output)
; Output: dist\SellAgent-Setup-<version>.exe
; Per-user data lives in %LOCALAPPDATA%\SellAgent and is KEPT on uninstall unless the user ticks the checkbox.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "SellAgent"
#define AppDisplayName "SELL AGENT"
#define AppPublisher "FITRON"
#define AppExeName "SellAgent.exe"

[Setup]
AppId={{7E3F3B4A-2C9A-4E31-9B22-SELLAGENT0001}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppDisplayName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SellAgent-Setup-{#AppVersion}
SetupIconFile=..\apps\windows-desktop\resources\sellagent.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0.19041
; Close a running SELL AGENT before replacing its files (avoids "MoveFile failed; code 5").
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
; Unsigned by default: Windows SmartScreen will warn. See docs/DESKTOP_APP.md for code-signing options.
; SignTool=signtool

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SellAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppDisplayName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppDisplayName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppDisplayName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppDisplayName}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DeleteDataCheck: TNewCheckBox;
  DeleteDataPage: TNewNotebookPage;

procedure StopRunningApp();
var
  Code: Integer;
begin
  { The desktop app and its backend child lock DLLs in the install folder. Stop both before copying. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#AppExeName}', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM sellagent-backend.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp();
  Result := True;
end;

function DataDir(): String;
begin
  Result := ExpandConstant('{localappdata}\SellAgent');
end;

procedure InitializeUninstallProgressForm();
begin
  { Add a checkbox to the uninstall progress form; default unchecked = keep per-user data. }
  DeleteDataPage := TNewNotebookPage.Create(UninstallProgressForm);
  DeleteDataCheck := TNewCheckBox.Create(UninstallProgressForm);
  DeleteDataCheck.Parent := UninstallProgressForm.InnerNotebook.ActivePage;
  DeleteDataCheck.Top := UninstallProgressForm.StatusLabel.Top + UninstallProgressForm.StatusLabel.Height + 24;
  DeleteDataCheck.Left := UninstallProgressForm.StatusLabel.Left;
  DeleteDataCheck.Width := UninstallProgressForm.StatusLabel.Width;
  DeleteDataCheck.Caption := 'Also delete my SELL AGENT data (contacts, calls, knowledge, backups) in ' + DataDir();
  DeleteDataCheck.Checked := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if (DeleteDataCheck <> nil) and DeleteDataCheck.Checked then
    begin
      if MsgBox('Permanently delete ' + DataDir() + '? This cannot be undone.', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir(), True, True, True);
    end;
  end;
end;
