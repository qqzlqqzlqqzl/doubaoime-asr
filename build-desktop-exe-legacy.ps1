$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
. "$Root\enter-dev.ps1"

function Test-Truthy {
  param([string]$Value)
  $Raw = if ($null -eq $Value) { "" } else { $Value }
  $Normalized = $Raw.Trim().ToLowerInvariant()
  return @("1", "true", "yes", "on") -contains $Normalized
}

$LegacyVenv = Join-Path $Root ".venv-win7"
$LegacyPython = Join-Path $LegacyVenv "Scripts\python.exe"
if (-not (Test-Path $LegacyPython)) {
  uv venv $LegacyVenv --python 3.8.20
}

uv pip install --python $LegacyPython -r (Join-Path $Root "requirements-win7-legacy.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install legacy requirements."
}

$PythonVersion = (& $LegacyPython --version).Trim()
if ($PythonVersion -notmatch "^Python 3\.8\.") {
  throw "Legacy build requires Python 3.8.x, got: $PythonVersion"
}

$OpusBin = Join-Path $Root ".devtools\opus\bin"
if (Test-Path $OpusBin) {
  $env:PATH = $OpusBin + [IO.Path]::PathSeparator + $env:PATH
}
$OpusDll = Join-Path $OpusBin "opus.dll"
if (-not (Test-Path $OpusDll)) {
  throw "Missing opus.dll: $OpusDll"
}

& $LegacyPython -m compileall -q (Join-Path $Root "doubaoime_asr") (Join-Path $Root "windows_installer.py")
if ($LASTEXITCODE -ne 0) {
  throw "Legacy Python 3.8 compile check failed."
}

$LicenseServerUrl = "$env:DOUBAO_ASR_LICENSE_URL".Trim()
$RequireActivation = Test-Truthy $env:DOUBAO_ASR_REQUIRE_ACTIVATION
if ($RequireActivation -and -not $LicenseServerUrl) {
  throw "DOUBAO_ASR_REQUIRE_ACTIVATION is enabled, but DOUBAO_ASR_LICENSE_URL is empty."
}

$GeneratedConfigDir = Join-Path $Root "build\license-config-legacy"
New-Item -ItemType Directory -Force -Path $GeneratedConfigDir | Out-Null
$GeneratedLicenseConfig = Join-Path $GeneratedConfigDir "license-config.json"
$LicenseConfigJson = [ordered]@{
  server_url = $LicenseServerUrl
  require_activation = $RequireActivation
} | ConvertTo-Json
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($GeneratedLicenseConfig, $LicenseConfigJson, $Utf8NoBom)

$DistDir = Join-Path $Root "dist-legacy"
$BuildDir = Join-Path $Root "build\legacy"
$SpecDir = Join-Path $BuildDir "spec"
$AppExe = Join-Path $DistDir "DoubaoASRHelper.exe"
New-Item -ItemType Directory -Force -Path $DistDir, $BuildDir, $SpecDir | Out-Null

Get-CimInstance Win32_Process |
  Where-Object { $_.ExecutablePath -eq $AppExe } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
  }

& $LegacyPython -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DoubaoASRHelper `
  --distpath $DistDir `
  --workpath (Join-Path $BuildDir "app") `
  --specpath $SpecDir `
  --add-binary "$OpusDll;." `
  --add-data "$GeneratedLicenseConfig;doubaoime_asr" `
  --collect-data sv_ttk `
  --collect-submodules pydantic `
  --collect-submodules pydantic_core `
  --hidden-import eval_type_backport `
  --hidden-import doubaoime_asr.long_text_sample `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  doubaoime_asr\desktop_app.py
if ($LASTEXITCODE -ne 0) {
  throw "Legacy app PyInstaller build failed."
}

& $LegacyPython -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DoubaoASRHelperSetup `
  --distpath $DistDir `
  --workpath (Join-Path $BuildDir "setup") `
  --specpath $SpecDir `
  --add-binary "$AppExe;." `
  windows_installer.py
