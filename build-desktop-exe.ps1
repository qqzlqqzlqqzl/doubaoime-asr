$ErrorActionPreference = "Stop"

. "$PSScriptRoot\enter-dev.ps1"

function Test-Truthy {
  param([string]$Value)
  $Raw = if ($null -eq $Value) { "" } else { $Value }
  $Normalized = $Raw.Trim().ToLowerInvariant()
  return @("1", "true", "yes", "on") -contains $Normalized
}

function Assert-LastExitCode {
  param([string]$Step)
  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

$LicenseServerUrl = "$env:DOUBAO_ASR_LICENSE_URL".Trim()
$RequireActivation = Test-Truthy $env:DOUBAO_ASR_REQUIRE_ACTIVATION
if ($RequireActivation -and -not $LicenseServerUrl) {
  throw "DOUBAO_ASR_REQUIRE_ACTIVATION is enabled, but DOUBAO_ASR_LICENSE_URL is empty."
}

$GeneratedConfigDir = Join-Path $PSScriptRoot "build\license-config"
New-Item -ItemType Directory -Force -Path $GeneratedConfigDir | Out-Null
$GeneratedLicenseConfig = Join-Path $GeneratedConfigDir "license-config.json"
$AppIcon = Join-Path $PSScriptRoot "doubaoime_asr\assets\app.ico"
if (-not (Test-Path $AppIcon)) {
  throw "Missing app icon: $AppIcon"
}
$LicenseConfigJson = [ordered]@{
  server_url = $LicenseServerUrl
  require_activation = $RequireActivation
} | ConvertTo-Json
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($GeneratedLicenseConfig, $LicenseConfigJson, $Utf8NoBom)

$AppExe = Join-Path $PSScriptRoot "dist\DoubaoASRHelper.exe"
$BridgeExe = Join-Path $PSScriptRoot "dist\asr_bridge.exe"
Get-Process DoubaoASRHelper,asr_bridge -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -eq $AppExe -or $_.Path -eq $BridgeExe } |
  ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $_.Id -Timeout 10 -ErrorAction SilentlyContinue
  }

$PyInstallerPackage = Join-Path $PSScriptRoot ".venv\Lib\site-packages\PyInstaller"
if (-not (Test-Path $PyInstallerPackage)) {
  uv pip install -e '.[dev]'
  Assert-LastExitCode "uv pip install project"
  uv pip install pyinstaller
  Assert-LastExitCode "uv pip install pyinstaller"
}

$env:PYTHONWARNINGS = "ignore::SyntaxWarning"

