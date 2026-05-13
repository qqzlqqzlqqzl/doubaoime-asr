from __future__ import annotations

import os
from pathlib import Path


_DLL_HANDLES = []


def pytest_configure() -> None:
    root = Path(__file__).resolve().parents[1]
    opus_bin = root / ".devtools" / "opus" / "bin"
    if not opus_bin.exists():
        return
    os.environ["PATH"] = str(opus_bin) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        _DLL_HANDLES.append(os.add_dll_directory(str(opus_bin)))
