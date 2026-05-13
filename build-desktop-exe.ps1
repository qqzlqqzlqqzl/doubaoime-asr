$ErrorActionPreference = "Stop"

. "$PSScriptRoot\enter-dev.ps1"

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

Write-Host "Built dist\DoubaoASRHelper.exe"
