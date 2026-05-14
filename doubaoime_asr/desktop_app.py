from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import queue
import struct
import sys
import tempfile
import threading
import time
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import sounddevice as sd
import sv_ttk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pynput import keyboard, mouse

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None  # type: ignore[assignment]

if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = str(bundle_dir) + os.pathsep + os.environ.get("PATH", "")

from doubaoime_asr import ASRConfig, ResponseType, transcribe_realtime
from doubaoime_asr.activation import (
    LicenseResult,
    activate_license,
    device_fingerprint,
    load_license_config,
    verify_license,
)
from doubaoime_asr.audio import AudioEncoder
from doubaoime_asr.desktop_help import HELP_TEXT
from doubaoime_asr.transcript import TranscriptAccumulator


APP_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "DoubaoASRHelper"
CONFIG_PATH = APP_CONFIG_DIR / "desktop-config.json"
LEGACY_CONFIG_PATH = Path.home() / ".doubaoime-asr" / "desktop-config.json"
DEFAULT_CREDENTIAL_PATH = APP_CONFIG_DIR / "credentials.json"
STARTUP_BAT = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs/Startup/doubaoime-asr.bat"
HOTKEY_LABELS = {
    "hold_key": "按着说触发键",
    "toggle_key": "自由说触发键",
    "hold_send_key": "按着说+自动发送触发键",
    "cancel_key": "取消键",
    "doubao_hotkey": "豆包快捷键",
}
UI_BG = "#f4f7fb"
UI_CARD = "#ffffff"
UI_BORDER = "#dbe3ef"
UI_TEXT = "#111827"
UI_MUTED = "#64748b"
UI_PRIMARY = "#2563eb"
UI_PRIMARY_DARK = "#1d4ed8"
UI_PRIMARY_SOFT = "#eff6ff"
UI_SUCCESS = "#15803d"
UI_SUCCESS_SOFT = "#ecfdf3"
UI_INPUT = "#fbfdff"
UI_TOGGLE_OFF = "#f8fafc"
UI_TOGGLE_OFF_ACTIVE = "#e2e8f0"
DELAY_SPECS = {
    "insert_delay_ms": (0, 1500, 50),
    "clipboard_restore_delay_ms": (500, 2000, 50),
    "auto_send_delay_ms": (0, 500, 50),
}
BASE_TK_SCALING = 96 / 72
DEFAULT_WINDOW_WIDTH = 760
DEFAULT_WINDOW_HEIGHT = 520
MIN_WINDOW_WIDTH = 560
MIN_WINDOW_HEIGHT = 420
MAIN_WINDOW_TITLE = "豆包 ASR 助手"
FLOAT_BASE_WIDTH = 760
FLOAT_MIN_WIDTH = 560
FLOAT_MAX_WIDTH = 960
FLOAT_MAX_LINES = 12
APP_ICON_RELATIVE_PATH = Path("assets") / "app.ico"
APP_USER_MODEL_ID = "DoubaoASRHelper.Desktop"
SINGLE_INSTANCE_MUTEX_NAME = "Local\\DoubaoASRHelper.SingleInstance"
_DPI_AWARENESS_CONFIGURED = False
MAX_CLIPBOARD_SNAPSHOT_BYTES = 64 * 1024 * 1024


async def _run_blocking(func: Callable, *args):
    to_thread = getattr(asyncio, "to_thread", None)
    if to_thread is not None:
        return await to_thread(func, *args)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


def app_icon_path() -> Path | None:
    package_icon = Path(__file__).resolve().parent / APP_ICON_RELATIVE_PATH
    if package_icon.exists():
        return package_icon
    if getattr(sys, "frozen", False):
        bundled_icon = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "doubaoime_asr" / APP_ICON_RELATIVE_PATH
        if bundled_icon.exists():
            return bundled_icon
    return None


def snap_delay_value(value: int | float, minimum: int, maximum: int, step: int) -> int:
    snapped = int(round(float(value)))
    snapped = max(minimum, min(maximum, snapped))
    if step > 1:
        snapped = minimum + int(math.floor(((snapped - minimum) / step) + 0.5)) * step
    return max(minimum, min(maximum, snapped))


def configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


class SingleInstanceGuard:
    ERROR_ALREADY_EXISTS = 183
    SW_RESTORE = 9

    def __init__(self, mutex_name: str = SINGLE_INSTANCE_MUTEX_NAME, window_title: str = MAIN_WINDOW_TITLE) -> None:
        self.mutex_name = mutex_name
        self.window_title = window_title
        self.handle: int | None = None
        self.already_running = False

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "win32" and wintypes is not None and hasattr(ctypes, "windll")

    def acquire(self) -> bool:
        if not self.is_supported():
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        if not handle:
            raise ctypes.WinError()
        self.handle = int(handle)
        self.already_running = kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS
        return not self.already_running

    def release(self) -> None:
        if self.handle is None or not self.is_supported():
            return
        try:
            ctypes.windll.kernel32.CloseHandle(self.handle)
        except OSError:
            pass
        self.handle = None

    def signal_existing_instance(self) -> bool:
        hwnd = find_main_window_by_title(self.window_title, exclude_pid=os.getpid())
        if hwnd is None:
            return False
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, self.SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True
        except (AttributeError, OSError):
            return False


def find_main_window_by_title(title: str, exclude_pid: int | None = None) -> int | None:
    if sys.platform != "win32" or wintypes is None or not hasattr(ctypes, "windll"):
        return None

    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found_hwnd = ctypes.c_void_p()

    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    def enum_window(hwnd: int, _lparam: int) -> bool:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if exclude_pid is not None and process_id.value == exclude_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value == title:
            found_hwnd.value = int(hwnd)
            return False
        return True

    callback = enum_proc_type(enum_window)
    user32.EnumWindows(callback, 0)
    return int(found_hwnd.value) if found_hwnd.value else None


if sys.platform == "win32" and wintypes is not None:
    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class _NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
        ]


class WindowsTrayIcon:
    ACTION_SHOW = "show"
    ACTION_HIDE = "hide"
    ACTION_OPEN_CONFIG = "open_config"
    ACTION_QUIT = "quit"

    _NIM_ADD = 0x00000000
    _NIM_DELETE = 0x00000002
    _NIF_MESSAGE = 0x00000001
    _NIF_ICON = 0x00000002
    _NIF_TIP = 0x00000004
    _WM_CLOSE = 0x0010
    _WM_COMMAND = 0x0111
    _WM_DESTROY = 0x0002
    _WM_NULL = 0x0000
    _WM_CONTEXTMENU = 0x007B
    _WM_USER = 0x0400
    _WM_TRAYICON = _WM_USER + 20
    _WM_LBUTTONUP = 0x0202
    _WM_LBUTTONDBLCLK = 0x0203
    _WM_RBUTTONUP = 0x0205
    _IMAGE_ICON = 1
    _LR_DEFAULTSIZE = 0x00000040
    _LR_LOADFROMFILE = 0x00000010
    _IDI_APPLICATION = 32512
    _MF_STRING = 0x00000000
    _MF_SEPARATOR = 0x00000800
    _TPM_RIGHTBUTTON = 0x0002

    _MENU_SHOW = 1001
    _MENU_HIDE = 1002
    _MENU_OPEN_CONFIG = 1003
    _MENU_QUIT = 1004

    def __init__(
        self,
        tooltip: str,
        action_callback: Callable[[str], None],
        icon_path: str | Path | None = None,
    ) -> None:
        self.tooltip = tooltip[:127]
        self.action_callback = action_callback
        self.icon_path = Path(icon_path) if icon_path else None
        self.last_error: str | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._started_ok = False
        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._hicon_owned = False
        self.icon_loaded_from_file = False
        self.loaded_icon_path: str | None = None
        self.icon_load_error: str | None = None
        self._hinstance: int | None = None
        self._class_name = f"DoubaoASRHelperTrayWindow-{os.getpid()}-{id(self)}"
        self._window_proc = None

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "win32" and wintypes is not None and hasattr(ctypes, "windll")

    def start(self, wait: bool = False, timeout: float = 2.0) -> bool:
        if not self.is_supported():
            self.last_error = "Windows system tray is only available on win32."
            self._ready.set()
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_message_loop, name="DoubaoASRTray", daemon=True)
        self._thread.start()
        return self.wait_until_ready(timeout) if wait else True

    def wait_until_ready(self, timeout: float = 2.0) -> bool:
        self._ready.wait(timeout)
        return self._started_ok

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        if not self.is_supported():
            return
        hwnd = self._hwnd
        if hwnd:
            try:
                ctypes.windll.user32.PostMessageW(hwnd, self._WM_CLOSE, 0, 0)
            except OSError:
                pass
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def _run_message_loop(self) -> None:
        assert wintypes is not None
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            self._configure_win32_signatures()
            self._hinstance = kernel32.GetModuleHandleW(None)
            self._window_proc = _WNDPROC(self._wnd_proc)
            window_class = _WNDCLASSW()
            window_class.lpfnWndProc = self._window_proc
            window_class.hInstance = self._hinstance
            window_class.lpszClassName = self._class_name
            if not user32.RegisterClassW(ctypes.byref(window_class)):
                raise ctypes.WinError()

            hwnd = user32.CreateWindowExW(
                0,
                self._class_name,
                "Doubao ASR Helper Tray",
                0,
                0,
                0,
                0,
                0,
                None,
                None,
                self._hinstance,
                None,
            )
            if not hwnd:
                raise ctypes.WinError()
            self._hwnd = hwnd
            self._add_icon(hwnd)
            self._started_ok = True
            self._ready.set()

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.last_error = repr(exc)
            self._ready.set()
        finally:
            self._delete_icon()
            self._destroy_icon()
            if self._hinstance:
                try:
                    user32.UnregisterClassW(self._class_name, self._hinstance)
                except OSError:
                    pass
            self._hwnd = None

    def _configure_win32_signatures(self) -> None:
        assert wintypes is not None
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.LPVOID,
        ]
        user32.TrackPopupMenu.restype = wintypes.BOOL
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.DestroyMenu.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadIconW.restype = wintypes.HICON
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL

        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        user32 = ctypes.windll.user32
        try:
            if msg == self._WM_TRAYICON:
                event = int(lparam)
                if event in {self._WM_LBUTTONUP, self._WM_LBUTTONDBLCLK}:
                    self.action_callback(self.ACTION_SHOW)
                    return 0
                if event in {self._WM_RBUTTONUP, self._WM_CONTEXTMENU}:
                    self._show_menu(hwnd)
                    return 0
            if msg == self._WM_COMMAND:
                command = int(wparam) & 0xFFFF
                action = {
                    self._MENU_SHOW: self.ACTION_SHOW,
                    self._MENU_HIDE: self.ACTION_HIDE,
                    self._MENU_OPEN_CONFIG: self.ACTION_OPEN_CONFIG,
                    self._MENU_QUIT: self.ACTION_QUIT,
                }.get(command)
                if action:
                    self.action_callback(action)
                    return 0
            if msg == self._WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == self._WM_DESTROY:
                self._delete_icon()
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.last_error = repr(exc)
        return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

    def _show_menu(self, hwnd: int) -> None:
        assert wintypes is not None
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError()
        try:
            for item_id, text in (
                (self._MENU_SHOW, "显示主窗口"),
                (self._MENU_HIDE, "隐藏窗口"),
                (self._MENU_OPEN_CONFIG, "打开配置目录"),
            ):
                if not user32.AppendMenuW(menu, self._MF_STRING, item_id, text):
                    raise ctypes.WinError()
            user32.AppendMenuW(menu, self._MF_SEPARATOR, 0, None)
            if not user32.AppendMenuW(menu, self._MF_STRING, self._MENU_QUIT, "退出"):
                raise ctypes.WinError()
            point = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError()
            user32.SetForegroundWindow(hwnd)
            user32.TrackPopupMenu(menu, self._TPM_RIGHTBUTTON, point.x, point.y, 0, hwnd, None)
            user32.PostMessageW(hwnd, self._WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)

    def _load_icon(self) -> int:
        assert wintypes is not None
        user32 = ctypes.windll.user32
        self.icon_loaded_from_file = False
        self.loaded_icon_path = None
        self.icon_load_error = None
        if self.icon_path and self.icon_path.exists():
            hicon = user32.LoadImageW(
                None,
                str(self.icon_path),
                self._IMAGE_ICON,
                0,
                0,
                self._LR_LOADFROMFILE | self._LR_DEFAULTSIZE,
            )
            if hicon:
                self._hicon_owned = True
                self.icon_loaded_from_file = True
                self.loaded_icon_path = str(self.icon_path)
                return int(hicon)
            self.icon_load_error = f"LoadImageW failed for {self.icon_path}: {ctypes.WinError()!r}"
        elif self.icon_path:
            self.icon_load_error = f"Icon file does not exist: {self.icon_path}"
        hicon = user32.LoadIconW(None, ctypes.c_wchar_p(self._IDI_APPLICATION))
        self._hicon_owned = False
        if not hicon:
            raise ctypes.WinError()
        return int(hicon)

    def _add_icon(self, hwnd: int) -> None:
        assert wintypes is not None
        self._hicon = self._load_icon()
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = hwnd
        data.uID = 1
        data.uFlags = self._NIF_MESSAGE | self._NIF_ICON | self._NIF_TIP
        data.uCallbackMessage = self._WM_TRAYICON
        data.hIcon = self._hicon
        data.szTip = self.tooltip
        if not ctypes.windll.shell32.Shell_NotifyIconW(self._NIM_ADD, ctypes.byref(data)):
            raise ctypes.WinError()

    def _delete_icon(self) -> None:
        if not self.is_supported() or not self._hwnd:
            return
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self._hwnd
        data.uID = 1
        try:
            ctypes.windll.shell32.Shell_NotifyIconW(self._NIM_DELETE, ctypes.byref(data))
        except OSError:
            pass

    def _destroy_icon(self) -> None:
        if not self.is_supported() or not self._hicon or not self._hicon_owned:
            return
        try:
            ctypes.windll.user32.DestroyIcon(self._hicon)
        except OSError:
            pass
        self._hicon = None


@dataclass
class DesktopConfig:
    hold_key: str = "rctrl"
    toggle_key: str = "xbutton1"
    hold_send_key: str = "lctrl+lwin"
    cancel_key: str = "esc"
    doubao_hotkey: str = "ctrl+d"
    insert_delay_ms: int = 300
    clipboard_restore_delay_ms: int = 500
    auto_send_delay_ms: int = 50
    protect_clipboard: bool = True
    startup: bool = False
    credential_path: str = str(DEFAULT_CREDENTIAL_PATH)


RESETTABLE_CONFIG_FIELDS = (
    "hold_key",
    "toggle_key",
    "hold_send_key",
    "cancel_key",
    "doubao_hotkey",
    "insert_delay_ms",
    "clipboard_restore_delay_ms",
    "auto_send_delay_ms",
    "protect_clipboard",
    "startup",
)


def resolve_user_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = APP_CONFIG_DIR / path
    return path


def normalize_config(config: DesktopConfig) -> DesktopConfig:
    config.credential_path = str(resolve_user_path(config.credential_path))
    defaults = DesktopConfig()
    for field in ("hold_key", "toggle_key", "hold_send_key", "cancel_key"):
        if not idle_start_hotkey_allowed(parse_hotkey(getattr(config, field))):
            setattr(config, field, getattr(defaults, field))
    for field, (minimum, maximum, step) in DELAY_SPECS.items():
        setattr(config, field, snap_delay_value(getattr(config, field), minimum, maximum, step))
    return config


def reset_config_to_defaults(config: DesktopConfig, preserve_credential_path: bool = True) -> DesktopConfig:
    defaults = DesktopConfig()
    credential_path = config.credential_path if preserve_credential_path else defaults.credential_path
    reset = DesktopConfig(**{**asdict(defaults), "credential_path": credential_path})
    return normalize_config(reset)


def hotkey_conflict_from_values(values: dict[str, str]) -> str | None:
    seen: dict[frozenset[str], str] = {}
    for field, label in HOTKEY_LABELS.items():
        value = values[field].strip()
        parsed = parse_hotkey(value)
        if not parsed:
            return f"{label} 不能为空。"
        if field in {"hold_key", "toggle_key", "hold_send_key", "cancel_key"} and not idle_start_hotkey_allowed(parsed):
            return f"{label} 不能只用普通字母或数字，避免和打字输入冲突。请使用 Ctrl/Alt/Win、鼠标侧键或功能键组合。"
        if parsed in seen:
            return f"{label} 与 {seen[parsed]} 使用了同一个快捷键：{value}"
        seen[parsed] = label
        system_conflict = system_hotkey_conflict(parsed)
        if system_conflict:
            return f"{label} 可能不可用：{system_conflict}"
    return None


def load_config() -> DesktopConfig:
    path = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
    if not path.exists():
        return normalize_config(DesktopConfig())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return normalize_config(DesktopConfig(**{**asdict(DesktopConfig()), **data}))
    except Exception:
        return normalize_config(DesktopConfig())