if ($LASTEXITCODE -ne 0) {
  throw "Legacy installer PyInstaller build failed."
}

$ReleaseDir = Join-Path $Root "release\legacy"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item -Force $AppExe (Join-Path $ReleaseDir "DoubaoASRHelper-win7-legacy-portable.exe")
Copy-Item -Force (Join-Path $DistDir "DoubaoASRHelperSetup.exe") (Join-Path $ReleaseDir "DoubaoASRHelperSetup-win7-legacy.exe")

$HelpPath = Join-Path $ReleaseDir "HELP.md"
& $LegacyPython -m doubaoime_asr.desktop_help $HelpPath

$ActivationReadme = if ($RequireActivation) {
  "Activation: this build requires an activation code and talks to $LicenseServerUrl."
} else {
  "Activation: this build does not require an activation code and opens directly to the voice input workflow."
}

$Readme = @(
  "Doubao ASR Helper legacy package",
  "",
  "Target:",
  "- Experimental package for Windows 7 SP1 x64, Windows 8.0 x64, and Windows 8.1 x64.",
  "- Built with Python 3.8 and an older PyInstaller bootloader.",
  "- This still needs a real Win7/Win8 VM smoke test before you promise support to other users.",
  "",
  "Files:",
  "- DoubaoASRHelperSetup-win7-legacy.exe: current-user installer.",
  "- DoubaoASRHelper-win7-legacy-portable.exe: portable one-file app.",
  "- HELP.md: offline usage guide.",
  "",
  $ActivationReadme,
  "",
  "Config and credential cache are saved under %APPDATA%\DoubaoASRHelper on first run.",
  "Windows SmartScreen may show an unknown publisher warning because this build is not code-signed."
) -join [Environment]::NewLine
$ReadmePath = Join-Path $ReleaseDir "README-Win7-Legacy.txt"
$Readme | Set-Content -Encoding UTF8 $ReadmePath

$PortableReadmePath = Join-Path $ReleaseDir "README-Win7-Legacy-Portable.txt"
$PortableReadme = @(
  "Doubao ASR Helper Win7 legacy portable package",
  "",
  "How to run:",
  "1. Extract this zip to any folder.",
  "2. Double-click DoubaoASRHelper-win7-legacy-portable.exe.",
  "3. Windows may show a SmartScreen warning because this build is not code-signed.",
  "",
  "No installer is required. Config and credential cache are saved under %APPDATA%\DoubaoASRHelper on first run.",
  $ActivationReadme
) -join [Environment]::NewLine
$PortableReadme | Set-Content -Encoding UTF8 $PortableReadmePath

$PortableZipPath = Join-Path $ReleaseDir "DoubaoASRHelper-Win7-Legacy-Portable.zip"
Compress-Archive -Force -Path @(
  (Join-Path $ReleaseDir "DoubaoASRHelper-win7-legacy-portable.exe"),
  $PortableReadmePath,
  $HelpPath
) -DestinationPath $PortableZipPath

$ZipPath = Join-Path $ReleaseDir "DoubaoASRHelper-Win7-Legacy-Windows.zip"
Compress-Archive -Force -Path @(
  (Join-Path $ReleaseDir "DoubaoASRHelperSetup-win7-legacy.exe"),
  (Join-Path $ReleaseDir "DoubaoASRHelper-win7-legacy-portable.exe"),
  $ReadmePath,
  $HelpPath
) -DestinationPath $ZipPath

Write-Host "Built dist-legacy\DoubaoASRHelper.exe"
Write-Host "Built dist-legacy\DoubaoASRHelperSetup.exe"
Write-Host "Built release\legacy\DoubaoASRHelper-Win7-Legacy-Portable.zip"
Write-Host "Built release\legacy\DoubaoASRHelper-Win7-Legacy-Windows.zip"
