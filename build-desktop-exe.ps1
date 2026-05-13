$ErrorActionPreference = "Stop"

. "$PSScriptRoot\enter-dev.ps1"

$AppExe = Join-Path $PSScriptRoot "dist\DoubaoASRHelper.exe"
Get-CimInstance Win32_Process |
  Where-Object { $_.ExecutablePath -eq $AppExe } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
  }

uv pip install -e '.[dev]'
uv pip install pyinstaller

pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DoubaoASRHelper `
  --add-binary ".devtools\opus\bin\opus.dll;." `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  doubaoime_asr\desktop_app.py

pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DoubaoASRHelperSetup `
  --add-binary "dist\DoubaoASRHelper.exe;." `
  windows_installer.py

$ReleaseDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "dist\DoubaoASRHelper.exe") (Join-Path $ReleaseDir "DoubaoASRHelper-portable.exe")
Copy-Item -Force (Join-Path $PSScriptRoot "dist\DoubaoASRHelperSetup.exe") (Join-Path $ReleaseDir "DoubaoASRHelperSetup.exe")

$Readme = @(
  "Doubao ASR Helper for Windows",
  "",
  "Recommended files:",
  "- DoubaoASRHelperSetup.exe: installer for the current Windows user. It creates Start Menu and Desktop shortcuts.",
  "- DoubaoASRHelper-portable.exe: portable one-file app. Run it directly without shortcuts.",
  "",
  "Config and credential cache are saved under %APPDATA%\DoubaoASRHelper on first run.",
  "Windows SmartScreen may show an unknown publisher warning because this build is not code-signed."
) -join [Environment]::NewLine
$Readme | Set-Content -Encoding UTF8 (Join-Path $ReleaseDir "README-Windows.txt")

$ZipPath = Join-Path $ReleaseDir "DoubaoASRHelper-Windows.zip"
Compress-Archive -Force -Path @(
  (Join-Path $ReleaseDir "DoubaoASRHelperSetup.exe"),
  (Join-Path $ReleaseDir "DoubaoASRHelper-portable.exe"),
  (Join-Path $ReleaseDir "README-Windows.txt")
) -DestinationPath $ZipPath

Write-Host "Built dist\DoubaoASRHelper.exe"
Write-Host "Built dist\DoubaoASRHelperSetup.exe"
Write-Host "Built release\DoubaoASRHelper-Windows.zip"
