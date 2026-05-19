$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$CleanPath = Join-Path $Root ".devtools\samples\simulated-clean-speech.wav"
$DegradedPath = Join-Path $Root ".devtools\samples\simulated-degraded-speech.wav"
$ReportPath = Join-Path $Root "release\test-reports\simulated-audio-processing-asr.json"
$CredentialPath = Join-Path $Root "credentials.json"
$ExePath = Join-Path $Root "dist\asr_bridge.exe"

. "$Root\enter-dev.ps1"

if (-not (Test-Path $ExePath)) {
  throw "Missing packaged bridge executable: $ExePath. Run .\build-desktop-exe.ps1 first."
}

$Args = @(
  "--simulated-audio-processing-test",
  "--simulated-audio-clean", $CleanPath,
  "--simulated-audio-degraded", $DegradedPath,
  "--simulated-audio-report", $ReportPath
)

if (Test-Path $CredentialPath) {
  $Args += @("--credential-path", $CredentialPath)
}

if ($env:DOUBAO_SIMULATED_AUDIO_RUN_ASR -eq "0") {
  Write-Host "Generating simulated audio only. Set DOUBAO_SIMULATED_AUDIO_RUN_ASR=1 or omit it to run ASR."
  $Args += @("--simulated-audio-generate-only")
} else {
  Write-Host "Running packaged bridge simulated audio ASR pipeline test."
}

$Process = Start-Process $ExePath -ArgumentList $Args -Wait -PassThru
if ($Process.ExitCode -ne 0) {
  throw "Simulated audio ASR pipeline test failed with exit code $($Process.ExitCode)"
}

Write-Host "Simulated clean audio: $CleanPath"
Write-Host "Simulated degraded audio: $DegradedPath"
Write-Host "Simulated audio report: $ReportPath"
