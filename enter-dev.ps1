$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$DevTools = Join-Path $Root ".devtools"

$env:RUSTUP_HOME = Join-Path $DevTools "rustup"
$env:CARGO_HOME = Join-Path $DevTools "cargo"
$env:PIP_CACHE_DIR = Join-Path $DevTools "pip-cache"
$env:UV_CACHE_DIR = Join-Path $DevTools "uv-cache"
$env:NPM_CONFIG_CACHE = Join-Path $DevTools "npm-cache"
$env:CC = "gcc"
$env:CXX = "g++"
$env:MAKE = "make"
$env:CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER = "gcc"

New-Item -ItemType Directory -Force `
  -Path $env:RUSTUP_HOME, $env:CARGO_HOME, $env:PIP_CACHE_DIR, $env:UV_CACHE_DIR, $env:NPM_CONFIG_CACHE `
  | Out-Null

$localPaths = @(
  (Join-Path $Venv "Scripts"),
  (Join-Path $env:CARGO_HOME "bin"),
  (Join-Path $DevTools "w64devkit\bin"),
  (Join-Path $DevTools "opus\bin")
)

$existingPaths = $env:Path -split ";" | Where-Object { $_ -and ($localPaths -notcontains $_) }
$env:Path = (($localPaths + $existingPaths) -join ";")

$activate = Join-Path $Venv "Scripts\Activate.ps1"
if (Test-Path $activate) {
  . $activate
}

Write-Host "Project dev environment is active."
Write-Host "Python: $((Get-Command python -ErrorAction SilentlyContinue).Source)"
Write-Host "Cargo:  $((Get-Command cargo -ErrorAction SilentlyContinue).Source)"
