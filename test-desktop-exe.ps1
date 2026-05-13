$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$DistExe = Join-Path $Root "dist\DoubaoASRHelper.exe"
$SetupExe = Join-Path $Root "dist\DoubaoASRHelperSetup.exe"
$PortableExe = Join-Path $Root "release\DoubaoASRHelper-portable.exe"
$ReleaseZip = Join-Path $Root "release\DoubaoASRHelper-Windows.zip"
$ReportsDir = Join-Path $Root "release\test-reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

function Invoke-AppSelfTest {
  param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$ReportName
  )

  if (-not (Test-Path $ExePath)) {
    throw "Missing executable: $ExePath"
  }

  $ReportPath = Join-Path $ReportsDir $ReportName
  Remove-Item -LiteralPath $ReportPath -Force -ErrorAction SilentlyContinue
  $Process = Start-Process $ExePath -ArgumentList @("--self-test", "--self-test-report", $ReportPath) -Wait -PassThru
  if ($Process.ExitCode -ne 0) {
    throw "Self-test failed for $ExePath with exit code $($Process.ExitCode)"
  }
  if (-not (Test-Path $ReportPath)) {
    throw "Self-test report was not written: $ReportPath"
  }

  $Report = Get-Content -Raw -LiteralPath $ReportPath | ConvertFrom-Json
  if (-not $Report.ok) {
    throw "Self-test report says ok=false: $ReportPath"
  }
  return $ReportPath
}

function Stop-AppFromPath {
  param([Parameter(Mandatory = $true)][string]$ExePath)

  Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -eq $ExePath } |
    ForEach-Object {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Remove-WithRetry {
  param([Parameter(Mandatory = $true)][string]$Path)

  for ($Index = 0; $Index -lt 12; $Index++) {
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $Path)) {
      return
    }
  }
  throw "Could not remove path after retries: $Path"
}

Invoke-AppSelfTest -ExePath $DistExe -ReportName "dist-self-test.json" | Out-Host
Invoke-AppSelfTest -ExePath $PortableExe -ReportName "portable-self-test.json" | Out-Host

if (-not (Test-Path $ReleaseZip)) {
  throw "Missing release zip: $ReleaseZip"
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [IO.Compression.ZipFile]::OpenRead($ReleaseZip)
try {
  $Expected = @("DoubaoASRHelperSetup.exe", "DoubaoASRHelper-portable.exe", "README-Windows.txt", "HELP.md")
  foreach ($Name in $Expected) {
    if (-not ($Zip.Entries | Where-Object { $_.FullName -eq $Name -and $_.Length -gt 0 })) {
      throw "Release zip missing required entry: $Name"
    }
  }
}
finally {
  $Zip.Dispose()
}

$TempRoot = (Resolve-Path $env:TEMP).Path
$InstallTarget = Join-Path $TempRoot "DoubaoASRHelperExeTest"
if (-not $InstallTarget.StartsWith($TempRoot)) {
  throw "Unsafe temp target: $InstallTarget"
}
Remove-Item -LiteralPath $InstallTarget -Recurse -Force -ErrorAction SilentlyContinue

$Install = Start-Process $SetupExe -ArgumentList @("--silent", "--no-shortcuts", "--no-run", "--target", $InstallTarget) -Wait -PassThru
if ($Install.ExitCode -ne 0) {
  throw "Installer failed with exit code $($Install.ExitCode)"
}

$InstalledExe = Join-Path $InstallTarget "DoubaoASRHelper.exe"
Invoke-AppSelfTest -ExePath $InstalledExe -ReportName "installed-self-test.json" | Out-Host

$App = Start-Process $InstalledExe -ArgumentList "--hidden" -PassThru
Start-Sleep -Seconds 5
if (-not (Get-Process -Id $App.Id -ErrorAction SilentlyContinue)) {
  throw "Installed app exited during launch smoke test"
}
Stop-Process -Id $App.Id -Force -ErrorAction SilentlyContinue
Stop-AppFromPath -ExePath $InstalledExe
Remove-WithRetry -Path $InstallTarget

Write-Host "Desktop EXE tests passed."
