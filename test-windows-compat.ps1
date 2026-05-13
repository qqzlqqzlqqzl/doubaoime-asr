$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
. "$Root\enter-dev.ps1"

$ExePath = Join-Path $Root "dist\DoubaoASRHelper.exe"
$ReportsDir = Join-Path $Root "release\test-reports"
$ReportPath = Join-Path $ReportsDir "windows-compatibility.json"
$SelfTestReport = Join-Path $ReportsDir "compat-self-test.json"
$TrayTestReport = Join-Path $ReportsDir "compat-tray-self-test.json"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

if (-not (Test-Path $ExePath)) {
  throw "Missing executable: $ExePath. Run .\build-desktop-exe.ps1 first."
}

$PythonVersion = (& "$Root\.venv\Scripts\python.exe" --version).Trim()
$PyInstallerVersion = (& "$Root\.venv\Scripts\python.exe" -m PyInstaller --version).Trim()

$SelfTestProcess = Start-Process $ExePath -ArgumentList @("--self-test", "--self-test-report", $SelfTestReport) -Wait -PassThru
if ($SelfTestProcess.ExitCode -ne 0) {
  throw "Self-test failed with exit code $($SelfTestProcess.ExitCode)"
}

$TrayTestProcess = Start-Process $ExePath -ArgumentList @("--tray-self-test", "--tray-self-test-report", $TrayTestReport) -Wait -PassThru
if ($TrayTestProcess.ExitCode -ne 0) {
  throw "Tray self-test failed with exit code $($TrayTestProcess.ExitCode)"
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

  $env:COMPAT_EXE_PATH = $ExePath
  $env:COMPAT_MEI_DIR = $ExtractDir.FullName
  $env:COMPAT_REPORT_PATH = $ReportPath
  $env:COMPAT_SELF_TEST_REPORT = $SelfTestReport
  $env:COMPAT_TRAY_TEST_REPORT = $TrayTestReport
  $env:COMPAT_DEV_PYTHON_VERSION = $PythonVersion
  $env:COMPAT_PYINSTALLER_VERSION = $PyInstallerVersion
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


exe_path = Path(os.environ["COMPAT_EXE_PATH"])
mei_dir = Path(os.environ["COMPAT_MEI_DIR"])
self_test_report = Path(os.environ["COMPAT_SELF_TEST_REPORT"])
tray_test_report = Path(os.environ["COMPAT_TRAY_TEST_REPORT"])
report_path = Path(os.environ["COMPAT_REPORT_PATH"])

targets = {
    "outer_exe": exe_path,
    "python313": mei_dir / "python313.dll",
    "python3": mei_dir / "python3.dll",
    "vcruntime140": mei_dir / "VCRUNTIME140.dll",
    "vcruntime140_1": mei_dir / "VCRUNTIME140_1.dll",
    "tcl86t": mei_dir / "tcl86t.dll",
    "tk86t": mei_dir / "tk86t.dll",
    "portaudio": mei_dir / "_sounddevice_data" / "portaudio-binaries" / "libportaudio64bit.dll",
    "openssl_ssl": mei_dir / "libssl-3.dll",
    "openssl_crypto": mei_dir / "libcrypto-3.dll",
    "opus": mei_dir / "opus.dll",
}

pe = {}
for name, path in targets.items():
    if path.exists():
        pe[name] = parse_pe(path)
    else:
        pe[name] = {"path": str(path), "exists": False}

python_flags = summarize_import_flags(pe["python313"])
outer_flags = summarize_import_flags(pe["outer_exe"])
self_test = json.loads(self_test_report.read_text(encoding="utf-8"))
tray_test = json.loads(tray_test_report.read_text(encoding="utf-8"))

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "host": {
        "platform": platform.platform(),
        "release": platform.release(),
        "version": platform.version(),
    },
    "toolchain": {
        "development_python": os.environ.get("COMPAT_DEV_PYTHON_VERSION"),
        "pyinstaller": os.environ.get("COMPAT_PYINSTALLER_VERSION"),
        "bundled_python_dll": "python313.dll",
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
            "source": "Microsoft PssQuerySnapshot API documentation",
            "url": "https://learn.microsoft.com/windows/win32/api/processsnapshot/nf-processsnapshot-pssquerysnapshot",
            "summary": "The Process Snapshotting API used by the bundled Python runtime requires Windows 8.1 or newer.",
        },
    ],
    "pe_findings": {
        "outer_exe": {
            "machine": pe["outer_exe"]["machine"],
            "is_x64": pe["outer_exe"]["is_x64"],
            "subsystem_version": pe["outer_exe"]["subsystem_version"],
            "flags": outer_flags,
        },
        "python313": {
            "machine": pe["python313"]["machine"],
            "is_x64": pe["python313"]["is_x64"],
            "subsystem_version": pe["python313"]["subsystem_version"],
            "flags": python_flags,
        },
    },
    "compatibility_matrix": [
        {
            "os": "Windows 7 SP1 x64",
            "supported": False,
            "runtime_tested": False,
            "expected_result": "unsupported / expected to fail",
            "reasons": [
                "Python 3.13 is not officially supported on Windows 7.",
                "PyInstaller 6.20 no longer targets Windows 7.",
                "The bundled Python 3.13 runtime imports newer Windows API sets.",
            ],
        },
        {
            "os": "Windows 8.0 x64",
            "supported": False,
            "runtime_tested": False,
            "expected_result": "unsupported / expected to fail",
            "reasons": [
                "Python 3.13 official Windows support starts at Windows 8.1.",
                "The bundled Python runtime imports PssQuerySnapshot/PssFreeSnapshot, which require Windows 8.1 or newer.",
            ],
        },
        {
            "os": "Windows 8.1 x64",
            "supported": "conditional",
            "runtime_tested": False,
            "expected_result": "runtime should be compatible by Python/PyInstaller policy, but not release-certified without a VM smoke test",
            "reasons": [
                "Python 3.13 documentation supports Windows 8.1 and newer.",
                "The current build is 64-bit only.",
                "No Windows 8.1 VM runtime test was available in this workspace.",
            ],
        },
        {
            "os": "Windows 10 x64",
            "supported": True,
            "runtime_tested": False,
            "expected_result": "supported target; should be VM-smoke-tested before broad release",
            "reasons": [
                "Python 3.13 and PyInstaller support this target.",
            ],
        },
        {
            "os": "Windows 11 x64",
            "supported": True,
            "runtime_tested": True,
            "expected_result": "passed on current host",
            "reasons": [
                "Self-test and tray self-test passed on the current Windows 11 host.",
            ],
        },
    ],
    "recommendation": {
        "current_minimum_supported_os": "Windows 10 x64 recommended; Windows 8.1 x64 is conditional/static-only.",
        "do_not_claim_support": ["Windows 7", "Windows 8.0", "32-bit Windows"],
        "if_win7_or_win8_0_is_required": [
            "Build a separate legacy package with an older Python runtime and matching dependency set.",
            "Expect feature downgrades, especially for modern TLS/crypto, DPI, and global input hooks.",
            "Run real VM smoke tests on the target OS before distribution.",
        ],
    },
}

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(str(report_path))
'@ | & "$Root\.venv\Scripts\python.exe" -
}
finally {
  Stop-Process -Id $App.Id -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

Write-Host "Windows compatibility report written to $ReportPath"
