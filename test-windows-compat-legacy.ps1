$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$LegacyPython = Join-Path $Root ".venv-win7\Scripts\python.exe"
$ExePath = Join-Path $Root "dist-legacy\DoubaoASRHelper.exe"
$ReportsDir = Join-Path $Root "release\test-reports"
$ReportPath = Join-Path $ReportsDir "windows-compatibility-legacy.json"
$SelfTestReport = Join-Path $ReportsDir "legacy-compat-self-test.json"
$TrayTestReport = Join-Path $ReportsDir "legacy-compat-tray-self-test.json"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

if (-not (Test-Path $LegacyPython)) {
  throw "Missing legacy Python: $LegacyPython. Run .\build-desktop-exe-legacy.ps1 first."
}
if (-not (Test-Path $ExePath)) {
  throw "Missing executable: $ExePath. Run .\build-desktop-exe-legacy.ps1 first."
}

$PythonVersion = (& $LegacyPython --version).Trim()
$PyInstallerVersion = (& $LegacyPython -m PyInstaller --version).Trim()

$SelfTestProcess = Start-Process $ExePath -ArgumentList @("--self-test", "--self-test-report", $SelfTestReport) -Wait -PassThru
if ($SelfTestProcess.ExitCode -ne 0) {
  throw "Legacy self-test failed with exit code $($SelfTestProcess.ExitCode)"
}

$TrayTestProcess = Start-Process $ExePath -ArgumentList @("--tray-self-test", "--tray-self-test-report", $TrayTestReport) -Wait -PassThru
if ($TrayTestProcess.ExitCode -ne 0) {
  throw "Legacy tray self-test failed with exit code $($TrayTestProcess.ExitCode)"
}

$VmTools = @("VBoxManage", "vmrun", "qemu-system-x86_64") |
  ForEach-Object { Get-Command $_ -ErrorAction SilentlyContinue } |
  Where-Object { $null -ne $_ } |
  Select-Object -ExpandProperty Source

$TempRoot = [IO.Path]::GetTempPath()
$Before = Get-ChildItem -LiteralPath $TempRoot -Directory -Filter "_MEI*" -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty FullName
$App = Start-Process $ExePath -ArgumentList "--hidden" -PassThru

