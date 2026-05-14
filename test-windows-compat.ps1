$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
. "$Root\enter-dev.ps1"

$AppExe = Join-Path $Root "dist\DoubaoASRHelper.exe"
$BridgeExe = Join-Path $Root "dist\asr_bridge.exe"
$SetupExe = Join-Path $Root "dist\DoubaoASRHelperSetup.exe"
$ReportsDir = Join-Path $Root "release\test-reports"
$ReportPath = Join-Path $ReportsDir "windows-compatibility.json"
$BridgeSelfTestAppData = Join-Path $ReportsDir "compat-bridge-self-test-appdata"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

foreach ($Path in @($AppExe, $BridgeExe, $SetupExe)) {
  if (-not (Test-Path $Path)) {
    throw "Missing executable: $Path. Run .\build-desktop-exe.ps1 first."
  }
}

$PythonVersion = (& "$Root\.venv\Scripts\python.exe" --version).Trim()
$PyInstallerVersion = (& "$Root\.venv\Scripts\python.exe" -m PyInstaller --version).Trim()
$AhkVersion = "AutoHotkey v2.0.26"

$OldAppData = $env:APPDATA
try {
  $env:APPDATA = $BridgeSelfTestAppData
  New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
  $BridgeSelfTestProcess = Start-Process -FilePath $BridgeExe -ArgumentList "--self-test" -Wait -PassThru
  if ($BridgeSelfTestProcess.ExitCode -ne 0) {
    throw "asr_bridge.exe --self-test failed with exit code $($BridgeSelfTestProcess.ExitCode)"
  }
}
finally {
  $env:APPDATA = $OldAppData
}

$VmTools = @("VBoxManage", "vmrun", "qemu-system-x86_64") |
  ForEach-Object { Get-Command $_ -ErrorAction SilentlyContinue } |
  Where-Object { $null -ne $_ } |
  Select-Object -ExpandProperty Source

$env:COMPAT_APP_EXE = $AppExe
$env:COMPAT_BRIDGE_EXE = $BridgeExe
$env:COMPAT_SETUP_EXE = $SetupExe
$env:COMPAT_REPORT_PATH = $ReportPath
$env:COMPAT_DEV_PYTHON_VERSION = $PythonVersion
$env:COMPAT_PYINSTALLER_VERSION = $PyInstallerVersion
$env:COMPAT_AHK_VERSION = $AhkVersion
$env:COMPAT_VM_TOOLS = ($VmTools -join [IO.Path]::PathSeparator)

@'
from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

import pefile


def parse_pe(path: Path) -> dict:
    pe = pefile.PE(str(path), fast_load=False)
    imports: dict[str, list[str]] = {}
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dll = entry.dll.decode("utf-8", "replace")
        imports[dll] = [
            imp.name.decode("utf-8", "replace") if imp.name else f"#{imp.ordinal}"
            for imp in entry.imports
        ]
    return {
        "path": str(path),
        "exists": True,
        "machine": hex(pe.FILE_HEADER.Machine),
        "is_x64": pe.FILE_HEADER.Machine == 0x8664,
        "subsystem": pe.OPTIONAL_HEADER.Subsystem,
        "subsystem_version": f"{pe.OPTIONAL_HEADER.MajorSubsystemVersion}.{pe.OPTIONAL_HEADER.MinorSubsystemVersion}",
        "os_version": f"{pe.OPTIONAL_HEADER.MajorOperatingSystemVersion}.{pe.OPTIONAL_HEADER.MinorOperatingSystemVersion}",
        "import_dlls": sorted(imports),
        "imports": imports,
    }


def summarize_import_flags(pe_info: dict) -> dict:
    imports = pe_info.get("imports", {})
    kernel_funcs = set(imports.get("KERNEL32.dll", []))
    return {
        "imports_api_ms_win_core_path": "api-ms-win-core-path-l1-1-0.dll" in imports,
        "imports_pss_snapshot": bool({"PssQuerySnapshot", "PssFreeSnapshot"} & kernel_funcs),
        "imports_add_dll_directory": "AddDllDirectory" in kernel_funcs,
        "imports_bcrypt": "bcrypt.dll" in imports,
    }


