from __future__ import annotations

import platform
import sys
import os


def _safe_win32_ver(_release: str = "", *_args, **_kwargs) -> tuple[str, str, str, str]:
    return ("10", "10.0.19045", "SP0", "Multiprocessor Free")


def _safe_uname():
    return platform.uname_result("Windows", "localhost", "10", "10.0.19045", "AMD64")


platform.win32_ver = _safe_win32_ver
platform.uname = _safe_uname
platform.system = lambda: "Windows"
platform.release = lambda: "10"
platform.version = lambda: "10.0.19045"
platform.machine = lambda: "AMD64"
platform.node = lambda: "localhost"

if os.environ.get("PYI_TRACE_TIMEOUT"):
    import faulthandler

    faulthandler.dump_traceback_later(float(os.environ["PYI_TRACE_TIMEOUT"]), repeat=True)

from PyInstaller.__main__ import run


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