try {
  Start-Sleep -Seconds 5
  $After = Get-ChildItem -LiteralPath $TempRoot -Directory -Filter "_MEI*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
  $ExtractDir = $After |
    Where-Object { $Before -notcontains $_.FullName } |
    Select-Object -First 1
  if (-not $ExtractDir) {
    $ExtractDir = $After | Select-Object -First 1
  }
  if (-not $ExtractDir) {
    throw "Could not find PyInstaller extraction directory."
  }

  $env:LEGACY_COMPAT_EXE_PATH = $ExePath
  $env:LEGACY_COMPAT_MEI_DIR = $ExtractDir.FullName
  $env:LEGACY_COMPAT_REPORT_PATH = $ReportPath
  $env:LEGACY_COMPAT_SELF_TEST_REPORT = $SelfTestReport
  $env:LEGACY_COMPAT_TRAY_TEST_REPORT = $TrayTestReport
  $env:LEGACY_COMPAT_DEV_PYTHON_VERSION = $PythonVersion
  $env:LEGACY_COMPAT_PYINSTALLER_VERSION = $PyInstallerVersion
  $env:LEGACY_COMPAT_VM_TOOLS = ($VmTools -join [IO.Path]::PathSeparator)

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
    imports = {}
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dll = entry.dll.decode("utf-8", "replace")
        imports[dll] = [
            imp.name.decode("utf-8", "replace") if imp.name else "#{}".format(imp.ordinal)
            for imp in entry.imports
        ]
    return {
        "path": str(path),
        "exists": True,
        "machine": hex(pe.FILE_HEADER.Machine),
        "is_x64": pe.FILE_HEADER.Machine == 0x8664,
        "subsystem": pe.OPTIONAL_HEADER.Subsystem,
        "subsystem_version": "{}.{}".format(
            pe.OPTIONAL_HEADER.MajorSubsystemVersion,
            pe.OPTIONAL_HEADER.MinorSubsystemVersion,
        ),
        "os_version": "{}.{}".format(
            pe.OPTIONAL_HEADER.MajorOperatingSystemVersion,
            pe.OPTIONAL_HEADER.MinorOperatingSystemVersion,
        ),
        "import_dlls": sorted(imports),
        "imports": imports,
    }


def first_existing(root: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        direct = root / pattern
        if direct.exists():
            return direct
        matches = list(root.rglob(pattern))
        if matches:
            return matches[0]
    return None


def summarize_import_flags(pe_info: dict) -> dict:
    imports = pe_info.get("imports", {})
    kernel_funcs = set(imports.get("KERNEL32.dll", []))
    return {
        "imports_api_ms_win_core_path": "api-ms-win-core-path-l1-1-0.dll" in imports,
        "imports_pss_snapshot": bool({"PssQuerySnapshot", "PssFreeSnapshot"} & kernel_funcs),
        "imports_add_dll_directory": "AddDllDirectory" in kernel_funcs,
        "imports_set_default_dll_directories": "SetDefaultDllDirectories" in kernel_funcs,
        "imports_get_system_time_precise": "GetSystemTimePreciseAsFileTime" in kernel_funcs,
        "imports_bcrypt": "bcrypt.dll" in imports,
    }


exe_path = Path(os.environ["LEGACY_COMPAT_EXE_PATH"])
mei_dir = Path(os.environ["LEGACY_COMPAT_MEI_DIR"])
self_test_report = Path(os.environ["LEGACY_COMPAT_SELF_TEST_REPORT"])
tray_test_report = Path(os.environ["LEGACY_COMPAT_TRAY_TEST_REPORT"])
report_path = Path(os.environ["LEGACY_COMPAT_REPORT_PATH"])

target_patterns = {
    "outer_exe": [str(exe_path)],
    "python38": ["python38.dll"],
    "python3": ["python3.dll"],
    "vcruntime140": ["VCRUNTIME140.dll"],
    "vcruntime140_1": ["VCRUNTIME140_1.dll"],
    "tcl86t": ["tcl86t.dll"],
    "tk86t": ["tk86t.dll"],
    "portaudio": ["libportaudio64bit.dll"],
    "opus": ["opus.dll"],
    "pydantic_core": ["_pydantic_core*.pyd"],
}

pe = {}
for name, patterns in target_patterns.items():
    path = Path(patterns[0]) if name == "outer_exe" else first_existing(mei_dir, patterns)
    if path and path.exists():
        pe[name] = parse_pe(path)
    else:
        pe[name] = {"path": str(path) if path else None, "exists": False}

python_flags = summarize_import_flags(pe["python38"]) if pe["python38"]["exists"] else {}
outer_flags = summarize_import_flags(pe["outer_exe"])
self_test = json.loads(self_test_report.read_text(encoding="utf-8"))
tray_test = json.loads(tray_test_report.read_text(encoding="utf-8"))

static_checks = {
    "python38_dll_present": bool(pe["python38"]["exists"]),
    "python38_is_x64": bool(pe["python38"].get("is_x64")),
    "python38_avoids_pss_snapshot_imports": not bool(python_flags.get("imports_pss_snapshot")),
    "python38_avoids_api_ms_win_core_path_import": not bool(python_flags.get("imports_api_ms_win_core_path")),
}

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "host": {
        "platform": platform.platform(),
        "release": platform.release(),
        "version": platform.version(),
    },
    "toolchain": {
        "development_python": os.environ.get("LEGACY_COMPAT_DEV_PYTHON_VERSION"),
        "pyinstaller": os.environ.get("LEGACY_COMPAT_PYINSTALLER_VERSION"),
        "bundled_python_dll": "python38.dll",
    },
    "runtime_tests_on_current_host": {
        "self_test_ok": bool(self_test.get("ok")),
        "tray_test_ok": bool(tray_test.get("ok")),
        "self_test_report": str(self_test_report),
        "tray_test_report": str(tray_test_report),
    },
    "vm_runtime_tests": {
        "executed": False,
        "reason": "No Win7/Win8 VM runner or image was available in this workspace.",
        "detected_vm_tools": [item for item in os.environ.get("LEGACY_COMPAT_VM_TOOLS", "").split(os.pathsep) if item],
    },
    "pe_findings": {
        "outer_exe": {
            "machine": pe["outer_exe"]["machine"],
            "is_x64": pe["outer_exe"]["is_x64"],
            "subsystem_version": pe["outer_exe"]["subsystem_version"],
            "flags": outer_flags,
        },
        "python38": {
            "exists": pe["python38"]["exists"],
            "machine": pe["python38"].get("machine"),
            "is_x64": pe["python38"].get("is_x64"),
            "subsystem_version": pe["python38"].get("subsystem_version"),
            "flags": python_flags,
        },
    },
    "static_checks": static_checks,
    "compatibility_matrix": [
        {
            "os": "Windows 7 SP1 x64",
            "supported": "experimental",
            "runtime_tested": False,
            "expected_result": "legacy package is designed to start, but needs a real VM smoke test before release certification",
            "reasons": [
                "This package bundles Python 3.8 instead of Python 3.13.",
                "Static PE audit avoids the Python 3.13 Win8.1+ PSS imports seen in the main build.",
                "Audio, global hotkeys, TLS, and tray behavior still require real OS testing.",
            ],
        },
        {
            "os": "Windows 8.0 x64",
            "supported": "experimental",
            "runtime_tested": False,
            "expected_result": "legacy package is designed to start, but needs a real VM smoke test before release certification",
            "reasons": [
                "This package bundles Python 3.8 and older dependency pins.",
                "No Windows 8.0 VM runtime test was available in this workspace.",
            ],
        },
        {
            "os": "Windows 8.1 x64",
            "supported": "experimental",
            "runtime_tested": False,
            "expected_result": "legacy package should be more conservative than the main build, but is not VM-certified here",
            "reasons": [
                "Python 3.8 and PyInstaller 4.10 are older than the main build chain.",
                "No Windows 8.1 VM runtime test was available in this workspace.",
            ],
        },
        {
            "os": "Windows 10 x64",
            "supported": True,
            "runtime_tested": False,
            "expected_result": "supported target; use the main package unless a legacy dependency is required",
            "reasons": [
                "The current main package remains the recommended Win10/Win11 build.",
            ],
        },
        {
            "os": "Windows 11 x64",
            "supported": True,
            "runtime_tested": True,
            "expected_result": "passed on current host",
            "reasons": [
                "Legacy self-test and tray self-test passed on the current host.",
            ],
        },
    ],
    "recommendation": {
        "legacy_package_status": "experimental",
        "before_distribution_to_win7_or_win8_users": [
            "Run this exact EXE in clean Windows 7 SP1 x64, Windows 8.0 x64, and Windows 8.1 x64 VMs.",
            "Smoke-test first launch, tray minimize/restore, global hotkeys, microphone recording, ASR network requests, installer, and uninstall.",
            "Keep the legacy package separate from the main Win10/Win11 package.",
        ],
    },
}

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

if not all(static_checks.values()):
    raise SystemExit("Legacy static compatibility checks failed: {}".format(static_checks))

print(str(report_path))
'@ | & $LegacyPython -
}
finally {
  Stop-Process -Id $App.Id -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

Write-Host "Legacy Windows compatibility report written to $ReportPath"
