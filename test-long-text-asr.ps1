$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$SamplePath = Join-Path $Root ".devtools\samples\long-text-volume-stress.wav"
$ReportPath = Join-Path $Root "release\test-reports\long-text-asr.json"
$CredentialPath = Join-Path $Root "credentials.json"
$ExePath = Join-Path $Root "dist\DoubaoASRHelper.exe"

. "$Root\enter-dev.ps1"

if (-not (Test-Path $ExePath)) {
  throw "Missing packaged executable: $ExePath. Run .\build-desktop-exe.ps1 first."
}

$Args = @(
  "--long-text-test",
  "--long-text-audio", $SamplePath,
  "--long-text-report", $ReportPath
)

if (Test-Path $CredentialPath) {
  $Args += @("--credential-path", $CredentialPath)
}

if ($env:DOUBAO_LONG_TEXT_RUN_ASR -eq "0") {
  Write-Host "Generating long text audio sample only. Set DOUBAO_LONG_TEXT_RUN_ASR=1 or omit it to run ASR."
  $Args += @("--long-text-generate-only")
} else {
  Write-Host "Running packaged EXE long text ASR test."
}

$Process = Start-Process $ExePath -ArgumentList $Args -Wait -PassThru
if ($Process.ExitCode -ne 0) {
  throw "Long text EXE test failed with exit code $($Process.ExitCode)"
}

Write-Host "Long text sample: $SamplePath"
Write-Host "Long text report: $ReportPath"