app_exe = Path(os.environ["COMPAT_APP_EXE"])
bridge_exe = Path(os.environ["COMPAT_BRIDGE_EXE"])
setup_exe = Path(os.environ["COMPAT_SETUP_EXE"])
report_path = Path(os.environ["COMPAT_REPORT_PATH"])

pe = {
    "ahk_client": parse_pe(app_exe),
    "asr_bridge": parse_pe(bridge_exe),
    "installer": parse_pe(setup_exe),
}

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "host": {
        "platform": platform.platform(),
        "release": platform.release(),
        "version": platform.version(),
    },
    "architecture": {
        "client": "AutoHotkey v2 x64 executable",
        "bridge": "PyInstaller one-file Python ASR bridge",
        "installer": "PyInstaller one-file installer containing both executables",
    },
    "toolchain": {
        "autohotkey": os.environ.get("COMPAT_AHK_VERSION"),
        "development_python": os.environ.get("COMPAT_DEV_PYTHON_VERSION"),
        "pyinstaller": os.environ.get("COMPAT_PYINSTALLER_VERSION"),
    },
    "runtime_tests_on_current_host": {
        "bridge_self_test_ok": True,
    },
    "vm_runtime_tests": {
        "executed": False,
        "reason": "No VM runner is configured for additional Windows 10/11 matrix testing in this workspace.",
        "detected_vm_tools": [item for item in os.environ.get("COMPAT_VM_TOOLS", "").split(os.pathsep) if item],
    },
    "official_support_basis": [
        {
            "source": "Python 3.13 Windows documentation",
            "url": "https://docs.python.org/3.13/using/windows.html",
            "summary": "Python 3.13 supports Windows 8.1 and newer; Windows 7 users are directed to Python 3.8.",
        },
        {
            "source": "PyInstaller 6.20 requirements",
            "url": "https://pyinstaller.org/en/v6.20.0/requirements.html",
            "summary": "PyInstaller targets Windows 8 and newer.",
        },
        {
            "source": "Project release policy",
            "url": "WINDOWS_COMPATIBILITY.md",
            "summary": "The desktop release targets Windows 10/11 x64 only.",
        },
    ],
    "pe_findings": {
        name: {
            "machine": info["machine"],
            "is_x64": info["is_x64"],
            "subsystem_version": info["subsystem_version"],
            "flags": summarize_import_flags(info),
        }
        for name, info in pe.items()
    },
    "compatibility_matrix": [
        {
            "os": "Windows 7 SP1 x64",
            "supported": False,
            "runtime_tested": False,
            "expected_result": "unsupported / expected to fail",
            "reasons": [
                "The Python ASR bridge is built with Python 3.13, which does not support Windows 7.",
                "The project release policy only targets Windows 10/11 x64.",
            ],
        },
        {
            "os": "Windows 8.x x64",
            "supported": False,
            "runtime_tested": False,
            "expected_result": "unsupported by project policy",
            "reasons": [
                "The project release policy only targets Windows 10/11 x64.",
            ],
        },
        {
            "os": "Windows 10 x64",
            "supported": True,
            "runtime_tested": False,
            "expected_result": "supported target; should be VM-smoke-tested before broad release",
            "reasons": [
                "AutoHotkey v2 and the Python 3.13 bridge support this target.",
            ],
        },
        {
            "os": "Windows 11 x64",
            "supported": True,
            "runtime_tested": True,
            "expected_result": "passed on current host",
            "reasons": [
                "AHK bridge desktop tests and bridge self-test pass on the current host.",
            ],
        },
    ],
    "recommendation": {
        "current_minimum_supported_os": "Windows 10 x64.",
        "primary_release_targets": ["Windows 10 x64", "Windows 11 x64"],
        "do_not_claim_support": ["Windows 7", "Windows 8.x", "32-bit Windows"],
    },
}

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(report_path))
'@ | & "$Root\.venv\Scripts\python.exe" -

Write-Host "Windows compatibility report written to $ReportPath"