python (Join-Path $PSScriptRoot "tools\run_pyinstaller_no_wmi.py") `
  --noconfirm `
  --clean `
  --log-level WARN `
  --onefile `
  --windowed `
  --name asr_bridge `
  --icon "$AppIcon" `
  --add-binary ".devtools\opus\bin\opus.dll;." `
  --add-data "$GeneratedLicenseConfig;doubaoime_asr" `
  --add-data "$AppIcon;doubaoime_asr\assets" `
  --collect-data sv_ttk `
  --hidden-import doubaoime_asr.long_text_sample `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  doubaoime_asr\asr_bridge.py
Assert-LastExitCode "pyinstaller asr_bridge"

$AhkDir = Join-Path $PSScriptRoot ".devtools\autohotkey\2.0.26"
$AhkBase = Join-Path $AhkDir "AutoHotkey64.exe"
$AhkZip = Join-Path $PSScriptRoot ".devtools\autohotkey\AutoHotkey_2.0.26.zip"
if (-not (Test-Path $AhkBase)) {
  New-Item -ItemType Directory -Force -Path (Split-Path $AhkZip) | Out-Null
  if (-not (Test-Path $AhkZip)) {
    Invoke-WebRequest -Uri "https://github.com/AutoHotkey/AutoHotkey/releases/download/v2.0.26/AutoHotkey_2.0.26.zip" -OutFile $AhkZip
  }
  Expand-Archive -LiteralPath $AhkZip -DestinationPath $AhkDir -Force
}
$AhkCompiler = Join-Path $PSScriptRoot "ahk_client\tools\compiler\Ahk2Exe.exe"
if (-not (Test-Path $AhkCompiler)) {
  throw "Missing AHK compiler: $AhkCompiler"
}
& $AhkCompiler `
  /in (Join-Path $PSScriptRoot "ahk_client\src\main.ahk") `
  /out $AppExe `
  /base $AhkBase `
  /icon (Join-Path $PSScriptRoot "ahk_client\assets\icon.ico")
Assert-LastExitCode "Ahk2Exe DoubaoASRHelper"

python (Join-Path $PSScriptRoot "tools\run_pyinstaller_no_wmi.py") `
  --noconfirm `
  --clean `
  --log-level WARN `
  --onefile `
  --windowed `
  --name DoubaoASRHelperSetup `
  --icon "$AppIcon" `
  --add-binary "dist\DoubaoASRHelper.exe;." `
  --add-binary "dist\asr_bridge.exe;." `
  windows_installer.py
Assert-LastExitCode "pyinstaller setup"

$ReleaseDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "dist\DoubaoASRHelper.exe") (Join-Path $ReleaseDir "DoubaoASRHelper-portable.exe")
Copy-Item -Force (Join-Path $PSScriptRoot "dist\asr_bridge.exe") (Join-Path $ReleaseDir "asr_bridge.exe")
Copy-Item -Force (Join-Path $PSScriptRoot "dist\DoubaoASRHelperSetup.exe") (Join-Path $ReleaseDir "DoubaoASRHelperSetup.exe")
$HelpPath = Join-Path $ReleaseDir "HELP.md"
python -m doubaoime_asr.desktop_help $HelpPath
Assert-LastExitCode "generate HELP.md"

$ActivationReadme = if ($RequireActivation) {
  "Activation: this build requires an activation code and talks to $LicenseServerUrl."
} else {
  "Activation: this build does not require an activation code and opens directly to the voice input workflow."
}
$Readme = @(
  "Doubao ASR Helper for Windows",
  "",
  "Recommended files:",
  "- DoubaoASRHelperSetup.exe: installer for the current Windows user. It creates Start Menu and Desktop shortcuts.",
  "- DoubaoASRHelper-Portable.zip: portable build. Extract it and keep DoubaoASRHelper-portable.exe together with asr_bridge.exe.",
  "- HELP.md: offline usage guide.",
  "",
  $ActivationReadme,
  "",
  "Config and credential cache are saved under %APPDATA%\DoubaoASRHelper on first run.",
  "Windows SmartScreen may show an unknown publisher warning because this build is not code-signed."
) -join [Environment]::NewLine
$Readme | Set-Content -Encoding UTF8 (Join-Path $ReleaseDir "README-Windows.txt")

$PortableReadmePath = Join-Path $ReleaseDir "README-Portable.txt"
$PortableReadme = @(
  "Doubao ASR Helper Portable",
  "",
  "How to run:",
  "1. Extract this zip to any folder.",
  "2. Double-click DoubaoASRHelper-portable.exe. Keep asr_bridge.exe in the same folder.",
  "3. Windows may show a SmartScreen warning because this build is not code-signed.",
  "",
  "No installer is required. Config and credential cache are saved under %APPDATA%\DoubaoASRHelper on first run.",
  $ActivationReadme
) -join [Environment]::NewLine
$PortableReadme | Set-Content -Encoding UTF8 $PortableReadmePath

$PortableZipPath = Join-Path $ReleaseDir "DoubaoASRHelper-Portable.zip"
Compress-Archive -Force -Path @(
  (Join-Path $ReleaseDir "DoubaoASRHelper-portable.exe"),
  (Join-Path $ReleaseDir "asr_bridge.exe"),
  $PortableReadmePath,
  $HelpPath
) -DestinationPath $PortableZipPath

$ZipPath = Join-Path $ReleaseDir "DoubaoASRHelper-Windows.zip"
Compress-Archive -Force -Path @(
  (Join-Path $ReleaseDir "DoubaoASRHelperSetup.exe"),
  (Join-Path $ReleaseDir "DoubaoASRHelper-portable.exe"),
  (Join-Path $ReleaseDir "asr_bridge.exe"),
  (Join-Path $ReleaseDir "README-Windows.txt"),
  $HelpPath
) -DestinationPath $ZipPath

Write-Host "Built dist\DoubaoASRHelper.exe"
Write-Host "Built dist\asr_bridge.exe"
Write-Host "Built dist\DoubaoASRHelperSetup.exe"
Write-Host "Built release\DoubaoASRHelper-Portable.zip"
Write-Host "Built release\DoubaoASRHelper-Windows.zip"
