$ErrorActionPreference = "Stop"

. "$PSScriptRoot\enter-dev.ps1"

uv pip install -e '.[dev]'
python tools/license_stress_test.py `
  --workers 32 `
  --same-code-requests 64 `
  --same-device-requests 64 `
  --verify-requests 200 `
  --invalid-requests 64 `
  --report release/test-reports/license-stress.json
