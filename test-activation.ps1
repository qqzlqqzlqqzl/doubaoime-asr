$ErrorActionPreference = "Stop"

. "$PSScriptRoot\enter-dev.ps1"

uv pip install -e '.[dev]'
pytest tests/test_activation.py