def save_config(config: DesktopConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_startup(config.startup)


def startup_executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "doubaoime-asr-desktop.exe"


def sync_startup(enabled: bool) -> None:
    if enabled:
        exe = startup_executable_path()
        STARTUP_BAT.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_BAT.write_text(f'@echo off\r\nstart "" "{exe}" --hidden\r\n', encoding="utf-8")
    else:
        STARTUP_BAT.unlink(missing_ok=True)


ALIASES = {
    "right ctrl": "rctrl",
    "右ctrl": "rctrl",
    "右 ctrl": "rctrl",
    "rctrl": "rctrl",
    "left ctrl": "lctrl",
    "左ctrl": "lctrl",
    "左 ctrl": "lctrl",
    "lctrl": "lctrl",
    "ctrl": "ctrl",
    "control": "ctrl",
    "right win": "rwin",
    "右win": "rwin",
    "右 win": "rwin",
    "rwin": "rwin",
    "left win": "lwin",
    "左win": "lwin",
    "左 win": "lwin",
    "lwin": "lwin",
    "win": "win",
    "cmd": "win",
    "left alt": "lalt",
    "左alt": "lalt",
    "左 alt": "lalt",
    "lalt": "lalt",
    "right alt": "ralt",
    "右alt": "ralt",
    "右 alt": "ralt",
    "ralt": "ralt",
    "alt": "alt",
    "atl": "alt",
    "alt gr": "ralt",
    "altgr": "ralt",
    "delete": "del",
    "left shift": "lshift",
    "左shift": "lshift",
    "左 shift": "lshift",
    "lshift": "lshift",
    "right shift": "rshift",
    "右shift": "rshift",
    "右 shift": "rshift",
    "rshift": "rshift",
    "shift": "shift",
    "鼠标侧键1": "xbutton1",
    "鼠标侧键 1": "xbutton1",
    "mouse x1": "xbutton1",
    "x1": "xbutton1",
    "xbutton1": "xbutton1",
    "鼠标侧键2": "xbutton2",
    "鼠标侧键 2": "xbutton2",
    "mouse x2": "xbutton2",
    "x2": "xbutton2",
    "xbutton2": "xbutton2",
}
HOTKEY_DISPLAY_NAMES = {
    "lctrl": "左 Ctrl",
    "rctrl": "右 Ctrl",
    "ctrl": "Ctrl",
    "lalt": "左 Alt",
    "ralt": "右 Alt",
    "alt": "Alt",
    "lshift": "左 Shift",
    "rshift": "右 Shift",
    "shift": "Shift",
    "lwin": "左 Win",
    "rwin": "右 Win",
    "win": "Win",
    "xbutton1": "鼠标侧键 1",
    "xbutton2": "鼠标侧键 2",
    "middle": "鼠标中键",
    "esc": "Esc",
    "enter": "Enter",
    "tab": "Tab",
    "space": "Space",
    "del": "Delete",
}
MODIFIER_KEYS = {"lctrl", "rctrl", "ctrl", "lalt", "ralt", "alt", "lshift", "rshift", "shift", "lwin", "rwin", "win"}
MODIFIER_FAMILIES = (
    frozenset({"lctrl", "rctrl", "ctrl"}),
    frozenset({"lalt", "ralt", "alt"}),
    frozenset({"lshift", "rshift", "shift"}),
    frozenset({"lwin", "rwin", "win"}),
)
HOLD_RECORDING_MODES = {"hold", "hold_send"}
MOUSE_HOTKEYS = {"xbutton1", "xbutton2", "middle"}
CONTROL_HOTKEYS = {"esc", "enter", "tab", "space"}
SAFE_SINGLE_MODIFIER_START_KEYS = {"rctrl"}
VK_KEYS = {
    "esc": 0x1B,
    "tab": 0x09,
    "enter": 0x0D,
    "space": 0x20,
    "del": 0x2E,
}
RESERVED_HOTKEYS = {
    frozenset({"alt", "tab"}): "Alt+Tab 是 Windows 切换窗口快捷键。",
    frozenset({"alt", "f4"}): "Alt+F4 是 Windows 关闭窗口快捷键。",
    frozenset({"ctrl", "alt", "del"}): "Ctrl+Alt+Del 是 Windows 安全快捷键。",
    frozenset({"win", "l"}): "Win+L 是 Windows 锁屏快捷键。",
    frozenset({"win", "d"}): "Win+D 是 Windows 显示桌面快捷键。",
    frozenset({"win", "tab"}): "Win+Tab 是 Windows 任务视图快捷键。",
}


def parse_hotkey(value: str) -> frozenset[str]:
    parts = [part.strip().lower() for part in value.replace("＋", "+").split("+") if part.strip()]
    return frozenset(ALIASES.get(part, part) for part in parts)


def generic_hotkey(keys: Iterable[str]) -> frozenset[str]:
    generic = set(keys)
    if "lctrl" in generic or "rctrl" in generic:
        generic.discard("lctrl")
        generic.discard("rctrl")
        generic.add("ctrl")
    if "lalt" in generic or "ralt" in generic:
        generic.discard("lalt")
        generic.discard("ralt")
        generic.add("alt")
    if "lshift" in generic or "rshift" in generic:
        generic.discard("lshift")
        generic.discard("rshift")
        generic.add("shift")
    if "lwin" in generic or "rwin" in generic:
        generic.discard("lwin")
        generic.discard("rwin")
        generic.add("win")
    return frozenset(generic)


def hotkey_vk(keys: frozenset[str]) -> int | None:
    normal_keys = [key for key in keys if key not in MODIFIER_KEYS]
    if len(normal_keys) != 1:
        return None
    key = normal_keys[0]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return VK_KEYS.get(key)


def hotkey_modifiers(keys: frozenset[str]) -> int:
    generic = generic_hotkey(keys)
    modifiers = 0
    if "alt" in generic:
        modifiers |= 0x0001
    if "ctrl" in generic:
        modifiers |= 0x0002
    if "shift" in generic:
        modifiers |= 0x0004
    if "win" in generic:
        modifiers |= 0x0008
    return modifiers


def system_hotkey_conflict(keys: frozenset[str]) -> str | None:
    generic = generic_hotkey(keys)
    reserved = RESERVED_HOTKEYS.get(generic)
    if reserved:
        return reserved
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        return None
    if keys & MOUSE_HOTKEYS:
        return None
    vk = hotkey_vk(generic)
    modifiers = hotkey_modifiers(generic)
    if vk is None or not modifiers:
        return None
    hotkey_id = 0xD0B0
    user32 = ctypes.windll.user32
    if user32.RegisterHotKey(None, hotkey_id, modifiers | 0x4000, vk):
        user32.UnregisterHotKey(None, hotkey_id)
        return None
    return "这个组合键已被 Windows 或其他正在运行的软件占用。"


def is_plain_text_key(name: str) -> bool:
    return len(name) == 1 and name.isprintable()


def idle_start_hotkey_allowed(keys: frozenset[str]) -> bool:
    if not keys:
        return False
    if len(keys) == 1:
        key = next(iter(keys))
        if key in SAFE_SINGLE_MODIFIER_START_KEYS | MOUSE_HOTKEYS | CONTROL_HOTKEYS:
            return True
        if key in MODIFIER_KEYS:
            return False
        if key.startswith("f") and key[1:].isdigit():
            return True
        return not is_plain_text_key(key)
    if keys & (MODIFIER_KEYS | MOUSE_HOTKEYS | CONTROL_HOTKEYS):
        return True
    if any(key.startswith("f") and key[1:].isdigit() for key in keys):
        return True
    return not all(is_plain_text_key(key) for key in keys)


def format_hotkey(keys: Iterable[str]) -> str:
    order = ["lctrl", "rctrl", "ctrl", "lalt", "ralt", "alt", "lshift", "rshift", "shift", "lwin", "rwin", "win"]
    unique = list(dict.fromkeys(keys))
    unique.sort(key=lambda item: order.index(item) if item in order else 99)
    return "+".join(unique)


def canonical_hotkey_value(value: str) -> str:
    return format_hotkey(parse_hotkey(value))


def display_hotkey_value(value: str | Iterable[str]) -> str:
    if isinstance(value, str):
        keys = parse_hotkey(value)
    else:
        keys = frozenset(value)
    canonical = format_hotkey(keys)
    if not canonical:
        return ""
    return " + ".join(HOTKEY_DISPLAY_NAMES.get(part, part.upper() if len(part) == 1 else part) for part in canonical.split("+"))


def default_hotkey_summary() -> str:
    defaults = DesktopConfig()
    return " / ".join(display_hotkey_value(getattr(defaults, field)) for field in HOTKEY_LABELS)


def key_name(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    key_map = {
        keyboard.Key.ctrl: "ctrl",
        keyboard.Key.ctrl_l: "lctrl",
        keyboard.Key.ctrl_r: "rctrl",
        keyboard.Key.cmd: "win",
        keyboard.Key.cmd_l: "lwin",
        keyboard.Key.cmd_r: "rwin",
        keyboard.Key.alt: "alt",
        keyboard.Key.alt_l: "lalt",
        keyboard.Key.alt_r: "ralt",
        keyboard.Key.alt_gr: "ralt",
        keyboard.Key.shift: "shift",
        keyboard.Key.shift_l: "lshift",
        keyboard.Key.shift_r: "rshift",
        keyboard.Key.esc: "esc",
        keyboard.Key.enter: "enter",
        keyboard.Key.space: "space",
        keyboard.Key.tab: "tab",
        keyboard.Key.delete: "del",
    }
    if key in key_map:
        return key_map[key]
    name = getattr(key, "name", None)
    if name and name.startswith("f"):
        return name
    char = getattr(key, "char", None)
    return char.lower() if char else None


def mouse_name(button: mouse.Button) -> str | None:
    return {
        mouse.Button.x1: "xbutton1",
        mouse.Button.x2: "xbutton2",
        mouse.Button.middle: "middle",
    }.get(button)


def active_matches(active: set[str], target: frozenset[str]) -> bool:
    if not target:
        return False
    expanded = set(active)
    if "lctrl" in active or "rctrl" in active:
        expanded.add("ctrl")
    if "lwin" in active or "rwin" in active:
        expanded.add("win")
    if "lalt" in active or "ralt" in active:
        expanded.add("alt")
    if "lshift" in active or "rshift" in active:
        expanded.add("shift")
    return target.issubset(expanded)


def active_matches_exact(active: set[str], target: frozenset[str]) -> bool:
    if len(active) != len(target):
        return False
    if not active_matches(active, target):
        return False
    return generic_hotkey(active) == generic_hotkey(target)


def key_release_variants(name: str) -> frozenset[str]:
    for family in MODIFIER_FAMILIES:
        if name in family:
            return family
    return frozenset({name})


def target_contains_released_key(target: frozenset[str], released_name: str) -> bool:
    return bool(target & key_release_variants(released_name))


def should_stop_hold_on_release(mode: str | None, released_name: str, active_keys: set[str], config: DesktopConfig) -> bool:
    if mode == "hold":
        target = parse_hotkey(config.hold_key)
    elif mode == "hold_send":
        target = parse_hotkey(config.hold_send_key)
    else:
        return False
    if target_contains_released_key(target, released_name):
        return True
    return not active_matches(active_keys, target)


def should_show_recognition_float(recording_mode: str | None, pending_mode: str | None) -> bool:
    if recording_mode is not None:
        return True
    return pending_mode == "toggle"


def should_show_stop_state_in_float(mode: str | None, cancelled: bool) -> bool:
    return cancelled or mode == "toggle"


def is_current_recording_session(session_id: int, current_session_id: int) -> bool:
    return session_id == current_session_id


def idle_start_mode_for_active_keys(name: str, active_keys: set[str], config: DesktopConfig) -> str | None:
    toggle_key = parse_hotkey(config.toggle_key)
    hold_send_key = parse_hotkey(config.hold_send_key)
    hold_key = parse_hotkey(config.hold_key)
    if idle_start_hotkey_allowed(hold_send_key) and name in hold_send_key and active_matches_exact(active_keys, hold_send_key):
        return "hold_send"
    if idle_start_hotkey_allowed(hold_key) and name in hold_key and active_matches_exact(active_keys, hold_key):
        return "hold"
    if idle_start_hotkey_allowed(toggle_key) and name in toggle_key and active_matches_exact(active_keys, toggle_key):
        return "toggle"
    return None


def configure_process_dpi_awareness() -> None:
    global _DPI_AWARENESS_CONFIGURED
    if _DPI_AWARENESS_CONFIGURED or sys.platform != "win32":
        return
    _DPI_AWARENESS_CONFIGURED = True
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


@dataclass
class ClipboardFormatData:
    format_id: int
    name: str
    data: bytes


@dataclass
class ClipboardSnapshot:
    formats: list[ClipboardFormatData]
    skipped_formats: list[dict[str, object]]
    text_fallback: str = ""
    native: bool = False
    error: str | None = None

    def format_ids(self) -> set[int]:
        return {item.format_id for item in self.formats}

    def format_names(self) -> list[str]:
        return [item.name for item in self.formats]

    def data_by_format(self) -> dict[int, bytes]:
        return {item.format_id: item.data for item in self.formats}


STANDARD_CLIPBOARD_FORMAT_NAMES = {
    1: "CF_TEXT",
    2: "CF_BITMAP",
    3: "CF_METAFILEPICT",
    4: "CF_SYLK",
    5: "CF_DIF",
    6: "CF_TIFF",
    7: "CF_OEMTEXT",
    8: "CF_DIB",
    13: "CF_UNICODETEXT",
    14: "CF_ENHMETAFILE",
    15: "CF_HDROP",
    16: "CF_LOCALE",
    17: "CF_DIBV5",
}


def clipboard_format_name(format_id: int) -> str:
    if format_id in STANDARD_CLIPBOARD_FORMAT_NAMES:
        return STANDARD_CLIPBOARD_FORMAT_NAMES[format_id]
    if sys.platform == "win32" and hasattr(ctypes, "windll"):
        buffer = ctypes.create_unicode_buffer(256)
        try:
            if ctypes.windll.user32.GetClipboardFormatNameW(format_id, buffer, len(buffer)):
                return buffer.value
        except OSError:
            pass
    return f"FORMAT_{format_id}"


def open_windows_clipboard(hwnd: int | None = None, timeout: float = 1.0) -> None:
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        raise RuntimeError("Windows clipboard APIs are not available.")
    user32 = ctypes.windll.user32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    deadline = time.time() + timeout
    owner = ctypes.c_void_p(hwnd or 0)
    while time.time() < deadline:
        if user32.OpenClipboard(owner):
            return
        time.sleep(0.025)
    raise ctypes.WinError()


def allocate_global_copy(data: bytes) -> int:
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    handle = kernel32.GlobalAlloc(0x0002, len(data))
    if not handle:
        raise ctypes.WinError()
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError()
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    return int(handle)


def set_windows_clipboard_formats(format_payloads: dict[int, bytes], hwnd: int | None = None) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    open_windows_clipboard(hwnd)
    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError()
        for format_id, payload in format_payloads.items():
            handle = allocate_global_copy(payload)
            if not user32.SetClipboardData(format_id, ctypes.c_void_p(handle)):
                kernel32.GlobalFree(ctypes.c_void_p(handle))
                raise ctypes.WinError()
    finally:
        user32.CloseClipboard()


def read_windows_clipboard_format(format_id: int, hwnd: int | None = None) -> bytes | None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    open_windows_clipboard(hwnd)
    try:
        handle = user32.GetClipboardData(format_id)
        if not handle:
            return None
        size = int(kernel32.GlobalSize(handle))
        if size <= 0 or size > MAX_CLIPBOARD_SNAPSHOT_BYTES:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.string_at(pointer, size)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def build_test_dib_payload() -> bytes:
    header = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0)
    return header + b"\x00\x00\xff\x00"


def build_test_hdrop_payload(path: Path) -> bytes:
    encoded_path = str(path).encode("utf-16le")
    return struct.pack("<IiiII", 20, 0, 0, 0, 1) + encoded_path + b"\x00\x00\x00\x00"


class Clipboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root

    def get_text(self) -> str:
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    def set_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def create_snapshot(self) -> ClipboardSnapshot:
        text_fallback = self.get_text()
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return ClipboardSnapshot([], [], text_fallback=text_fallback, native=False)

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.EnumClipboardFormats.argtypes = [ctypes.c_uint]
        user32.EnumClipboardFormats.restype = ctypes.c_uint
        user32.GetClipboardData.argtypes = [ctypes.c_uint]
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
        kernel32.GlobalSize.restype = ctypes.c_size_t
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_bool

        formats: list[ClipboardFormatData] = []
        skipped: list[dict[str, object]] = []
        try:
            open_windows_clipboard(self.root.winfo_id())
            try:
                current = 0
                while True:
                    current = int(user32.EnumClipboardFormats(current))
                    if current == 0:
                        break
                    name = clipboard_format_name(current)
                    if current == 2:
                        skipped.append({"format_id": current, "name": name, "reason": "bitmap_handle_not_portable"})
                        continue
                    if current == 17 and any(item.format_id == 8 for item in formats):
                        skipped.append({"format_id": current, "name": name, "reason": "synthesized_from_CF_DIB"})
                        continue
                    handle = user32.GetClipboardData(current)
                    if not handle:
                        skipped.append({"format_id": current, "name": name, "reason": "no_handle"})
                        continue
                    size = int(kernel32.GlobalSize(handle))
                    if size <= 0:
                        skipped.append({"format_id": current, "name": name, "reason": "not_hglobal_or_empty"})
                        continue
                    if size > MAX_CLIPBOARD_SNAPSHOT_BYTES:
                        skipped.append({"format_id": current, "name": name, "reason": "too_large", "bytes": size})
                        continue
                    pointer = kernel32.GlobalLock(handle)
                    if not pointer:
                        skipped.append({"format_id": current, "name": name, "reason": "lock_failed", "bytes": size})
                        continue
                    try:
                        formats.append(ClipboardFormatData(current, name, ctypes.string_at(pointer, size)))
                    finally:
                        kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
            return ClipboardSnapshot(formats, skipped, text_fallback=text_fallback, native=True)
        except Exception as exc:
            return ClipboardSnapshot([], skipped, text_fallback=text_fallback, native=False, error=repr(exc))

    def restore_snapshot(self, snapshot: ClipboardSnapshot) -> None:
        if snapshot.native and sys.platform == "win32" and hasattr(ctypes, "windll"):
            try:
                payloads = {item.format_id: item.data for item in snapshot.formats}
                if 8 in payloads and 17 in payloads:
                    # Windows can synthesize CF_DIBV5 from CF_DIB. Re-publishing both raw
                    # handles has proven fragile in frozen builds, so keep the source DIB.
                    payloads.pop(17, None)
                set_windows_clipboard_formats(
                    payloads,
                    hwnd=None,
                )
                self.root.update_idletasks()
                return
            except Exception:
                if not snapshot.text_fallback:
                    raise
        if snapshot.text_fallback:
            self.set_text(snapshot.text_fallback)
        else:
            self.root.clipboard_clear()
            self.root.update_idletasks()


def paste_text_with_clipboard_protection(
    clipboard: Clipboard,
    text: str,
    *,
    protect_clipboard: bool,
    restore_delay_ms: int,
    target_hwnd: int | None,
    schedule_ui: Callable[[int, Callable[[], None]], object],
    auto_send: bool = False,
    auto_send_delay_ms: int = 0,
) -> bool:
    if not text:
        return False
    original = clipboard.create_snapshot() if protect_clipboard else None
    clipboard.set_text(text)
    if target_hwnd:
        set_foreground_window(target_hwnd)
        time.sleep(0.05)
    send_ctrl_v()
    if auto_send:
        schedule_ui(auto_send_delay_ms, send_enter)
    if protect_clipboard and original is not None:
        schedule_ui(restore_delay_ms, lambda: clipboard.restore_snapshot(original))
    return True


class DesktopApp:
    def __init__(
        self,
        hidden: bool = False,
        show_help: bool = False,
        background: bool = False,
        ui_layout_report: str | None = None,
        ui_window_size: str | None = None,
        ui_scale_factor: float | None = None,
    ) -> None:
        configure_windows_app_identity()
        configure_process_dpi_awareness()
        self.root = tk.Tk()
        self._quitting = False
        self.tray_actions: queue.Queue[str] = queue.Queue()
        self.tray_icon: WindowsTrayIcon | None = None
        self.default_window_scaled = ui_window_size is None
        if ui_scale_factor is not None:
            self.root.tk.call("tk", "scaling", BASE_TK_SCALING * max(0.75, min(3.0, ui_scale_factor)))
        self.root.title(MAIN_WINDOW_TITLE)
        icon_path = app_icon_path()
        if icon_path is not None:
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        if ui_window_size:
            self.root.geometry(ui_window_size)
        else:
            window_width, window_height = self.scaled_window_size(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
            self.root.geometry(f"{window_width}x{window_height}")
        min_window_scale = min(max(self.current_ui_scale_factor(), 1.0), 1.35)
        self.root.minsize(int(MIN_WINDOW_WIDTH * min_window_scale), int(MIN_WINDOW_HEIGHT * min_window_scale))
        self.root.protocol("WM_DELETE_WINDOW", self.hide_main_window)
        self._configure_ttk_styles()
        self.config = load_config()
        self.license_config = load_license_config()
        self.license_result: LicenseResult | None = None
        self.license_checked_at = 0.0
        self.clipboard = Clipboard(self.root)
        self.active_keys: set[str] = set()
        self._layout_after_id: str | None = None
        self._layout_signature: tuple[int, int, int, float] | None = None
        self._action_layout_signature: tuple[int, int, int, bool, bool, bool] | None = None
        self.recording_session_id = 0
        self.recording_mode: str | None = None
        self.pending_mode: str | None = None
        self.cancelled = False
        self.target_hwnd: int | None = None
        self.audio_queue: queue.Queue[bytes | None] | None = None
        self.audio_stream: sd.InputStream | None = None
        self.asr_thread: threading.Thread | None = None
        self.transcript = TranscriptAccumulator()
        self.final_text = ""
        self.entries: dict[str, tk.Entry] = {}
        self.vars: dict[str, tk.BooleanVar] = {}
        self.settings_outer: tk.Frame | None = None
        self.settings_title_label: tk.Label | None = None
        self.settings_subtitle_label: tk.Label | None = None
        self.settings_status_label: tk.Label | None = None
        self.settings_table: tk.Frame | None = None
        self.settings_sections: list[dict[str, tk.Widget]] = []
        self.settings_mode_groups: list[dict[str, tk.Widget]] = []
        self.settings_rows: list[dict[str, object]] = []
        self.settings_checks_frame: tk.Frame | None = None
        self.settings_checkbuttons: list[tk.Checkbutton] = []
        self.settings_option_buttons: dict[str, tk.Checkbutton] = {}
        self.settings_option_labels: dict[str, str] = {}
        self.settings_help_label: tk.Label | None = None
        self.action_buttons_frame: tk.Frame | None = None
        self.action_buttons: list[tk.Button] = []
        self.delay_vars: dict[str, tk.IntVar] = {}
        self.ui_layout_report = Path(ui_layout_report) if ui_layout_report else None
        self.help_win: tk.Toplevel | None = None
        self.activation_win: tk.Toplevel | None = None
        self.activation_code_var = tk.StringVar(value="")
        self.activation_status_var = tk.StringVar(value="")
        self.float_needed_lines = 0
        self.float_visible_lines = 0
        self.float_action_buttons: list[tk.Button] = []
        self.recording_field: str | None = None
        self.status_var = tk.StringVar(value="已就绪")
        self.transcript_var = tk.StringVar(value="")
        self._build_settings_ui()
        self._build_float_window()
        self._start_listeners()
        self._start_tray_icon()
        self.root.after(100, self._process_tray_actions)
        self.root.after(150, self.check_license_on_startup)
        if hidden or background:
            self.root.withdraw()
        if hidden:
            pass
        elif background:
            self.root.after(100, self.show_main_window_background)
        else:
            self.root.after(100, self.show_main_window)
        if show_help:
            self.root.after(100, self.show_help)
        if self.ui_layout_report is not None:
            self.root.after(800, self.write_ui_layout_report)

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self._cleanup_resources()

    def _start_tray_icon(self) -> None:
        if not WindowsTrayIcon.is_supported():
            return
        self.tray_icon = WindowsTrayIcon("豆包 ASR 助手 - 后台运行", self._enqueue_tray_action, icon_path=app_icon_path())
        self.tray_icon.start()
        self.root.after(1200, self._report_tray_startup_error)

    def _report_tray_startup_error(self) -> None:
        if self._quitting or not self.tray_icon:
            return
        if self.tray_icon.last_error:
            self.status_var.set("系统托盘不可用，窗口隐藏后可从任务管理器结束")

    def _enqueue_tray_action(self, action: str) -> None:
        self.tray_actions.put(action)

    def _process_tray_actions(self) -> None:
        while True:
            try:
                action = self.tray_actions.get_nowait()
            except queue.Empty:
                break
            self._handle_tray_action(action)
        if not self._quitting:
            try:
                self.root.after(100, self._process_tray_actions)
            except tk.TclError:
                pass

    def _handle_tray_action(self, action: str) -> None:
        if action == WindowsTrayIcon.ACTION_SHOW:
            self.show_main_window()
        elif action == WindowsTrayIcon.ACTION_HIDE:
            self.hide_main_window()
        elif action == WindowsTrayIcon.ACTION_OPEN_CONFIG:
            self.open_config_dir()
        elif action == WindowsTrayIcon.ACTION_QUIT:
            self.quit_app()

    def hide_main_window(self) -> None:
        try:
            self.root.withdraw()
            self.status_var.set("已隐藏到系统托盘，右键托盘图标可退出")
        except tk.TclError:
            pass

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._cleanup_resources()
        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _cleanup_resources(self) -> None:
        if getattr(self, "_resources_cleaned", False):
            return
        self._resources_cleaned = True
        self._quitting = True
        self._stop_recording_for_exit()
        for listener in (getattr(self, "keyboard_listener", None), getattr(self, "mouse_listener", None)):
            if listener is None:
                continue
            try:
                listener.stop()
            except Exception:
                pass
        if self.tray_icon is not None:
            self.tray_icon.stop()

    def _stop_recording_for_exit(self) -> None:
        self.recording_session_id += 1
        self.recording_mode = None
        self.pending_mode = None
        self.recording_field = None
        self.active_keys.clear()
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
            except Exception:
                pass
            try:
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        if self.audio_queue is not None:
            try:
                self.audio_queue.put_nowait(None)
            except Exception:
                pass

    def schedule_ui(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if self._quitting:
            return
        try:
            self.root.after(delay_ms, callback)
        except tk.TclError:
            pass

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            sv_ttk.set_theme("light")
        except tk.TclError:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        style.configure(".", font=("Microsoft YaHei UI", 9), background=UI_BG, foreground=UI_TEXT)
        style.configure(
            "Modern.TEntry",
            fieldbackground=UI_INPUT,
            background=UI_INPUT,
            foreground=UI_TEXT,
            bordercolor=UI_BORDER,
            lightcolor=UI_BORDER,
            darkcolor=UI_BORDER,
            insertcolor=UI_TEXT,
            relief="flat",
            padding=(8, 4),
        )
        style.map(
            "Modern.TEntry",
            bordercolor=[("focus", UI_PRIMARY), ("!focus", UI_BORDER)],
            lightcolor=[("focus", UI_PRIMARY), ("!focus", UI_BORDER)],
            darkcolor=[("focus", UI_PRIMARY), ("!focus", UI_BORDER)],
        )
        style.configure(
            "Modern.Horizontal.TScale",
            background=UI_CARD,
            troughcolor="#dbeafe",
            bordercolor=UI_CARD,
            lightcolor=UI_CARD,
            darkcolor=UI_CARD,
            sliderthickness=12,
        )
        style.configure(
            "Modern.TCheckbutton",
            background=UI_CARD,
            foreground=UI_TEXT,
            focuscolor=UI_CARD,
            indicatorbackground=UI_INPUT,
            indicatorforeground=UI_PRIMARY,
            padding=(0, 3),
        )
        style.map(
            "Modern.TCheckbutton",
            background=[("active", UI_CARD)],
            foreground=[("active", UI_TEXT)],
            indicatorbackground=[("selected", UI_PRIMARY), ("!selected", UI_INPUT)],
        )

    def current_ui_scale_factor(self) -> float:
        try:
            return max(0.75, float(self.root.tk.call("tk", "scaling")) / BASE_TK_SCALING)
        except (tk.TclError, ValueError):
            return 1.0

    def scaled_window_size(
        self,
        base_width: int,
        base_height: int,
        max_width_ratio: float = 0.9,
        max_height_ratio: float = 0.88,
    ) -> tuple[int, int]:
        scale = min(max(self.current_ui_scale_factor(), 1.0), 2.5)
        width = int(round(base_width * scale))
        height = int(round(base_height * scale))
        try:
            screen_width = max(int(self.root.winfo_screenwidth()), base_width)
            screen_height = max(int(self.root.winfo_screenheight()), base_height)
        except tk.TclError:
            return width, height
        max_width = max(base_width, int(screen_width * max_width_ratio))
        max_height = max(base_height, int(screen_height * max_height_ratio))
        return min(width, max_width), min(height, max_height)

    def show_main_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def show_main_window_background(self) -> None:
        if sys.platform == "win32":
            try:
                self.root.deiconify()
                self.root.update_idletasks()
                hwnd = int(self.root.winfo_id())
                user32 = ctypes.windll.user32
                user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                user32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0010 | 0x0002 | 0x0001)
                return
            except (OSError, tk.TclError, AttributeError):
                pass
        self.root.deiconify()
        try:
            self.root.lower()
        except tk.TclError:
            pass

    def _build_settings_ui(self) -> None:
        shell = tk.Frame(self.root, bg=UI_BG)
        shell.pack(fill="both", expand=True)

        outer = tk.Frame(shell, padx=12, pady=10, bg=UI_BG)
        outer.pack(fill="both", expand=True)
        self.root.bind("<Configure>", lambda _event: self.request_layout_settings_controls(), add="+")
        self.settings_outer = outer

        self.settings_title_label = tk.Label(
            outer,
            text="豆包语音助手 - 设置",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=UI_BG,
            fg=UI_TEXT,
            anchor="w",
        )
        self.settings_title_label.pack(anchor="w")
        self.settings_subtitle_label = tk.Label(
            outer,
            text="按模式设置触发键，再微调插入、发送和剪贴板行为",
            bg=UI_BG,
            fg=UI_MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        self.settings_subtitle_label.pack(anchor="w", pady=(2, 0))

        table = tk.Frame(outer, bg=UI_BG)
        table.pack(fill="x", pady=(6, 0))
        self.settings_table = table
        self.settings_sections.clear()
        self.settings_mode_groups.clear()
        self.settings_rows.clear()
        self.delay_vars.clear()
        self.entries.clear()

        hold_body = self._build_mode_group(table, "按着说")
        self._create_setting_row(hold_body, "hold_key", "触发按键：", "按住说话，松开自动插入", row_type="hotkey")

        toggle_body = self._build_mode_group(table, "自由说")
        self._create_setting_row(toggle_body, "toggle_key", "触发按键：", "点击开始，再次点击结束并插入", row_type="hotkey")

        hold_send_body = self._build_mode_group(table, "按着说+自动发送")
        self._create_setting_row(hold_send_body, "hold_send_key", "触发按键：", "", row_type="hotkey")
        self._create_setting_row(hold_send_body, "cancel_key", "取消按键：", "按住说话松开发送，说话中按取消键可取消", row_type="hotkey")

        self._build_separator(table)
        common_body = tk.Frame(table, bg=UI_BG)
        common_body.pack(fill="x")
        self._create_setting_row(common_body, "doubao_hotkey", "豆包快捷键：", "保留兼容配置，当前使用内置 ASR", row_type="hotkey")
        self._create_delay_row(common_body, "insert_delay_ms", "插入延迟：", "", *DELAY_SPECS["insert_delay_ms"], display="seconds")

        checks = tk.Frame(common_body, bg=UI_BG)
        checks.pack(fill="x", pady=(1, 3))
        self.settings_checks_frame = checks
        self.settings_checkbuttons.clear()
        self.settings_option_buttons.clear()
        self.settings_option_labels.clear()
        self.vars["protect_clipboard"] = tk.BooleanVar(value=self.config.protect_clipboard)
        self.vars["startup"] = tk.BooleanVar(value=self.config.startup)
        protect_clipboard = self._create_option_toggle(checks, "protect_clipboard", "剪贴板保护（防止覆盖原有复制内容）")
        startup = self._create_option_toggle(checks, "startup", "开机自启动")
        protect_clipboard.pack(anchor="w")
        startup.pack(anchor="w", pady=(3, 0))
        self.settings_checkbuttons.extend([protect_clipboard, startup])

        advanced_body = self._build_settings_section(table, "高级设置", "")
        self._create_setting_row(advanced_body, "credential_path", "凭据文件：", "设备注册和 token 缓存文件", row_type="path")
        self._create_delay_entry_row(advanced_body, "clipboard_restore_delay_ms", "剪贴板超时：", "最小 500", *DELAY_SPECS["clipboard_restore_delay_ms"])
        self._create_delay_entry_row(advanced_body, "auto_send_delay_ms", "发送延迟：", "推荐 0~100", *DELAY_SPECS["auto_send_delay_ms"])

        buttons = tk.Frame(outer, bg=UI_BG)
        buttons.pack(fill="x", pady=(7, 5))
        self.action_buttons_frame = buttons
        self.action_buttons.clear()
        actions = [
            ("保存", self.save_from_ui),
            ("取消", self.hide_main_window),
            ("恢复默认", self.reset_settings_to_defaults),
            ("显示悬浮窗", lambda: self.show_float("")),
            ("使用说明", self.show_help),
            ("打开配置目录", self.open_config_dir),
        ]
        for index, (text, command) in enumerate(actions):
            button = tk.Button(buttons, text=text, command=command, width=12)
            self._style_action_button(button, primary=index == 0)
            self.action_buttons.append(button)

        self.settings_status_label = tk.Label(
            outer,
            textvariable=self.status_var,
            bg=UI_BG,
            fg=UI_SUCCESS,
            anchor="w",
            justify="left",
            padx=0,
            pady=0,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.settings_status_label.pack(anchor="w")
        help_text = (
            f"默认热键：{default_hotkey_summary()}。"
            "录音结束后会把识别文字粘贴到开始录音前的窗口。"
        )
        self.settings_help_label = tk.Label(
            outer,
            text=help_text,
            bg=UI_BG,
            fg=UI_MUTED,
            wraplength=660,
            justify="left",
        )
        self.settings_help_label.pack(anchor="w", pady=(4, 0))
        self.root.after_idle(self.layout_settings_controls)

    def _build_mode_group(self, parent: tk.Widget, title: str) -> tk.Frame:
        group = tk.Frame(parent, bg=UI_CARD, highlightthickness=1, highlightbackground=UI_BORDER)
        group.pack(fill="x", pady=(0, 5))
        title_label = tk.Label(
            group,
            text=f"【{title}】 模式",
            bg=UI_CARD,
            fg=UI_TEXT,
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        )
        title_label.pack(anchor="w", padx=10, pady=(6, 0))
        body = tk.Frame(group, bg=UI_CARD, padx=8, pady=4)
        body.pack(fill="x")
        self.settings_mode_groups.append(
            {
                "group": group,
                "title": title_label,
                "body": body,
            }
        )
        return body

    def _build_separator(self, parent: tk.Widget) -> None:
        separator = tk.Frame(parent, bg=UI_BORDER, height=1)
        separator.pack(fill="x", pady=(1, 6))

    def _build_settings_section(self, parent: tk.Widget, title: str, subtitle: str) -> tk.Frame:
        section = tk.Frame(parent, bg=UI_CARD, highlightthickness=1, highlightbackground=UI_BORDER)
        section.pack(fill="x", pady=3)
        body = tk.Frame(section, bg=UI_CARD, padx=10, pady=6)
        body.pack(fill="x")
        header = tk.Frame(body, bg=UI_CARD)
        header.pack(fill="x", pady=(0, 3))
        title_label = tk.Label(
            header,
            text=title,
            bg=UI_CARD,
            fg=UI_TEXT,
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        )
        title_label.pack(side="left")
        subtitle_label = tk.Label(
            header,
            text=subtitle,
            bg=UI_CARD,
            fg=UI_MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        subtitle_label.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.settings_sections.append(
            {
                "section": section,
                "body": body,
                "header": header,
                "title": title_label,
                "subtitle": subtitle_label,
            }
        )
        return body

    def _create_base_row(
        self,
        parent: tk.Widget,
        key: str,
        label: str,
        desc: str,
        row_type: str,
    ) -> dict[str, object]:
        row_frame = tk.Frame(parent, bg=UI_CARD)
        row_frame.pack(fill="x", pady=2)
        label_widget = tk.Label(
            row_frame,
            text=label,
            anchor="w",
            bg=UI_CARD,
            fg=UI_TEXT,
            font=("Microsoft YaHei UI", 9),
        )
        desc_widget = tk.Label(
            row_frame,
            text=desc,
            anchor="w",
            bg=UI_CARD,
            fg=UI_MUTED,
            wraplength=170,
            justify="left",
            font=("Microsoft YaHei UI", 9),
        )
        row: dict[str, object] = {
            "key": key,
            "frame": row_frame,
            "label": label_widget,
            "desc": desc_widget,
            "desc_enabled": bool(desc.strip()),
            "button": None,
            "entry": None,
            "scale": None,
            "unit": None,
            "value": None,
            "hint": None,
            "kind": row_type,
        }
        return row

    def _create_setting_row(self, parent: tk.Widget, key: str, label: str, desc: str, row_type: str) -> None:
        row = self._create_base_row(parent, key, label, desc, row_type)
        frame = row["frame"]
        if not isinstance(frame, tk.Frame):
            return
        entry = ttk.Entry(
            frame,
            width=10,
            style="Modern.TEntry",
        )
        initial_value = display_hotkey_value(str(getattr(self.config, key))) if key in HOTKEY_LABELS else str(getattr(self.config, key))
        entry.insert(0, initial_value)
        self.entries[key] = entry
        button: tk.Button | None = None
        if key in HOTKEY_LABELS:
            button = tk.Button(frame, text="录制", command=lambda field=key: self.start_key_record(field), width=5)
            self._style_small_button(button)
        elif key == "credential_path":
            button = tk.Button(frame, text="选择", command=self.select_credential_file, width=5)
            self._style_small_button(button)
        row["button"] = button
        row["entry"] = entry
        self.settings_rows.append(row)

    def _create_delay_row(
        self,
        parent: tk.Widget,
        key: str,
        label: str,
        desc: str,
        minimum: int,
        maximum: int,
        step: int,
        display: str = "entry",
    ) -> None:
        row = self._create_base_row(parent, key, label, desc, "delay")
        frame = row["frame"]
        if not isinstance(frame, tk.Frame):
            return
        row["delay_display"] = display
        value = snap_delay_value(int(getattr(self.config, key)), minimum, maximum, step)
        var = tk.IntVar(value=value)
        self.delay_vars[key] = var
        scale = ttk.Scale(
            frame,
            from_=minimum,
            to=maximum,
            orient="horizontal",
            variable=var,
            style="Modern.Horizontal.TScale",
            command=lambda value, field=key, low=minimum, high=maximum, inc=step: self._sync_delay_from_scale(field, value, low, high, inc),
        )
        entry = ttk.Entry(
            frame,
            width=5,
            justify="right",
            style="Modern.TEntry",
        )
        entry.insert(0, str(value))
        entry.bind("<FocusOut>", lambda _event, field=key, low=minimum, high=maximum, inc=step: self._sync_delay_from_entry(field, low, high, inc))
        entry.bind("<Return>", lambda _event, field=key, low=minimum, high=maximum, inc=step: self._sync_delay_from_entry(field, low, high, inc))
        unit = tk.Label(frame, text="ms", bg=UI_CARD, fg=UI_MUTED, font=("Microsoft YaHei UI", 8))
        value_label = tk.Label(frame, text=self._delay_seconds_text(value), bg=UI_CARD, fg=UI_TEXT, font=("Microsoft YaHei UI", 9, "bold"))
        self.entries[key] = entry
        row["entry"] = entry
        row["scale"] = scale
        row["unit"] = unit
        row["value"] = value_label
        self.settings_rows.append(row)

    def _create_delay_entry_row(
        self,
        parent: tk.Widget,
        key: str,
        label: str,
        hint: str,
        minimum: int,
        maximum: int,
        step: int,
    ) -> None:
        row = self._create_base_row(parent, key, label, "", "delay_entry")
        frame = row["frame"]
        if not isinstance(frame, tk.Frame):
            return
        value = snap_delay_value(int(getattr(self.config, key)), minimum, maximum, step)
        var = tk.IntVar(value=value)
        self.delay_vars[key] = var
        entry = ttk.Entry(
            frame,
            width=6,
            justify="right",
            style="Modern.TEntry",
        )
        entry.insert(0, str(value))
        entry.bind("<FocusOut>", lambda _event, field=key, low=minimum, high=maximum, inc=step: self._sync_delay_from_entry(field, low, high, inc))
        entry.bind("<Return>", lambda _event, field=key, low=minimum, high=maximum, inc=step: self._sync_delay_from_entry(field, low, high, inc))
        unit = tk.Label(frame, text="ms", bg=UI_CARD, fg=UI_TEXT, font=("Microsoft YaHei UI", 9))
        hint_label = tk.Label(frame, text=f"（{hint}）", bg=UI_CARD, fg=UI_MUTED, font=("Microsoft YaHei UI", 9), anchor="w")
        self.entries[key] = entry
        row["entry"] = entry
        row["unit"] = unit
        row["hint"] = hint_label
        self.settings_rows.append(row)

    def _delay_seconds_text(self, value: int) -> str:
        seconds = value / 1000
        text = f"{seconds:.2f}".rstrip("0").rstrip(".")
        return f"{text} 秒"

    def _style_small_button(self, button: tk.Button) -> None:
        button.configure(
            bg=UI_PRIMARY_SOFT,
            fg=UI_PRIMARY_DARK,
            activebackground="#dbeafe",
            activeforeground=UI_PRIMARY_DARK,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )

    def _style_action_button(self, button: tk.Button, primary: bool = False) -> None:
        button.configure(
            bg=UI_PRIMARY if primary else UI_CARD,
            fg="#ffffff" if primary else UI_TEXT,
            activebackground=UI_PRIMARY_DARK if primary else UI_PRIMARY_SOFT,
            activeforeground="#ffffff" if primary else UI_TEXT,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9, "bold" if primary else "normal"),
            highlightthickness=1,
            highlightbackground=UI_PRIMARY if primary else UI_BORDER,
        )

    def _create_option_toggle(self, parent: tk.Widget, key: str, text: str) -> tk.Checkbutton:
        self.settings_option_labels[key] = text
        toggle = tk.Checkbutton(
            parent,
            text=text,
            variable=self.vars[key],
            indicatoron=False,
            anchor="w",
            justify="left",
            bg=UI_CARD,
            fg=UI_TEXT,
            activebackground=UI_TOGGLE_OFF_ACTIVE,
            activeforeground=UI_TEXT,
            selectcolor=UI_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            highlightbackground=UI_CARD,
            highlightcolor=UI_PRIMARY,
            cursor="hand2",
            takefocus=True,
            padx=8,
            pady=5,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        toggle.configure(command=lambda widget=toggle, option_key=key: self._sync_option_toggle_style(widget, option_key))
        self.settings_option_buttons[key] = toggle
        self._sync_option_toggle_style(toggle, key)
        return toggle

    def _sync_option_toggle_style(self, toggle: tk.Checkbutton, key: str) -> None:
        var = self.vars.get(key)
        selected = bool(var.get()) if var is not None else False
        marker = "☑" if selected else "☐"
        label = self.settings_option_labels.get(key, key)
        toggle.configure(
            text=f"{marker} {label}",
            bg=UI_CARD,
            fg=UI_TEXT,
            activebackground=UI_PRIMARY_SOFT,
            activeforeground=UI_TEXT,
            selectcolor=UI_CARD,
        )

    def _sync_option_toggle_styles(self) -> None:
        for key, toggle in self.settings_option_buttons.items():
            self._sync_option_toggle_style(toggle, key)

    def _sync_delay_entry(self, field: str) -> None:
        entry = self.entries.get(field)
        var = self.delay_vars.get(field)
        if entry is None or var is None:
            return
        entry.delete(0, "end")
        entry.insert(0, str(var.get()))
        for row in self.settings_rows:
            if row.get("key") != field:
                continue
            value_label = row.get("value")
            if isinstance(value_label, tk.Label):
                value_label.configure(text=self._delay_seconds_text(var.get()))
            break

    def _sync_delay_from_scale(self, field: str, value: str, minimum: int, maximum: int, step: int) -> None:
        var = self.delay_vars.get(field)
        if var is None:
            return
        snapped = snap_delay_value(float(value), minimum, maximum, step)
        if var.get() != snapped:
            var.set(snapped)
        self._sync_delay_entry(field)

    def _sync_delay_from_entry(self, field: str, minimum: int, maximum: int, step: int) -> None:
        entry = self.entries.get(field)
        var = self.delay_vars.get(field)
        if entry is None or var is None:
            return
        try:
            value = int(entry.get().strip())
        except ValueError:
            value = var.get()
        value = snap_delay_value(value, minimum, maximum, step)
        var.set(value)
        self._sync_delay_entry(field)

    def request_layout_settings_controls(self) -> None:
        if self._layout_after_id is not None:
            return
        self._layout_after_id = self.root.after(80, self._run_deferred_layout_settings_controls)

    def _run_deferred_layout_settings_controls(self) -> None:
        self._layout_after_id = None
        self.layout_settings_controls()

    def layout_settings_controls(self, force: bool = False) -> None:
        if self.settings_table is None:
            return

        root_width = max(self.root.winfo_width(), 1)
        root_height = max(self.root.winfo_height(), 1)
        available_width = max(self.settings_table.winfo_width(), root_width - 40, 1)
        ui_scale = self.current_ui_scale_factor()
        signature = (
            root_width // 24,
            root_height // 24,
            available_width // 24,
            round(ui_scale, 2),
        )
        if not force and signature == self._layout_signature:
            return
        self._layout_signature = signature
        logical_width = root_width / max(ui_scale, 1.0)
        logical_height = root_height / max(ui_scale, 1.0)
        logical_available_width = available_width / max(ui_scale, 1.0)
        narrow = logical_width <= 620
        short = logical_height <= 540
        tiny = (
            (logical_width <= 620 and logical_height <= 430)
            or logical_height <= 430
        )
        compact = narrow or logical_available_width < 760 or logical_height < 640
        show_desc = not compact and not narrow and logical_height > 700
        show_section_headers = not tiny
        hide_advanced_section = logical_height <= 700
        desc_wrap = int(
            min(
                max(220 * ui_scale, available_width * 0.24),
                min(420 * ui_scale, available_width * 0.34),
            )
        )
        outer_padx = 6 if tiny else 10 if short or compact else 18
        outer_pady = 4 if tiny else 7 if short else 10 if compact else 14
        row_pady = 0 if tiny else 1 if short else 2 if compact else 3
        title_size = 10 if tiny else 11 if short or compact else 12
        normal_size = 8 if tiny else 9
        desc_size = normal_size
        normal_font = ("Microsoft YaHei UI", normal_size)
        desc_font = ("Microsoft YaHei UI", desc_size)
        label_font = normal_font
        button_font = normal_font
        label_font_metrics = tkfont.Font(root=self.root, font=label_font)
        button_font_metrics = tkfont.Font(root=self.root, font=button_font)
        label_col_width = max(
            82,
            max(
                (
                    label_font_metrics.measure(str(row["label"].cget("text"))) + (12 if tiny else 20)
                    for row in self.settings_rows
                    if isinstance(row.get("label"), tk.Label)
                ),
                default=82,
            ),
        )
        info_col_width = label_col_width
        desc_label_wrap = max(120, info_col_width - (12 if tiny else 18))
        if not compact and not narrow:
            desc_label_wrap = max(320, available_width - 120)
        button_col_width = max(button_font_metrics.measure("选择") + 28, button_font_metrics.measure("录制") + 28, 56)

        if self.settings_outer is not None:
            self.settings_outer.configure(padx=outer_padx, pady=outer_pady)
        if self.settings_title_label is not None:
            self.settings_title_label.configure(font=("Microsoft YaHei UI", title_size, "bold"))
            if tiny and self.settings_title_label.winfo_ismapped():
                self.settings_title_label.pack_forget()
            elif not tiny and not self.settings_title_label.winfo_ismapped():
                if self.settings_subtitle_label is not None and self.settings_subtitle_label.winfo_ismapped():
                    self.settings_title_label.pack(anchor="w", before=self.settings_subtitle_label)
                else:
                    self.settings_title_label.pack(anchor="w")
        if self.settings_subtitle_label is not None:
            if (tiny or short or compact) and self.settings_subtitle_label.winfo_ismapped():
                self.settings_subtitle_label.pack_forget()
            elif not tiny and not short and not compact and not self.settings_subtitle_label.winfo_ismapped():
                self.settings_subtitle_label.pack(anchor="w", pady=(2, 0))
        if self.settings_status_label is not None:
            self.settings_status_label.configure(
                font=normal_font,
                wraplength=max(160, available_width - 20),
                padx=8 if tiny else 12,
                pady=2 if tiny else 4,
            )
            self.settings_status_label.pack_configure(padx=(8 if tiny else 14, 0))

        if self.settings_table is not None:
            self.settings_table.pack_configure(pady=(3 if tiny else 5 if short or compact else 8, 0))

        for group in self.settings_mode_groups:
            group_frame = group.get("group")
            title = group.get("title")
            body = group.get("body")
            if isinstance(group_frame, tk.Frame):
                group_frame.configure(highlightthickness=0 if tiny else 1)
                group_frame.pack_configure(pady=(0, 3 if tiny else 4 if short or compact else 6))
            if isinstance(title, tk.Label):
                title.configure(font=("Microsoft YaHei UI", normal_size, "bold"))
                title.pack_configure(padx=8 if tiny else 10, pady=(4 if tiny else 5 if short or compact else 6, 0))
            if isinstance(body, tk.Frame):
                body.configure(padx=8 if tiny else 9 if short or compact else 10, pady=3 if tiny else 4 if short or compact else 5)

        for section in self.settings_sections:
            section_frame = section.get("section")
            body = section.get("body")
            header = section.get("header")
            title = section.get("title")
            subtitle = section.get("subtitle")
            hide_section = (
                (
                    hide_advanced_section
                    or (tiny and logical_height < 310)
                )
                and isinstance(title, tk.Label)
                and str(title.cget("text")) == "高级设置"
            )
            if isinstance(section_frame, tk.Frame):
                if hide_section:
                    if section_frame.winfo_ismapped():
                        section_frame.pack_forget()
                    continue
                if not section_frame.winfo_ismapped():
                    section_frame.pack(fill="x", pady=3)
                section_frame.configure(highlightthickness=0 if tiny else 1)
                section_frame.pack_configure(pady=0 if tiny else 2 if short or compact else 3)
            if isinstance(body, tk.Frame):
                body.configure(padx=8 if tiny else 9 if short or compact else 10, pady=0 if tiny else 4 if short or compact else 6)
            if isinstance(header, tk.Frame):
                if show_section_headers:
                    if not header.winfo_ismapped():
                        siblings = [child for child in body.winfo_children() if child is not header]
                        if siblings:
                            header.pack(fill="x", before=siblings[0])
                        else:
                            header.pack(fill="x")
                    header.pack_configure(pady=(0, 2 if short or compact else 3))
                elif header.winfo_ismapped():
                    header.pack_forget()
            if isinstance(title, tk.Label):
                title.configure(font=("Microsoft YaHei UI", normal_size, "bold"))
                if show_section_headers and not title.winfo_ismapped():
                    title.pack(side="left")
                elif not show_section_headers and title.winfo_ismapped():
                    title.pack_forget()
            if isinstance(subtitle, tk.Label):
                subtitle.configure(font=desc_font, wraplength=max(180, available_width - 220))
                should_show_subtitle = bool(str(subtitle.cget("text")).strip()) and show_section_headers and not short and not compact
                if should_show_subtitle and not subtitle.winfo_ismapped():
                    subtitle.pack(side="left", padx=(10, 0), fill="x", expand=True)
                elif not should_show_subtitle and subtitle.winfo_ismapped():
                    subtitle.pack_forget()

        for row in self.settings_rows:
            frame = row["frame"]
            label = row["label"]
            desc = row["desc"]
            button = row["button"]
            entry = row["entry"]
            scale = row.get("scale")
            unit = row.get("unit")
            value = row.get("value")
            hint = row.get("hint")
            kind = row.get("kind")
            if not isinstance(frame, tk.Frame) or label is None or desc is None or entry is None:
                continue

            hide_row = tiny and row.get("key") == "credential_path"
            if hide_row:
                if frame.winfo_ismapped():
                    frame.pack_forget()
                continue
            if not frame.winfo_ismapped():
                frame.pack(fill="x")
            frame.pack_configure(pady=row_pady)
            row_show_desc = show_desc and bool(row.get("desc_enabled"))
            for widget in (label, desc, button, entry, scale, unit, value, hint):
                if widget is not None:
                    if isinstance(widget, tk.Widget):
                        widget.grid_forget()
                    if isinstance(widget, tk.Label):
                        widget.configure(font=desc_font if widget is desc or widget is hint else label_font if widget is label else normal_font)
                    elif isinstance(widget, (tk.Entry, ttk.Entry)):
                        widget.configure(font=normal_font)
                    elif isinstance(widget, tk.Button):
                        widget.configure(font=button_font)
            for column in range(6):
                frame.columnconfigure(column, weight=0, minsize=0)
            for row_index in range(2):
                frame.rowconfigure(row_index, weight=0, minsize=0)

            if isinstance(desc, tk.Label):
                desc.configure(wraplength=desc_label_wrap)

            if kind == "delay" and isinstance(scale, (tk.Scale, ttk.Scale)) and isinstance(value, tk.Label):
                frame.columnconfigure(0, minsize=info_col_width)
                display = row.get("delay_display")
                if narrow:
                    frame.columnconfigure(1, weight=1)
                    label.grid(row=0, column=0, sticky="w", padx=(0, 6))
                    scale.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                    if display == "seconds":
                        value.grid(row=0, column=2, sticky="e")
                    elif isinstance(unit, tk.Label):
                        entry.grid(row=0, column=2, sticky="ew", padx=(0, 4))
                        unit.grid(row=0, column=3, sticky="w")
                else:
                    frame.columnconfigure(1, weight=1)
                    label.grid(row=0, column=0, sticky="w", padx=(0, 14), pady=(0, 1 if row_show_desc else 0))
                    if row_show_desc:
                        desc.grid(row=1, column=0, sticky="w", padx=(0, 14))
                    row_span = 2 if row_show_desc else 1
                    scale.grid(row=0, column=1, rowspan=row_span, sticky="ew", padx=(0, 8))
                    if display == "seconds":
                        value.grid(row=0, column=2, rowspan=row_span, sticky="e")
                    elif isinstance(unit, tk.Label):
                        entry.grid(row=0, column=2, rowspan=row_span, sticky="ew", padx=(0, 4))
                        unit.grid(row=0, column=3, rowspan=row_span, sticky="w")
                continue

            if kind == "delay_entry" and isinstance(unit, tk.Label):
                frame.columnconfigure(0, minsize=info_col_width)
                frame.columnconfigure(1, minsize=86 if not tiny else 70)
                label.grid(row=0, column=0, sticky="w", padx=(0, 8))
                entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                unit.grid(row=0, column=2, sticky="w", padx=(0, 12))
                if isinstance(hint, tk.Label) and not tiny:
                    hint.grid(row=0, column=3, sticky="w")
                continue

            if narrow:
                frame.columnconfigure(0, minsize=info_col_width)
                frame.columnconfigure(1, weight=1)
                label.grid(row=0, column=0, sticky="w", padx=(0, 6))
                if button is not None:
                    button.configure(width=4)
                    frame.columnconfigure(2, minsize=button_col_width)
                    entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
                    button.grid(row=0, column=2, sticky="ew")
                else:
                    entry.grid(row=0, column=1, columnspan=2, sticky="ew")
            else:
                frame.columnconfigure(0, minsize=info_col_width)
                frame.columnconfigure(1, weight=1)
                label.grid(row=0, column=0, sticky="w", padx=(0, 14), pady=(0, 1 if row_show_desc else 0))
                if row_show_desc:
                    desc.grid(row=1, column=0, columnspan=3, sticky="w", padx=(0, 14))
                row_span = 1
                if button is not None:
                    button.configure(width=5)
                    frame.columnconfigure(2, minsize=button_col_width)
                    entry.grid(row=0, column=1, rowspan=row_span, sticky="ew", padx=(0, 8))
                    button.grid(row=0, column=2, rowspan=row_span)
                else:
                    entry.grid(row=0, column=1, columnspan=2, rowspan=row_span, sticky="ew")

        if self.settings_checks_frame is not None:
            self.settings_checks_frame.pack_configure(pady=1 if tiny else 2 if short else 4)
        inline_option_toggles = tiny and logical_available_width > 360
        toggle_font = ("Microsoft YaHei UI", max(normal_size, 9), "bold")
        toggle_padx = 8
        toggle_pady = 5
        for index, checkbutton in enumerate(self.settings_checkbuttons):
            if isinstance(checkbutton, tk.Checkbutton):
                checkbutton.configure(font=toggle_font, padx=toggle_padx, pady=toggle_pady)
                option_key = next(
                    (key for key, widget in self.settings_option_buttons.items() if widget is checkbutton),
                    "",
                )
                if option_key:
                    self._sync_option_toggle_style(checkbutton, option_key)
            if inline_option_toggles:
                checkbutton.pack_configure(side="left", anchor="w", fill="none", padx=(0 if index == 0 else 14, 0), pady=0)
            else:
                checkbutton.pack_configure(side="top", anchor="w", fill="none", padx=0, pady=(0 if index == 0 else 2, 0))

        self.layout_action_buttons(force=force)
        if self.settings_help_label is not None:
            help_text = (
                f"默认热键：{default_hotkey_summary()}。保存前会检查快捷键冲突。"
                if short
                else f"默认热键：{default_hotkey_summary()}。录音结束后会把识别文字粘贴到开始录音前的窗口。"
            )
            self.settings_help_label.configure(
                text=help_text,
                font=desc_font,
                wraplength=max(240, available_width - 20),
            )
            if tiny or short or compact:
                self.settings_help_label.pack_forget()
            elif not self.settings_help_label.winfo_ismapped():
                self.settings_help_label.pack(anchor="w")

    def layout_action_buttons(self, force: bool = False) -> None:
        if self.action_buttons_frame is None:
            return
        width = max(self.action_buttons_frame.winfo_width(), self.root.winfo_width() - 20, 1)
        root_height = max(self.root.winfo_height(), 1)
        ui_scale = self.current_ui_scale_factor()
        logical_width = width / max(ui_scale, 1.0)
        logical_height = root_height / max(ui_scale, 1.0)
        tight = logical_width <= 620 or logical_height <= 540
        compact = logical_width <= 780 or logical_height <= 640
        roomy = logical_width >= 760 and logical_height >= 600
        if logical_height <= 430 and width >= 520:
            columns = len(self.action_buttons)
        else:
            columns = len(self.action_buttons) if width >= 720 else 3 if width >= 500 else 2 if width >= 340 else 1
        signature = (width // 24, root_height // 24, columns, tight, compact, roomy)
        if not force and signature == self._action_layout_signature:
            return
        self._action_layout_signature = signature
        button_font = ("Microsoft YaHei UI", 8 if tight else 9)
        button_padx = 2 if root_height <= 430 else 3 if tight or compact else 6
        button_pady = 0 if root_height <= 430 else 1 if tight or compact else 4
        self.action_buttons_frame.pack_configure(pady=(5 if tight or compact else 10, 0 if tight or compact else 10))
        for column in range(6):
            self.action_buttons_frame.columnconfigure(column, weight=0)
        for button in self.action_buttons:
            button.grid_forget()
        for column in range(columns):
            self.action_buttons_frame.columnconfigure(column, weight=1)
        for index, button in enumerate(self.action_buttons):
            button.configure(font=button_font)
            row, column = divmod(index, columns)
            button.grid(
                row=row,
                column=column,
                sticky="" if roomy else "ew",
                padx=button_padx,
                pady=button_pady,
            )

    def _widget_bounds(self, name: str, widget: tk.Widget | None) -> dict[str, int | str] | None:
        if widget is None or not widget.winfo_ismapped():
            return None
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        x = widget.winfo_rootx() - root_x
        y = widget.winfo_rooty() - root_y
        width = widget.winfo_width()
        height = widget.winfo_height()
        return {
            "name": name,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "right": x + width,
            "bottom": y + height,
        }

    def write_ui_layout_report(self) -> None:
        if self.ui_layout_report is None:
            return
        self.root.update_idletasks()
        self.layout_settings_controls(force=True)
        self.root.update_idletasks()
        widgets: list[dict[str, int | str]] = []
        for name, widget in (
            ("title", self.settings_title_label),
            ("status", self.settings_status_label),
            ("checks", self.settings_checks_frame),
            ("actions", self.action_buttons_frame),
            ("help", self.settings_help_label),
        ):
            bounds = self._widget_bounds(name, widget)
            if bounds is not None:
                widgets.append(bounds)
        for index, group in enumerate(self.settings_mode_groups):
            group_widget = group.get("group")
            bounds = self._widget_bounds(f"mode-{index}", group_widget if isinstance(group_widget, tk.Widget) else None)
            if bounds is not None:
                widgets.append(bounds)
        for index, row in enumerate(self.settings_rows):
            row_key = str(row.get("key", index))
            for key in ("label", "desc", "button", "entry", "scale", "unit", "value", "hint"):
                widget = row.get(key)
                bounds = self._widget_bounds(f"setting-{index}-{key}", widget if isinstance(widget, tk.Widget) else None)
                if bounds is not None:
                    widgets.append(bounds)
                semantic_bounds = self._widget_bounds(f"setting-{row_key}-{key}", widget if isinstance(widget, tk.Widget) else None)
                if semantic_bounds is not None:
                    widgets.append(semantic_bounds)
        for index, button in enumerate(self.action_buttons):
            bounds = self._widget_bounds(f"action-{index}", button)
            if bounds is not None:
                widgets.append(bounds)
        for key, button in self.settings_option_buttons.items():
            bounds = self._widget_bounds(f"option-{key}", button)
            if bounds is not None:
                widgets.append(bounds)

        if not widgets:
            self.root.after(200, self.write_ui_layout_report)
            return

        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        content_right = max((int(widget["right"]) for widget in widgets), default=0)
        content_bottom = max((int(widget["bottom"]) for widget in widgets), default=0)
        report = {
            "root": {
                "width": root_width,
                "height": root_height,
                "logical_width": round(root_width / max(self.current_ui_scale_factor(), 1.0), 1),
                "logical_height": round(root_height / max(self.current_ui_scale_factor(), 1.0), 1),
            },
            "display": {
                "tk_scaling": float(self.root.tk.call("tk", "scaling")),
                "ui_scale_factor": round(self.current_ui_scale_factor(), 3),
                "screen_width": self.root.winfo_screenwidth(),
                "screen_height": self.root.winfo_screenheight(),
                "default_window_scaled": self.default_window_scaled,
            },
            "content": {
                "right": content_right,
                "bottom": content_bottom,
                "fits_horizontally": content_right <= root_width + 2,
                "fits_vertically": content_bottom <= root_height + 2,
            },
            "delays": {
                field: {
                    "value": int(self.delay_vars[field].get()),
                    "step": spec[2],
                }
                for field, spec in DELAY_SPECS.items()
                if field in self.delay_vars
            },
            "hotkeys": {
                field: self.entries[field].get()
                for field in HOTKEY_LABELS
                if field in self.entries
            },
            "widgets": widgets,
        }
        self.ui_layout_report.parent.mkdir(parents=True, exist_ok=True)
        self.ui_layout_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.ui_layout_report is not None:
            self.root.after(500, self.write_ui_layout_report)

    def start_key_record(self, field: str) -> None:
        self.recording_field = field
        self.active_keys.clear()
        self.status_var.set("请按下新的快捷键，支持键盘组合键或鼠标侧键")

    def select_credential_file(self) -> None:
        initial_dir = resolve_user_path(self.entries["credential_path"].get()).parent
        initial_dir.mkdir(parents=True, exist_ok=True)
        selected = filedialog.askopenfilename(
            title="选择凭据缓存文件",
            initialdir=str(initial_dir),
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if selected:
            self.entries["credential_path"].delete(0, "end")
            self.entries["credential_path"].insert(0, selected)

    def open_config_dir(self) -> None:
        APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(APP_CONFIG_DIR)

    def show_help(self) -> None:
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.deiconify()
            self.help_win.lift()
            return

        self.help_win = tk.Toplevel(self.root)
        self.help_win.title("使用说明 - 豆包 ASR 助手")
        self.help_win.geometry("760x620+420+220")
        self.help_win.minsize(640, 480)
        self.help_win.protocol("WM_DELETE_WINDOW", self.help_win.withdraw)

        frame = tk.Frame(self.help_win, padx=14, pady=14)
        frame.pack(fill="both", expand=True)
        text = scrolledtext.ScrolledText(frame, wrap="word", font=("Microsoft YaHei UI", 10), borderwidth=1)
        text.pack(fill="both", expand=True)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=(10, 0))
        tk.Button(actions, text="打开配置目录", command=self.open_config_dir, width=14).pack(side="left")
        tk.Button(actions, text="关闭", command=self.help_win.withdraw, width=12).pack(side="right")

    def check_license_on_startup(self) -> None:
        result = self.verify_current_license()
        if self.license_config.require_activation and not result.ok:
            self.status_var.set("需要激活后使用")
            return
        self.status_var.set("已就绪")

    def verify_current_license(self, force: bool = False) -> LicenseResult:
        now = time.time()
        if (
            not force
            and self.license_result is not None
            and self.license_result.ok
            and now - self.license_checked_at < 600
        ):
            return self.license_result
        self.license_config = load_license_config()
        self.license_result = verify_license(self.license_config)
        self.license_checked_at = now
        return self.license_result

    def format_license_status(self, result: LicenseResult | None = None) -> str:
        result = result or self.license_result
        if not self.license_config.require_activation:
            return "授权：当前构建未启用强制激活"
        if result and result.ok:
            suffix = f"，到期：{result.expires_at}" if result.expires_at else ""
            return f"授权：已激活{suffix}"
        message = result.message if result else "尚未校验"
        return f"授权：{message}"

    def ensure_license(self, show_dialog: bool = False) -> bool:
        result = self.verify_current_license()
        if result.ok:
            return True
        self.status_var.set("需要激活后使用")
        if show_dialog:
            self.root.after(0, lambda message=result.message: self.show_activation_window(message))
        return False

    def show_activation_window(self, initial_message: str | None = None) -> None:
        if self.activation_win is not None and self.activation_win.winfo_exists():
            if initial_message:
                self.activation_status_var.set(initial_message)
            else:
                self.activation_status_var.set(self.format_license_status())
            self.activation_win.deiconify()
            self.activation_win.lift()
            return

        self.activation_win = tk.Toplevel(self.root)
        self.activation_win.title("授权激活 - 豆包 ASR 助手")
        self.activation_win.geometry("560x340+460+260")
        self.activation_win.minsize(520, 320)
        self.activation_win.protocol("WM_DELETE_WINDOW", self.activation_win.withdraw)

        frame = tk.Frame(self.activation_win, padx=20, pady=18)
        frame.pack(fill="both", expand=True)

        title = "此版本需要激活后使用" if self.license_config.require_activation else "授权状态"
        tk.Label(frame, text=title, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="激活码会绑定当前电脑。把安装包转发给别人时，对方仍需要自己的激活码。",
            fg="#5d6b82",
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        self.activation_status_var.set(initial_message or self.format_license_status())
        tk.Label(frame, textvariable=self.activation_status_var, fg="#39465e", wraplength=500, justify="left").pack(anchor="w")

        server_text = self.license_config.server_url or "未配置授权服务器"
        tk.Label(frame, text=f"授权服务器：{server_text}", fg="#5d6b82", wraplength=500, justify="left").pack(anchor="w", pady=(10, 0))
        tk.Label(frame, text=f"本机设备码：{device_fingerprint()}", fg="#5d6b82", wraplength=500, justify="left").pack(anchor="w", pady=(4, 14))

        row = tk.Frame(frame)
        row.pack(fill="x")
        tk.Label(row, text="激活码", width=10, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=self.activation_code_var)
        entry.pack(side="left", fill="x", expand=True)

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=(16, 0))
        tk.Button(actions, text="激活", command=self.activate_from_ui, width=12).pack(side="left")
        tk.Button(actions, text="重新校验", command=self.verify_license_from_ui, width=12).pack(side="left", padx=8)
        tk.Button(actions, text="复制设备码", command=self.copy_device_id, width=12).pack(side="left")
        tk.Button(actions, text="关闭", command=self.activation_win.withdraw, width=12).pack(side="right")

        self.activation_win.lift()
        entry.focus_set()

    def copy_device_id(self) -> None:
        self.clipboard.set_text(device_fingerprint())
        self.activation_status_var.set("设备码已复制。")

    def activate_from_ui(self) -> None:
        code = self.activation_code_var.get().strip()
        self.activation_status_var.set("正在激活...")
        threading.Thread(target=self._activate_worker, args=(code,), daemon=True).start()

    def _activate_worker(self, code: str) -> None:
        result = activate_license(self.license_config, code)
        self.root.after(0, lambda: self._handle_activation_result(result))

    def verify_license_from_ui(self) -> None:
        self.activation_status_var.set("正在校验授权...")
        threading.Thread(target=self._verify_license_worker, daemon=True).start()

    def _verify_license_worker(self) -> None:
        result = self.verify_current_license(force=True)
        self.root.after(0, lambda: self._handle_activation_result(result))

    def _handle_activation_result(self, result: LicenseResult) -> None:
        self.license_result = result
        self.license_checked_at = time.time()
        self.activation_status_var.set(self.format_license_status(result))
        self.status_var.set(self.format_license_status(result) if self.license_config.require_activation else "已就绪")
        if result.ok and self.activation_win is not None and self.activation_win.winfo_exists():
            self.activation_win.after(700, self.activation_win.withdraw)

    def _build_float_window(self) -> None:
        self.float_win = tk.Toplevel(self.root)
        self.float_win.title("豆包 ASR")
        self.float_win.geometry("760x220+360+360")
        self.float_win.minsize(FLOAT_MIN_WIDTH, 170)
        self.float_win.attributes("-topmost", True)
        self.float_win.withdraw()
        self.float_win.protocol("WM_DELETE_WINDOW", self.float_win.withdraw)
        frame = tk.Frame(self.float_win, padx=16, pady=14, bg="#ffffff")
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="🎙", font=("Segoe UI Emoji", 18), bg="#ffffff").pack(side="left", anchor="n", padx=(0, 10))
        center = tk.Frame(frame, bg="#ffffff")
        center.pack(side="left", fill="both", expand=True)
        self.float_text = tk.Text(center, height=3, wrap="word", borderwidth=0, font=("Microsoft YaHei UI", 13))
        self.float_text.pack(fill="both", expand=True)
        actions = tk.Frame(center, bg="#ffffff")
        actions.pack(fill="x", pady=(8, 0))
        clear_button = tk.Button(actions, text="清空", command=self.clear_float)
        copy_button = tk.Button(actions, text="复制", command=self.copy_float)
        insert_button = tk.Button(actions, text="插入 ↵", command=lambda: self.insert_text(self.get_float_text(), auto_send=False))
        clear_button.pack(side="left")
        copy_button.pack(side="left", padx=8)
        insert_button.pack(side="right")
        self.float_action_buttons = [clear_button, copy_button, insert_button]

    def _resize_float_window_for_text(self, text: str) -> None:
        self.float_win.update_idletasks()
        screen_width = self.float_win.winfo_screenwidth()
        screen_height = self.float_win.winfo_screenheight()
        scale = max(self.current_ui_scale_factor(), 1.0)
        width = min(max(int(FLOAT_BASE_WIDTH * scale), FLOAT_MIN_WIDTH), FLOAT_MAX_WIDTH, max(FLOAT_MIN_WIDTH, screen_width - 80))
        text_width = max(260, width - int(120 * scale))

        font = tkfont.Font(font=self.float_text["font"])
        line_height = max(font.metrics("linespace"), 18)
        sample_width = max(font.measure("测"), font.measure("M"), 1)
        chars_per_line = max(8, text_width // sample_width)
        paragraphs = text.splitlines() or [""]
        needed_lines = sum(max(1, math.ceil(max(len(paragraph), 1) / chars_per_line)) for paragraph in paragraphs)
        visible_lines = max(3, min(FLOAT_MAX_LINES, needed_lines))
        self.float_needed_lines = needed_lines
        self.float_visible_lines = visible_lines

        self.float_text.configure(height=visible_lines)
        height = int(58 * scale) + line_height * visible_lines
        height = min(max(height, 170), max(170, int(screen_height * 0.58)))

        current_x = self.float_win.winfo_x()
        current_y = self.float_win.winfo_y()
        if current_x <= 0 and current_y <= 0:
            current_x = max(20, (screen_width - width) // 2)
            current_y = max(20, screen_height // 3)
        x = min(max(20, current_x), max(20, screen_width - width - 20))
        y = min(max(20, current_y), max(20, screen_height - height - 60))
        self.float_win.geometry(f"{width}x{height}+{x}+{y}")

    def write_float_layout_report(self, report_path: str | Path, text: str) -> None:
        self.show_float(text)
        self.float_win.update_idletasks()
        text_bounds = self._widget_bounds("float-text", self.float_text)
        button_bounds = [
            bounds
            for index, button in enumerate(self.float_action_buttons)
            for bounds in [self._widget_bounds(f"float-action-{index}", button)]
            if bounds is not None
        ]
        window = {
            "width": self.float_win.winfo_width(),
            "height": self.float_win.winfo_height(),
            "screen_width": self.float_win.winfo_screenwidth(),
            "screen_height": self.float_win.winfo_screenheight(),
        }
        report = {
            "text_chars": len(text),
            "stored_text_chars": len(self.get_float_text()),
            "text_equal_input": self.get_float_text() == text,
            "window": window,
            "text_widget": text_bounds,
            "action_buttons": button_bounds,
            "wrap": self.float_text.cget("wrap"),
            "yview": self.float_text.yview(),
            "needed_lines": self.float_needed_lines,
            "visible_lines": self.float_visible_lines,
            "fits_text_sample": self.float_needed_lines <= self.float_visible_lines,
            "fits_screen": window["width"] <= window["screen_width"] and window["height"] <= window["screen_height"],
        }
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_from_ui(self) -> None:
        conflict = self.find_hotkey_conflict()
        if conflict:
            messagebox.showwarning("快捷键冲突", conflict)
            self.status_var.set("快捷键冲突，请调整后再保存")
            return
        for field, (minimum, maximum, step) in DELAY_SPECS.items():
            self._sync_delay_from_entry(field, minimum, maximum, step)
        for key, entry in self.entries.items():
            value: str | int = entry.get().strip()
            if key.endswith("_ms"):
                try:
                    value = int(value)
                except ValueError:
                    messagebox.showwarning("配置错误", f"{key} 必须是数字。")
                    self.status_var.set("配置错误，请检查数字项")
                    return
            elif key in HOTKEY_LABELS:
                value = canonical_hotkey_value(value)
            elif key == "credential_path":
                value = str(resolve_user_path(value))
            setattr(self.config, key, value)
        self.config.protect_clipboard = self.vars["protect_clipboard"].get()
        self.config.startup = self.vars["startup"].get()
        save_config(self.config)
        for field in HOTKEY_LABELS:
            entry = self.entries.get(field)
            if entry is not None:
                entry.delete(0, "end")
                entry.insert(0, display_hotkey_value(str(getattr(self.config, field))))
        self.status_var.set("配置已保存")

    def reset_settings_to_defaults(self) -> None:
        self.config = reset_config_to_defaults(self.config, preserve_credential_path=True)
        for key, entry in self.entries.items():
            if key in self.delay_vars:
                continue
            value = display_hotkey_value(str(getattr(self.config, key))) if key in HOTKEY_LABELS else str(getattr(self.config, key))
            entry.delete(0, "end")
            entry.insert(0, value)
        for key, var in self.delay_vars.items():
            var.set(int(getattr(self.config, key)))
            self._sync_delay_entry(key)
        self.vars["protect_clipboard"].set(self.config.protect_clipboard)
        self.vars["startup"].set(self.config.startup)
        self._sync_option_toggle_styles()
        save_config(self.config)
        self.status_var.set("已恢复默认设置，凭据文件路径已保留")

    def find_hotkey_conflict(self) -> str | None:
        return hotkey_conflict_from_values({field: self.entries[field].get() for field in HOTKEY_LABELS})

    def _start_listeners(self) -> None:
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        name = key_name(key)
        if not name:
            return
        self.active_keys.add(name)
        if self.recording_field:
            self.status_var.set(f"正在录制：{display_hotkey_value(self.active_keys)}")
            return
        self._handle_active_press(name)

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        name = key_name(key)
        if not name:
            return
        if self.recording_field and self.active_keys:
            self._finish_key_record(format_hotkey(self.active_keys))
            self.active_keys.clear()
            return
        self._discard_active_key(name)
        self._handle_active_release(name)

    def _on_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        name = mouse_name(button)
        if not name:
            return
        if pressed and self.recording_field:
            self._finish_key_record(name)
            self.active_keys.clear()
            return
        if pressed:
            self.active_keys.add(name)
            self._handle_active_press(name)
        else:
            self._discard_active_key(name)
            self._handle_active_release(name)

    def _discard_active_key(self, name: str) -> None:
        for variant in key_release_variants(name):
            self.active_keys.discard(variant)

    def _finish_key_record(self, value: str) -> None:
        field = self.recording_field
        self.recording_field = None
        if field and value:
            values = {hotkey_field: self.entries[hotkey_field].get() for hotkey_field in HOTKEY_LABELS}
            values[field] = value
            conflict = hotkey_conflict_from_values(values)
            if conflict:
                messagebox.showwarning("快捷键冲突", conflict)
                self.status_var.set("快捷键冲突，请重新录制")
                return
            display_value = display_hotkey_value(value)
            self.entries[field].delete(0, "end")
            self.entries[field].insert(0, display_value)
            self.status_var.set(f"已录制：{display_value}，点击保存配置生效")

    def _handle_active_press(self, name: str) -> None:
        cancel_key = parse_hotkey(self.config.cancel_key)
        toggle_key = parse_hotkey(self.config.toggle_key)
        if self.recording_mode and active_matches(self.active_keys, cancel_key):
            self.cancelled = True
            self.stop_recording()
            return
        if self.recording_mode == "toggle" and active_matches(self.active_keys, toggle_key):
            self.stop_recording()
            return
        if self.recording_mode:
            return
        mode = idle_start_mode_for_active_keys(name, self.active_keys, self.config)
        if mode:
            self.start_recording(mode)

    def _handle_active_release(self, released_name: str) -> None:
        if should_stop_hold_on_release(self.recording_mode, released_name, self.active_keys, self.config):
            self.stop_recording()

    def start_recording(self, mode: str) -> None:
        if not self.ensure_license(show_dialog=False):
            return
        self.target_hwnd = get_foreground_window()
        self.recording_session_id += 1
        session_id = self.recording_session_id
        self.recording_mode = mode
        self.pending_mode = None
        self.cancelled = False
        self.final_text = ""
        self.transcript = TranscriptAccumulator()
        audio_queue: queue.Queue[bytes | None] = queue.Queue()
        self.audio_queue = audio_queue
        try:
            self.audio_stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=320,
                callback=lambda indata, frames, time_info, status: self._audio_callback(
                    audio_queue,
                    indata,
                    frames,
                    time_info,
                    status,
                ),
            )
            self.audio_stream.start()
            self.asr_thread = threading.Thread(target=self._run_asr_thread, args=(session_id, audio_queue), daemon=True)
            self.asr_thread.start()
        except Exception as exc:
            self.recording_mode = None
            self.pending_mode = None
            self.audio_queue = None
            if self.audio_stream is not None:
                try:
                    self.audio_stream.close()
                except Exception:
                    pass
                self.audio_stream = None
            self.status_var.set(f"录音启动失败：{exc}")
            self.schedule_ui(0, lambda msg=str(exc): self.show_float(f"录音启动失败：{msg}"))
            self.schedule_ui(2200, self.hide_float)
            return
        self.schedule_ui(0, lambda sid=session_id: self.show_recording_start_float(sid))
        self.status_var.set("正在录音")

    def stop_recording(self) -> None:
        if not self.recording_mode:
            return
        mode = self.recording_mode
        self.recording_mode = None
        self.pending_mode = mode
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
        if self.audio_queue:
            self.audio_queue.put(None)
        self.status_var.set("正在识别")
        if should_show_stop_state_in_float(mode, self.cancelled):
            if self.cancelled:
                self.schedule_ui(0, lambda: self.show_float("已取消"))
                self.schedule_ui(900, self.hide_float)
            else:
                self.schedule_ui(0, lambda: self.show_float("正在识别..."))
        else:
            self.schedule_ui(0, self.hide_float)

    def _audio_callback(self, audio_queue: queue.Queue[bytes | None], indata, _frames, _time_info, status) -> None:
        if status:
            print(status)
        audio_queue.put(bytes(indata))

    def _run_asr_thread(self, session_id: int, audio_queue: queue.Queue[bytes | None]) -> None:
        async def source() -> Iterable[bytes]:
            while True:
                chunk = await _run_blocking(audio_queue.get)
                if chunk is None:
                    break
                yield chunk

        async def runner() -> None:
            transcript = TranscriptAccumulator()
            final_text = ""
            config = ASRConfig(credential_path=str(resolve_user_path(self.config.credential_path)))
            async for response in transcribe_realtime(source(), config=config):
                if response.type in {ResponseType.INTERIM_RESULT, ResponseType.FINAL_RESULT} and response.text:
                    final_text = self._update_asr_text(session_id, transcript, final_text, response)
                    self.schedule_ui(0, lambda value=final_text, sid=session_id: self.show_recognition_float(sid, value))
                if response.type == ResponseType.ERROR:
                    self.schedule_ui(0, lambda msg=response.error_msg, sid=session_id: self.show_recognition_error(sid, msg))

        try:
            asyncio.run(runner())
            self.schedule_ui(0, lambda sid=session_id: self._finish_insert(sid))
        except Exception as exc:
            self.schedule_ui(0, lambda msg=str(exc), sid=session_id: self.show_recognition_error(sid, msg))

    def _update_asr_text(self, session_id: int, transcript: TranscriptAccumulator, current_text: str, response) -> str:
        if response.text:
            current_text = transcript.update(
                response.text,
                is_final=response.type == ResponseType.FINAL_RESULT,
            )
            if is_current_recording_session(session_id, self.recording_session_id):
                self.final_text = current_text
        return current_text

    def _finish_insert(self, session_id: int | None = None) -> None:
        if session_id is not None and not is_current_recording_session(session_id, self.recording_session_id):
            return
        self.status_var.set("识别完成")
        pending_mode = self.pending_mode
        if self.cancelled:
            self.hide_float()
            self.pending_mode = None
            return
        if not self.final_text:
            if pending_mode in HOLD_RECORDING_MODES:
                self.hide_float()
            else:
                self.show_float("未识别到语音")
                self.schedule_ui(1200, self.hide_float)
            self.pending_mode = None
            return
        auto_send = pending_mode == "hold_send"
        if pending_mode in HOLD_RECORDING_MODES:
            self.hide_float()
        text_to_insert = self.final_text
        target_hwnd = self.target_hwnd
        self.schedule_ui(
            self.config.insert_delay_ms,
            lambda sid=session_id, value=text_to_insert, hwnd=target_hwnd: self.insert_text_for_session(
                sid,
                value,
                auto_send=auto_send,
                target_hwnd=hwnd,
                allow_completed=True,
            ),
        )
        self.pending_mode = None

    def show_recording_start_float(self, session_id: int) -> None:
        if is_current_recording_session(session_id, self.recording_session_id) and self.recording_mode is not None:
            self.show_float("正在听...")

    def show_recognition_float(self, session_id: int, text: str) -> None:
        if is_current_recording_session(session_id, self.recording_session_id) and should_show_recognition_float(self.recording_mode, self.pending_mode):
            self.show_float(text)

    def show_recognition_error(self, session_id: int, message: str) -> None:
        if not is_current_recording_session(session_id, self.recording_session_id):
            return
        self.status_var.set(f"识别错误：{message}")
        if should_show_recognition_float(self.recording_mode, self.pending_mode):
            self.show_float(f"错误：{message}")
        else:
            self.hide_float()

    def show_float(self, text: str) -> None:
        self.float_text.delete("1.0", "end")
        self.float_text.insert("1.0", text)
        self._resize_float_window_for_text(text)
        self.float_win.deiconify()
        self.float_win.lift()

    def hide_float(self) -> None:
        self.float_win.withdraw()

    def get_float_text(self) -> str:
        return self.float_text.get("1.0", "end").strip()

    def clear_float(self) -> None:
        self.float_text.delete("1.0", "end")

    def copy_float(self) -> None:
        self.clipboard.set_text(self.get_float_text())
        self.status_var.set("已复制")

    def insert_text_for_session(
        self,
        session_id: int | None,
        text: str,
        auto_send: bool,
        target_hwnd: int | None,
        allow_completed: bool = False,
    ) -> None:
        if (
            session_id is not None
            and not allow_completed
            and not is_current_recording_session(session_id, self.recording_session_id)
        ):
            return
        self.insert_text(text, auto_send=auto_send, target_hwnd=target_hwnd)

    def insert_text(self, text: str, auto_send: bool, target_hwnd: int | None = None) -> None:
        destination_hwnd = self.target_hwnd if target_hwnd is None else target_hwnd
        paste_text_with_clipboard_protection(
            self.clipboard,
            text,
            protect_clipboard=self.config.protect_clipboard,
            restore_delay_ms=self.config.clipboard_restore_delay_ms,
            target_hwnd=destination_hwnd,
            schedule_ui=self.schedule_ui,
            auto_send=auto_send,
            auto_send_delay_ms=self.config.auto_send_delay_ms,
        )


def simulate_hold_release_auto_insert_cases() -> list[dict[str, object]]:
    class FakeStatus:
        def __init__(self) -> None:
            self.values: list[str] = []

        def set(self, value: str) -> None:
            self.values.append(value)

    class FakeStream:
        def __init__(self) -> None:
            self.stopped = False
            self.closed = False

        def stop(self) -> None:
            self.stopped = True

        def close(self) -> None:
            self.closed = True

    def build_app(
        mode: str,
        *,
        auto_run_callbacks: bool = True,
    ) -> tuple[DesktopApp, list[dict[str, object]], list[dict[str, object]], FakeStream]:
        app = DesktopApp.__new__(DesktopApp)
        app.config = DesktopConfig(insert_delay_ms=0)
        app.recording_session_id = 9001
        app.recording_mode = mode
        app.pending_mode = None
        app.cancelled = False
        app.final_text = ""
        app.target_hwnd = 24680
        app.active_keys = {"rctrl"} if mode == "hold" else {"lctrl", "lwin"}
        app.audio_queue = queue.Queue()
        stream = FakeStream()
        app.audio_stream = stream
        app.status_var = FakeStatus()
        scheduled: list[dict[str, object]] = []
        inserted: list[dict[str, object]] = []

        def schedule_ui(delay_ms: int, callback: Callable[[], None]) -> object:
            scheduled.append({"delay_ms": delay_ms, "callback": callback})
            if auto_run_callbacks:
                callback()
            return object()

        app.schedule_ui = schedule_ui  # type: ignore[method-assign]
        app.hide_float = lambda: None  # type: ignore[method-assign]
        app.show_float = lambda _text: None  # type: ignore[method-assign]
        app.insert_text = (  # type: ignore[method-assign]
            lambda text, auto_send, target_hwnd=None: inserted.append(
                {"text": text, "auto_send": auto_send, "target_hwnd": target_hwnd}
            )
        )
        return app, scheduled, inserted, stream

    cases: list[dict[str, object]] = []
    for mode, released_key, expected_auto_send in (
        ("hold", "rctrl", False),
        ("hold_send", "lwin", True),
    ):
        app, scheduled, inserted, stream = build_app(mode)
        expected_text = f"{mode} release auto insert"
        app._handle_active_release(released_key)
        app.final_text = expected_text
        app._finish_insert(app.recording_session_id)
        expected_insert = [{"text": expected_text, "auto_send": expected_auto_send, "target_hwnd": 24680}]
        cases.append(
            {
                "mode": mode,
                "released_key": released_key,
                "stopped_on_release": app.recording_mode is None,
                "stream_stopped": stream.stopped,
                "stream_closed": stream.closed,
                "insert_scheduled": any(item["delay_ms"] == 0 for item in scheduled),
                "inserted": inserted,
                "expected_insert": expected_insert,
                "ok": inserted == expected_insert and app.pending_mode is None and stream.stopped and stream.closed,
            }
        )

    app, _scheduled, inserted, _stream = build_app("hold")
    app.cancelled = True
    app._handle_active_release("rctrl")
    app.final_text = "cancelled text"
    app._finish_insert(app.recording_session_id)
    cases.append({"mode": "hold_cancelled", "inserted": inserted, "ok": inserted == []})

    app, _scheduled, inserted, _stream = build_app("hold")
    app._handle_active_release("rctrl")
    app._finish_insert(app.recording_session_id)
    cases.append({"mode": "hold_empty", "inserted": inserted, "ok": inserted == []})

    app, scheduled, inserted, _stream = build_app("hold", auto_run_callbacks=False)
    app._handle_active_release("rctrl")
    app.final_text = "delayed insert survives next recording"
    original_session_id = app.recording_session_id
    app._finish_insert(original_session_id)
    app.recording_session_id += 1
    for item in scheduled:
        if item["delay_ms"] == 0:
            callback = item.get("callback")
            if callable(callback):
                callback()
    cases.append(
        {
            "mode": "hold_delayed_after_restart",
            "original_session_id": original_session_id,
            "current_session_id": app.recording_session_id,
            "inserted": inserted,
            "ok": inserted == [
                {
                    "text": "delayed insert survives next recording",
                    "auto_send": False,
                    "target_hwnd": 24680,
                }
            ],
        }
    )
    return cases


def run_hold_release_auto_insert_test(report_path: str | None = None) -> int:
    cases = simulate_hold_release_auto_insert_cases()
    report = {
        "ok": all(bool(case["ok"]) for case in cases),
        "test_id": "T01-auto-insert",
        "name": "Hold release automatically inserts recognized text",
        "scope": "source/packaged logic smoke; no manual float button click",
        "cases": cases,
    }
    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-hold-release-auto-insert.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def get_foreground_window() -> int:
    try:
        import ctypes

        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return 0


def set_foreground_window(hwnd: int) -> None:
    try:
        import ctypes

        root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd
        ctypes.windll.user32.ShowWindow(root_hwnd, 5)
        ctypes.windll.user32.BringWindowToTop(root_hwnd)
        ctypes.windll.user32.SetForegroundWindow(root_hwnd)
    except Exception:
        pass


def send_key(vk: int, up: bool = False) -> None:
    import ctypes

    ctypes.windll.user32.keybd_event(vk, 0, 2 if up else 0, 0)


def send_ctrl_v() -> None:
    send_key(0x11)
    send_key(0x56)
    send_key(0x56, up=True)
    send_key(0x11, up=True)


def send_enter() -> None:
    send_key(0x0D)
    send_key(0x0D, up=True)


def run_self_test(report_path: str | None = None) -> int:
    report = {
        "ok": True,
        "executable": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python_version": sys.version,
        "platform": sys.platform,
        "app_config_dir": str(APP_CONFIG_DIR),
        "checks": [],
    }

    def check(name: str, func, required: bool = True) -> None:
        try:
            detail = func()
            report["checks"].append({"name": name, "ok": True, "required": required, "detail": detail})
        except Exception as exc:
            report["checks"].append({"name": name, "ok": False, "required": required, "error": repr(exc)})
            if required:
                report["ok"] = False

    config = load_config()
    credential_path = resolve_user_path(config.credential_path)
    license_config = load_license_config()
    report["credential_path"] = str(credential_path)
    report["license_config"] = {
        "require_activation": license_config.require_activation,
        "server_url_configured": bool(license_config.server_url),
    }

    def config_dir_check() -> str:
        APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        marker = APP_CONFIG_DIR / ".self-test.tmp"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return "config directory is writable"

    def credential_path_check() -> str:
        credential_path.parent.mkdir(parents=True, exist_ok=True)
        marker = credential_path.parent / ".credential-write-test.tmp"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return "credential cache directory is writable"

    def hotkey_check() -> str:
        conflict = hotkey_conflict_from_values({field: getattr(config, field) for field in HOTKEY_LABELS})
        if conflict:
            raise ValueError(conflict)
        dangerous_values = {field: getattr(DesktopConfig(), field) for field in HOTKEY_LABELS}
        dangerous_values["toggle_key"] = "x"
        if hotkey_conflict_from_values(dangerous_values) is None:
            raise ValueError("bare text hotkey was not rejected")
        if idle_start_hotkey_allowed(parse_hotkey("x")):
            raise ValueError("single text key should not start recording while idle")
        for risky_single_modifier in ("左 Ctrl", "Alt", "左 Alt", "Win", "左 Win", "Shift"):
            values = {field: getattr(DesktopConfig(), field) for field in HOTKEY_LABELS}
            values["hold_key"] = risky_single_modifier
            if hotkey_conflict_from_values(values) is None:
                raise ValueError(f"risky single modifier was not rejected: {risky_single_modifier}")
        dangerous_config = DesktopConfig(toggle_key="x")
        active: set[str] = set()
        for char in "xian":
            active.add(char)
            if idle_start_mode_for_active_keys(char, active, dangerous_config):
                raise ValueError("typing xian would start recording")
            active.discard(char)
        default_config = DesktopConfig()
        if idle_start_mode_for_active_keys("rctrl", {"rctrl"}, default_config) != "hold":
            raise ValueError("default hold key no longer starts hold recording")
        if idle_start_mode_for_active_keys("rctrl", {"lctrl", "rctrl"}, default_config):
            raise ValueError("pressing both Ctrl sides should not match the default right-Ctrl hold key")
        if "rctrl" not in key_release_variants("ctrl"):
            raise ValueError("generic Ctrl release would leave right Ctrl stuck")
        if not should_stop_hold_on_release("hold", "ctrl", {"rctrl"}, default_config):
            raise ValueError("generic Ctrl release should stop default hold recording")
        if should_stop_hold_on_release("hold", "lalt", {"rctrl"}, default_config):
            raise ValueError("releasing an extra Alt key should not stop right-Ctrl hold recording")
        if idle_start_mode_for_active_keys("rctrl", {"rctrl", "lalt"}, default_config):
            raise ValueError("default hold key should require an exact active key set")
        if idle_start_mode_for_active_keys("xbutton1", {"xbutton1"}, default_config) != "toggle":
            raise ValueError("default mouse side key no longer starts toggle recording")
        if idle_start_mode_for_active_keys("xbutton1", {"xbutton1", "lshift"}, default_config):
            raise ValueError("mouse side key should not start while extra modifiers are held")
        if idle_start_mode_for_active_keys("lwin", {"lctrl", "lwin"}, default_config) != "hold_send":
            raise ValueError("default hold-send combo no longer starts hold_send recording")
        if not should_stop_hold_on_release("hold_send", "win", {"lctrl", "lwin"}, default_config):
            raise ValueError("generic Win release should stop hold-send recording")
        if idle_start_mode_for_active_keys("lwin", {"lctrl", "lwin", "d"}, default_config):
            raise ValueError("hold-send combo should not start when extra keys are already active")
        if not should_show_recognition_float("hold", None):
            raise ValueError("hold mode should show the floating transcript while the key is held")
        if should_show_recognition_float(None, "hold"):
            raise ValueError("hold mode should hide the floating transcript after release")
        if should_show_recognition_float(None, "hold_send"):
            raise ValueError("hold-send mode should hide the floating transcript after release")
        if not should_show_recognition_float(None, "toggle"):
            raise ValueError("toggle mode should keep the floating transcript visible after stop")
        if should_show_stop_state_in_float("hold", False):
            raise ValueError("hold mode should not show a persistent recognition state after release")
        if not should_show_stop_state_in_float("toggle", False):
            raise ValueError("toggle mode should show recognition state after stop")
        if not is_current_recording_session(7, 7):
            raise ValueError("current ASR session updates should be accepted")
        if is_current_recording_session(6, 7):
            raise ValueError("stale ASR session updates should be ignored")
        strict_config = DesktopConfig(toggle_key="ctrl+d")
        if idle_start_mode_for_active_keys("d", {"lctrl", "d"}, strict_config) != "toggle":
            raise ValueError("generic Ctrl combo should match either physical Ctrl side")
        if idle_start_mode_for_active_keys("d", {"lctrl", "rctrl", "d"}, strict_config):
            raise ValueError("generic Ctrl combo should reject both Ctrl sides as an extra-key match")
        if idle_start_mode_for_active_keys("d", {"lctrl", "lalt", "d"}, strict_config):
            raise ValueError("Ctrl+D should not start from Ctrl+Alt+D")
        if key_name(keyboard.Key.alt) != "alt":
            raise ValueError("generic Alt key is not captured")
        if format_hotkey({key_name(keyboard.Key.alt), "m"}) != "alt+m":
            raise ValueError("Alt+M hotkey capture would lose Alt")
        if parse_hotkey("atl+m") != frozenset({"alt", "m"}):
            raise ValueError("common Alt typo alias is not normalized")
        if canonical_hotkey_value("右 Ctrl") != "rctrl":
            raise ValueError("right Ctrl display label is not parsed")
        if canonical_hotkey_value("左 Ctrl + 左 Win") != "lctrl+lwin":
            raise ValueError("left Ctrl + left Win display label is not parsed")
        if display_hotkey_value("rctrl") != "右 Ctrl":
            raise ValueError("right Ctrl is not shown as a user-facing label")
        if display_hotkey_value("lctrl+lwin") != "左 Ctrl + 左 Win":
            raise ValueError("left Ctrl + left Win is not shown as user-facing labels")
        if generic_hotkey(parse_hotkey("lalt+m")) != frozenset({"alt", "m"}):
            raise ValueError("left/right modifier aliases are not normalized for conflict checks")
        if hotkey_vk(parse_hotkey("alt+m")) != ord("M"):
            raise ValueError("Alt+M cannot be converted to a Windows hotkey probe")
        if system_hotkey_conflict(parse_hotkey("alt+tab")) is None:
            raise ValueError("reserved Windows hotkey was not rejected")
        custom_config = DesktopConfig(
            hold_key="alt+m",
            toggle_key="xbutton2",
            hold_send_key="ctrl+shift+m",
            cancel_key="f12",
            doubao_hotkey="ctrl+shift+d",
            insert_delay_ms=900,
            auto_send_delay_ms=120,
            protect_clipboard=False,
            startup=True,
            credential_path=str(APP_CONFIG_DIR / "custom-credentials.json"),
        )
        reset_config = reset_config_to_defaults(custom_config)
        defaults = DesktopConfig()
        for field in RESETTABLE_CONFIG_FIELDS:
            if getattr(reset_config, field) != getattr(defaults, field):
                raise ValueError(f"default reset did not restore {field}")
        if reset_config.credential_path != str(resolve_user_path(custom_config.credential_path)):
            raise ValueError("default reset should preserve the credential path")
        return "configured hotkeys are valid, hold release cleanup is covered, stale ASR sessions are ignored, hold floats hide after release, xian typing is safe, Alt combos are captured, Windows conflicts are checked, and default reset is safe"

    def auto_insert_check() -> str:
        cases = simulate_hold_release_auto_insert_cases()
        failed = [case for case in cases if not case["ok"]]
        if failed:
            raise ValueError(f"hold release auto-insert failed: {failed}")
        return "hold and hold-send release paths schedule insertion automatically without the float Insert button; cancelled, empty, and delayed-after-next-recording cases are safe"

    def delay_snap_check() -> str:
        for field, (minimum, maximum, step) in DELAY_SPECS.items():
            if step != 50:
                raise ValueError(f"{field} should snap in 50ms steps")
            if snap_delay_value(492, minimum, maximum, step) != 500:
                raise ValueError(f"{field} did not snap 492ms to 500ms")
            expected_low_value = minimum if 92 < minimum else 100
            if snap_delay_value(92, minimum, maximum, step) != expected_low_value:
                raise ValueError(f"{field} did not snap/clamp 92ms to {expected_low_value}ms")
            if snap_delay_value(maximum + 100, minimum, maximum, step) != maximum:
                raise ValueError(f"{field} did not clamp at max")
        normalized = normalize_config(DesktopConfig(insert_delay_ms=492, auto_send_delay_ms=92))
        if normalized.insert_delay_ms != 500 or normalized.auto_send_delay_ms != 100:
            raise ValueError("loaded delay config values are not normalized to 50ms steps")
        return "delay sliders snap to 50ms magnetic steps"

    def opus_check() -> str:
        encoder = AudioEncoder(ASRConfig(credential_path=str(credential_path)))
        frames = encoder.pcm_to_opus_frames(b"\x00" * 640)
        if not frames:
            raise RuntimeError("Opus encoder returned no frames")
        return f"encoded {len(frames)} frame(s)"

    def sounddevice_check() -> str:
        devices = sd.query_devices()
        input_count = sum(1 for device in devices if int(device.get("max_input_channels", 0)) > 0)
        if input_count == 0:
            raise RuntimeError("No input audio devices found")
        return f"{input_count} input audio device(s) found"

    def input_control_check() -> str:
        keyboard.Controller()
        mouse.Controller()
        get_foreground_window()
        return "keyboard, mouse, and foreground window APIs are available"

    def tray_api_check() -> str:
        if sys.platform != "win32":
            return "system tray is Windows-only; skipped on this platform"
        if not WindowsTrayIcon.is_supported():
            raise RuntimeError("Windows notification area APIs are unavailable")
        ctypes.windll.shell32.Shell_NotifyIconW
        return "Windows notification area APIs are available"

    def single_instance_check() -> str:
        if not SingleInstanceGuard.is_supported():
            return "single-instance mutex is Windows-only; skipped on this platform"
        mutex_name = f"Local\\DoubaoASRHelper.SelfTest.{os.getpid()}.{time.time_ns()}"
        first = SingleInstanceGuard(mutex_name=mutex_name)
        second = SingleInstanceGuard(mutex_name=mutex_name)
        try:
            if not first.acquire():
                raise ValueError("first single-instance guard reported an existing instance")
            if second.acquire():
                raise ValueError("second single-instance guard acquired the same mutex")
            if not second.already_running:
                raise ValueError("second single-instance guard did not report already_running")
        finally:
            second.release()
            first.release()
        third = SingleInstanceGuard(mutex_name=mutex_name)
        try:
            if not third.acquire():
                raise ValueError("single-instance mutex was not released after closing guards")
        finally:
            third.release()
        return "single-instance mutex prevents duplicate desktop/tray processes"

    def app_icon_check() -> str:
        icon_path = app_icon_path()
        if icon_path is None:
            raise RuntimeError("App icon resource is missing")
        if icon_path.stat().st_size < 1024:
            raise RuntimeError(f"App icon resource is unexpectedly small: {icon_path}")
        report["app_icon"] = {
            "path": str(icon_path),
            "size": icon_path.stat().st_size,
        }
        return f"app icon is available at {icon_path}"

    def help_text_check() -> str:
        required = ["豆包 ASR 助手使用说明", "首次运行", "默认快捷键", "系统托盘", "常见问题", "卸载"]
        missing = [item for item in required if item not in HELP_TEXT]
        if missing:
            raise RuntimeError(f"Help text is missing required section(s): {missing}")
        return f"embedded help has {len(HELP_TEXT)} characters"

    def license_config_check() -> str:
        if license_config.require_activation and not license_config.server_url:
            raise RuntimeError("activation is required but license server URL is empty")
        mode = "required" if license_config.require_activation else "disabled"
        return f"activation mode is {mode}"

    def license_state_check() -> str:
        result = verify_license(license_config)
        report["license_state"] = {
            "ok": result.ok,
            "message": result.message,
            "expires_at": result.expires_at,
            "code": result.code,
        }
        if not result.ok:
            return f"license is not currently valid: {result.message}"
        return result.message

    check("config_dir", config_dir_check)
    check("credential_path", credential_path_check)
    check("hotkeys", hotkey_check)
    check("auto_insert", auto_insert_check)
    check("delay_snap", delay_snap_check)
    check("opus_encoder", opus_check)
    check("audio_devices", sounddevice_check)
    check("input_control", input_control_check)
    check("system_tray_api", tray_api_check)
    check("single_instance", single_instance_check)
    check("app_icon", app_icon_check)
    check("help_text", help_text_check)
    check("license_config", license_config_check)
    check("license_state", license_state_check, required=False)

    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-self-test.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def run_tray_self_test(report_path: str | None = None) -> int:
    icon_path = app_icon_path()
    report = {
        "ok": False,
        "platform": sys.platform,
        "supported": WindowsTrayIcon.is_supported(),
        "icon_path": str(icon_path) if icon_path else None,
        "icon_exists": bool(icon_path and icon_path.exists()),
        "icon_loaded_from_file": False,
        "loaded_icon_path": None,
        "icon_load_error": None,
        "started": False,
        "stopped": False,
        "error": None,
    }

    tray: WindowsTrayIcon | None = None
    try:
        if not WindowsTrayIcon.is_supported():
            raise RuntimeError("Windows system tray is not supported on this platform")
        if icon_path is None:
            raise RuntimeError("App icon resource is missing")
        tray = WindowsTrayIcon("豆包 ASR 助手 - 托盘测试", lambda _action: None, icon_path=icon_path)
        report["started"] = tray.start(wait=True, timeout=3.0)
        report["icon_loaded_from_file"] = tray.icon_loaded_from_file
        report["loaded_icon_path"] = tray.loaded_icon_path
        report["icon_load_error"] = tray.icon_load_error
        if not report["started"]:
            raise RuntimeError(tray.last_error or "Timed out waiting for tray icon")
        if not report["icon_loaded_from_file"]:
            raise RuntimeError(tray.icon_load_error or "Tray icon fell back to the Windows default icon")
        time.sleep(0.5)
        tray.stop()
        report["stopped"] = not tray.is_alive()
        if not report["stopped"]:
            raise RuntimeError("Tray message loop did not stop cleanly")
        report["ok"] = True
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        if tray is not None:
            tray.stop()
        destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-tray-test.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def run_float_layout_test(report_path: str | None = None, text: str | None = None) -> int:
    sample = text or (
        "啊，我这啊？我自己是行不行？感觉好像还可以，嗯，"
        "我试一下整个系统的正确率怎么样，如果把时间跨度拉长，"
        "可能正确率就会有所下降，但总体来说是还可以。"
    )
    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-float-layout.json"
    app: DesktopApp | None = None
    try:
        app = DesktopApp(hidden=True)
        app.write_float_layout_report(destination, sample)
        report = json.loads(destination.read_text(encoding="utf-8"))
        return 0 if report.get("fits_text_sample") and report.get("fits_screen") else 1
    finally:
        if app is not None:
            app.quit_app()


def run_clipboard_insert_test(report_path: str | None = None) -> int:
    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-clipboard-insert.json"
    report = {
        "ok": False,
        "test_id": "T09",
        "name": "Clipboard text protection insertion smoke",
        "restore_delay_ms": DesktopConfig().clipboard_restore_delay_ms,
        "target": "temporary Tk text box",
        "paste_method": "clipboard helper plus Tk <<Paste>> event",
        "text_inserted": False,
        "clipboard_restored": False,
        "error": None,
    }
    root: tk.Tk | None = None
    previous_snapshot: ClipboardSnapshot | None = None
    try:
        root = tk.Tk()
        root.title("Doubao ASR Clipboard Insert Test")
        root.geometry("460x160+80+80")
        root.attributes("-topmost", True)
        target = tk.Text(root, width=40, height=5)
        target.pack(fill="both", expand=True)
        for _ in range(5):
            root.update()
            root.deiconify()
            root.lift()
            set_foreground_window(root.winfo_id())
            target.focus_force()
            root.update()
            time.sleep(0.1)

        clipboard = Clipboard(root)
        previous_snapshot = clipboard.create_snapshot()
        original = "T09_ORIGINAL_CLIPBOARD_TEXT"
        inserted = "T09_INSERTED_TEXT_剪贴板保护"
        clipboard.set_text(original)

        def schedule_ui(delay_ms: int, callback: Callable[[], None]) -> object:
            return root.after(delay_ms, callback)

        paste_text_with_clipboard_protection(
            clipboard,
            inserted,
            protect_clipboard=True,
            restore_delay_ms=DesktopConfig().clipboard_restore_delay_ms,
            target_hwnd=None,
            schedule_ui=schedule_ui,
        )
        target.event_generate("<<Paste>>")

        deadline = time.time() + 2.0
        while time.time() < deadline:
            root.update()
            time.sleep(0.01)

        target_text = target.get("1.0", "end").strip()
        clipboard_after = clipboard.get_text()
        report.update(
            {
                "target_text": target_text,
                "clipboard_after": clipboard_after,
                "text_inserted": inserted in target_text,
                "clipboard_restored": clipboard_after == original,
            }
        )
        report["ok"] = bool(report["text_inserted"] and report["clipboard_restored"])
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        if root is not None:
            try:
                if previous_snapshot is not None:
                    Clipboard(root).restore_snapshot(previous_snapshot)
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def run_clipboard_complex_test(report_path: str | None = None) -> int:
    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-clipboard-complex.json"
    report = {
        "ok": False,
        "test_id": "T10",
        "name": "Complex clipboard format restore smoke",
        "target": "temporary Tk text box",
        "restore_delay_ms": DesktopConfig().clipboard_restore_delay_ms,
        "native_clipboard_available": sys.platform == "win32" and hasattr(ctypes, "windll"),
        "stage": "start",
        "cases": [],
        "error": None,
    }
    root: tk.Tk | None = None
    previous_snapshot: ClipboardSnapshot | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    def write_report() -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        write_report()
        if not report["native_clipboard_available"]:
            raise RuntimeError("Windows native clipboard APIs are required for complex clipboard testing.")

        report["stage"] = "create_tk_root"
        write_report()
        root = tk.Tk()
        root.title("Doubao ASR Complex Clipboard Test")
        root.geometry("460x160+100+100")
        root.attributes("-topmost", True)
        target = tk.Text(root, width=40, height=5)
        target.pack(fill="both", expand=True)
        for _ in range(5):
            root.update()
            root.deiconify()
            root.lift()
            set_foreground_window(root.winfo_id())
            target.focus_force()
            root.update()
            time.sleep(0.1)

        clipboard = Clipboard(root)
        report["stage"] = "snapshot_previous"
        write_report()
        previous_snapshot = clipboard.create_snapshot()
        temp_dir = tempfile.TemporaryDirectory(prefix="DoubaoASRClipboard-")
        sample_file = Path(temp_dir.name) / "clipboard-file.txt"
        sample_file.write_text("Doubao ASR clipboard file payload", encoding="utf-8")

        cases = [
            {
                "name": "CF_DIB image",
                "formats": {8: build_test_dib_payload()},
                "inserted": "T10_INSERTED_TEXT_IMAGE_CLIPBOARD",
            },
            {
                "name": "CF_HDROP file list",
                "formats": {15: build_test_hdrop_payload(sample_file)},
                "inserted": "T10_INSERTED_TEXT_FILE_CLIPBOARD",
            },
        ]

        for case in cases:
            report["stage"] = f"set_original_{case['name']}"
            write_report()
            target.delete("1.0", "end")
            expected_formats: dict[int, bytes] = case["formats"]  # type: ignore[assignment]
            set_windows_clipboard_formats(expected_formats, hwnd=root.winfo_id())
            report["stage"] = f"snapshot_before_{case['name']}"
            write_report()
            before = clipboard.create_snapshot()

            def schedule_ui(delay_ms: int, callback: Callable[[], None]) -> object:
                return root.after(delay_ms, callback)

            inserted = str(case["inserted"])
            report["stage"] = f"paste_{case['name']}"
            write_report()
            paste_text_with_clipboard_protection(
                clipboard,
                inserted,
                protect_clipboard=True,
                restore_delay_ms=DesktopConfig().clipboard_restore_delay_ms,
                target_hwnd=None,
                schedule_ui=schedule_ui,
            )
            target.event_generate("<<Paste>>")

            deadline = time.time() + 2.0
            while time.time() < deadline:
                root.update()
                time.sleep(0.01)

            report["stage"] = f"read_after_{case['name']}"
            write_report()
            target_text = target.get("1.0", "end").strip()
            before_payloads = before.data_by_format()
            after_payloads = {
                format_id: read_windows_clipboard_format(format_id, hwnd=root.winfo_id())
                for format_id in expected_formats
            }
            format_checks = {
                str(format_id): before_payloads.get(format_id) == after_payloads.get(format_id) == payload
                for format_id, payload in expected_formats.items()
            }
            case_report = {
                "name": case["name"],
                "before_formats": before.format_names(),
                "after_formats_checked": [clipboard_format_name(format_id) for format_id in expected_formats],
                "skipped_before": before.skipped_formats,
                "text_inserted": inserted in target_text,
                "format_restored": all(format_checks.values()),
                "format_checks": format_checks,
            }
            report["cases"].append(case_report)
            report["stage"] = f"case_done_{case['name']}"
            write_report()

        report["ok"] = bool(report["cases"]) and all(
            bool(case["text_inserted"] and case["format_restored"]) for case in report["cases"]
        )
        report["stage"] = "done"
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        if root is not None:
            try:
                if previous_snapshot is not None:
                    report["stage"] = "restore_previous"
                    write_report()
                    Clipboard(root).restore_snapshot(previous_snapshot)
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
        if temp_dir is not None:
            temp_dir.cleanup()
        if report["ok"]:
            report["stage"] = "done"
        write_report()
    return 0 if report["ok"] else 1


def run_startup_script_test(report_path: str | None = None) -> int:
    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-startup-script.json"
    report = {
        "ok": False,
        "test_id": "T13",
        "name": "startup script write/remove smoke without reboot",
        "startup_bat": str(STARTUP_BAT),
        "executable": sys.executable,
        "expected_startup_executable": str(startup_executable_path()),
        "created": False,
        "removed": False,
        "contains_executable": False,
        "contains_hidden_flag": False,
        "error": None,
    }
    original_config_text: str | None = None
    original_config_existed = CONFIG_PATH.exists()
    original_startup_text: str | None = None
    original_startup_existed = STARTUP_BAT.exists()
    try:
        if original_config_existed:
            original_config_text = CONFIG_PATH.read_text(encoding="utf-8")
        if original_startup_existed:
            original_startup_text = STARTUP_BAT.read_text(encoding="utf-8")
        config = reset_config_to_defaults(DesktopConfig())
        config.startup = True
        save_config(config)
        content = STARTUP_BAT.read_text(encoding="utf-8") if STARTUP_BAT.exists() else ""
        report.update(
            {
                "created": STARTUP_BAT.exists(),
                "content": content,
                "contains_executable": str(startup_executable_path()) in content,
                "contains_hidden_flag": "--hidden" in content,
            }
        )
        config.startup = False
        save_config(config)
        report["removed"] = not STARTUP_BAT.exists()
        report["ok"] = bool(
            report["created"]
            and report["contains_executable"]
            and report["contains_hidden_flag"]
            and report["removed"]
        )
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            if original_config_existed and original_config_text is not None:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_PATH.write_text(original_config_text, encoding="utf-8")
            elif not original_config_existed:
                CONFIG_PATH.unlink(missing_ok=True)
            if original_startup_existed and original_startup_text is not None:
                STARTUP_BAT.parent.mkdir(parents=True, exist_ok=True)
                STARTUP_BAT.write_text(original_startup_text, encoding="utf-8")
            elif not original_startup_existed:
                STARTUP_BAT.unlink(missing_ok=True)
        except Exception:
            pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def run_license_network_test(report_path: str | None = None) -> int:
    from doubaoime_asr import activation

    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-license-network.json"
    bad_server_url = "http://127.0.0.1:9"
    cached_token = "cached-token-for-network-smoke"
    report = {
        "ok": False,
        "test_id": "T20",
        "name": "packaged license network failure smoke",
        "config_dir": str(activation.CONFIG_DIR),
        "server_url": bad_server_url,
        "ordinary_build_ok": False,
        "required_build_blocks": False,
        "cached_token_preserved": False,
        "message": "",
        "error": None,
    }
    previous_state: dict[str, object] | None = None
    try:
        previous_state = activation.load_license_state()
        activation.clear_license_state()
        ordinary = activation.verify_license(activation.LicenseConfig(server_url="", require_activation=False))
        required_config = activation.LicenseConfig(server_url=bad_server_url, require_activation=True)
        activation.save_license_state(
            {
                "server_url": bad_server_url,
                "device_id": activation.device_fingerprint(),
                "token": cached_token,
            }
        )
        result = activation.verify_license(required_config)
        state = activation.load_license_state()
        report.update(
            {
                "ordinary_build_ok": ordinary.ok,
                "required_build_blocks": not result.ok,
                "cached_token_preserved": state.get("token") == cached_token,
                "message": result.message,
            }
        )
        report["ok"] = bool(
            report["ordinary_build_ok"]
            and report["required_build_blocks"]
            and report["cached_token_preserved"]
            and "授权校验失败" in result.message
        )
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        try:
            if previous_state:
                activation.save_license_state(previous_state)
            else:
                activation.clear_license_state()
        except Exception:
            pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def run_long_text_test(
    audio_path: str | None,
    report_path: str | None,
    credential_path: str | None,
    run_asr_check: bool,
    min_recognized_chars: int,
    min_keywords: int,
) -> int:
    from doubaoime_asr.long_text_sample import (
        default_credential_path,
        default_output_path,
        generate_long_text_sample,
        run_asr,
        sample_text,
    )

    output = Path(audio_path) if audio_path else default_output_path()
    report = Path(report_path) if report_path else Path("release/test-reports/long-text-asr.json")
    credential = Path(credential_path) if credential_path else default_credential_path()
    license_config = load_license_config()

    result = {
        "ok": False,
        "runner": {
            "executable": sys.executable,
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "license_config": {
            "require_activation": license_config.require_activation,
            "server_url_configured": bool(license_config.server_url),
        },
    }
    try:
        license_result = verify_license(license_config)
        result["license_state"] = {
            "ok": license_result.ok,
            "message": license_result.message,
            "expires_at": license_result.expires_at,
            "code": license_result.code,
        }
        if run_asr_check and not license_result.ok:
            raise RuntimeError(f"授权校验未通过：{license_result.message}")

        info = generate_long_text_sample(output)
        result["sample"] = asdict(info)
        result["source_text"] = sample_text()

        if run_asr_check:
            result["asr"] = asyncio.run(run_asr(output, credential, min_recognized_chars, min_keywords))
            result["ok"] = bool(result["asr"]["passed"])
        else:
            result["ok"] = True
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Doubao ASR desktop helper.")
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--background", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--show-help", action="store_true", help="Open the desktop help window on startup.")
    parser.add_argument("--ui-layout-report", help=argparse.SUPPRESS)
    parser.add_argument("--ui-window-size", help=argparse.SUPPRESS)
    parser.add_argument("--ui-scale-factor", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true", help="Run packaged app diagnostics and exit.")
    parser.add_argument("--self-test-report", help="Write self-test JSON report to this path.")
    parser.add_argument("--tray-self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tray-self-test-report", help=argparse.SUPPRESS)
    parser.add_argument("--float-layout-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--float-layout-report", help=argparse.SUPPRESS)
    parser.add_argument("--float-layout-text", help=argparse.SUPPRESS)
    parser.add_argument("--clipboard-insert-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--clipboard-insert-report", help=argparse.SUPPRESS)
    parser.add_argument("--clipboard-complex-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--clipboard-complex-report", help=argparse.SUPPRESS)
    parser.add_argument("--hold-release-auto-insert-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--hold-release-auto-insert-report", help=argparse.SUPPRESS)
    parser.add_argument("--startup-script-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--startup-script-report", help=argparse.SUPPRESS)
    parser.add_argument("--license-network-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--license-network-report", help=argparse.SUPPRESS)
    parser.add_argument("--long-text-test", action="store_true", help="Generate the long text stress sample and optionally run ASR.")
    parser.add_argument("--long-text-audio", help="Path for the generated long text WAV sample.")
    parser.add_argument("--long-text-report", help="Path for the long text JSON report.")
    parser.add_argument("--long-text-generate-only", action="store_true", help="Skip ASR and only generate the WAV sample.")
    parser.add_argument("--credential-path", help="Credential cache path for ASR tests.")
    parser.add_argument("--min-recognized-chars", type=int, default=220)
    parser.add_argument("--min-keywords", type=int, default=3)
    args = parser.parse_args(argv)
    if args.self_test:
        raise SystemExit(run_self_test(args.self_test_report))
    if args.tray_self_test:
        raise SystemExit(run_tray_self_test(args.tray_self_test_report))
    if args.float_layout_test:
        raise SystemExit(run_float_layout_test(args.float_layout_report, args.float_layout_text))
    if args.clipboard_insert_test:
        raise SystemExit(run_clipboard_insert_test(args.clipboard_insert_report))
    if args.clipboard_complex_test:
        raise SystemExit(run_clipboard_complex_test(args.clipboard_complex_report))
    if args.hold_release_auto_insert_test:
        raise SystemExit(run_hold_release_auto_insert_test(args.hold_release_auto_insert_report))
    if args.startup_script_test:
        raise SystemExit(run_startup_script_test(args.startup_script_report))
    if args.license_network_test:
        raise SystemExit(run_license_network_test(args.license_network_report))
    if args.long_text_test:
        raise SystemExit(
            run_long_text_test(
                args.long_text_audio,
                args.long_text_report,
                args.credential_path,
                not args.long_text_generate_only,
                args.min_recognized_chars,
                args.min_keywords,
            )
        )
    guard = SingleInstanceGuard()
    if not guard.acquire():
        try:
            guard.signal_existing_instance()
        finally:
            guard.release()
        raise SystemExit(0)
    try:
        app = DesktopApp(
            hidden=args.hidden,
            show_help=args.show_help,
            background=args.background,
            ui_layout_report=args.ui_layout_report,
            ui_window_size=args.ui_window_size,
            ui_scale_factor=args.ui_scale_factor,
        )
        app.run()
    finally:
        guard.release()


if __name__ == "__main__":
    main()
