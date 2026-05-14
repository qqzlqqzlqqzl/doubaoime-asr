from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox


APP_NAME = "Doubao ASR Helper"
APP_EXE = "DoubaoASRHelper.exe"
BRIDGE_EXE = "asr_bridge.exe"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "DoubaoASRHelper"
START_MENU_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs/Doubao ASR Helper"


def bundled_app_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / APP_EXE
    return Path(__file__).resolve().parent / "dist" / APP_EXE


def bundled_bridge_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / BRIDGE_EXE
    return Path(__file__).resolve().parent / "dist" / BRIDGE_EXE


def desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


def create_shortcut(shortcut: Path, target: Path, description: str, arguments: str = "") -> None:
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{str(shortcut).replace("'", "''")}')
$shortcut.TargetPath = '{str(target).replace("'", "''")}'
$shortcut.Arguments = '{arguments.replace("'", "''")}'
$shortcut.WorkingDirectory = '{str(target.parent).replace("'", "''")}'
$shortcut.Description = '{description.replace("'", "''")}'
$shortcut.IconLocation = '{str(target).replace("'", "''")},0'
$shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_running_app() -> None:
    for exe in (APP_EXE, BRIDGE_EXE):
        subprocess.run(
            ["taskkill", "/IM", exe, "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def write_uninstaller(install_dir: Path) -> Path:
    uninstall = install_dir / "uninstall.cmd"
    uninstall.write_text(
        "\r\n".join(
            [
                "@echo off",
                'set "INSTALL_DIR=%~dp0"',
                f'taskkill /IM "{APP_EXE}" /F >nul 2>nul',
                f'taskkill /IM "{BRIDGE_EXE}" /F >nul 2>nul',
                'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Doubao ASR Helper\\Doubao ASR Helper.lnk" >nul 2>nul',
                'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Doubao ASR Helper\\Help.lnk" >nul 2>nul',
                'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Doubao ASR Helper\\Uninstall Doubao ASR Helper.lnk" >nul 2>nul',
                'rmdir "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Doubao ASR Helper" >nul 2>nul',
                'del "%USERPROFILE%\\Desktop\\Doubao ASR Helper.lnk" >nul 2>nul',
                'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\doubaoime-asr.bat" >nul 2>nul',
                'cd /d "%LOCALAPPDATA%"',
                'start "" /min cmd /c "timeout /t 1 /nobreak >nul 2>nul & rmdir /s /q ""%INSTALL_DIR%"""',
                'exit /b 0',
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    return uninstall


def install(target: Path, shortcuts: bool = True) -> Path:
    source = bundled_app_exe()
    if not source.exists():
        raise FileNotFoundError(f"找不到主程序：{source}")
    bridge_source = bundled_bridge_exe()
    if not bridge_source.exists():
        raise FileNotFoundError(f"找不到 ASR bridge：{bridge_source}")

    target.mkdir(parents=True, exist_ok=True)
    stop_running_app()
    target_exe = target / APP_EXE
    target_bridge = target / BRIDGE_EXE
    shutil.copy2(source, target_exe)
    shutil.copy2(bridge_source, target_bridge)

    write_uninstaller(target)
    (target / "install.json").write_text(
        json.dumps(
            {
                "app": APP_NAME,
                "exe": str(target_exe),
                "installed_by": Path(sys.executable).name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if shortcuts:
        create_shortcut(START_MENU_DIR / f"{APP_NAME}.lnk", target_exe, "Doubao ASR voice input helper")
        create_shortcut(START_MENU_DIR / "Help.lnk", target_exe, "Doubao ASR Helper help", "--show-help")
        create_shortcut(desktop_dir() / f"{APP_NAME}.lnk", target_exe, "Doubao ASR voice input helper")
        create_shortcut(START_MENU_DIR / f"Uninstall {APP_NAME}.lnk", target / "uninstall.cmd", f"Uninstall {APP_NAME}")

    return target_exe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Doubao ASR Helper for the current Windows user.")
    parser.add_argument("--target", type=Path, default=INSTALL_DIR)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--no-shortcuts", action="store_true")
    parser.add_argument("--no-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        exe = install(args.target, shortcuts=not args.no_shortcuts)
    except Exception as exc:
        if not args.silent:
            messagebox.showerror(APP_NAME, f"安装失败：{exc}")
        raise

    if args.silent:
        return 0

    if messagebox.askyesno(APP_NAME, f"安装完成：\n{exe}\n\n现在启动吗？"):
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
