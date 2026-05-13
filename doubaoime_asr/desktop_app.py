from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import sounddevice as sd
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pynput import keyboard, mouse

if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = str(bundle_dir) + os.pathsep + os.environ.get("PATH", "")

from doubaoime_asr import ASRConfig, ResponseType, transcribe_realtime
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


@dataclass
class DesktopConfig:
    hold_key: str = "rctrl"
    toggle_key: str = "xbutton1"
    hold_send_key: str = "lctrl+lwin"
    cancel_key: str = "z"
    doubao_hotkey: str = "ctrl+d"
    insert_delay_ms: int = 300
    auto_send_delay_ms: int = 50
    protect_clipboard: bool = True
    startup: bool = False
    credential_path: str = str(DEFAULT_CREDENTIAL_PATH)


def resolve_user_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = APP_CONFIG_DIR / path
    return path


def normalize_config(config: DesktopConfig) -> DesktopConfig:
    config.credential_path = str(resolve_user_path(config.credential_path))
    return config


def hotkey_conflict_from_values(values: dict[str, str]) -> str | None:
    seen: dict[frozenset[str], str] = {}
    for field, label in HOTKEY_LABELS.items():
        value = values[field].strip()
        parsed = parse_hotkey(value)
        if not parsed:
            return f"{label} 不能为空。"
        if parsed in seen:
            return f"{label} 与 {seen[parsed]} 使用了同一个快捷键：{value}"
        seen[parsed] = label
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


def sync_startup(enabled: bool) -> None:
    if enabled:
        exe = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "doubaoime-asr-desktop.exe"
        STARTUP_BAT.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_BAT.write_text(f'@echo off\r\nstart "" "{exe}" --hidden\r\n', encoding="utf-8")
    else:
        STARTUP_BAT.unlink(missing_ok=True)


ALIASES = {
    "right ctrl": "rctrl",
    "右ctrl": "rctrl",
    "rctrl": "rctrl",
    "left ctrl": "lctrl",
    "左ctrl": "lctrl",
    "lctrl": "lctrl",
    "ctrl": "ctrl",
    "control": "ctrl",
    "right win": "rwin",
    "右win": "rwin",
    "rwin": "rwin",
    "left win": "lwin",
    "左win": "lwin",
    "lwin": "lwin",
    "win": "win",
    "cmd": "win",
    "alt": "alt",
    "shift": "shift",
    "鼠标侧键1": "xbutton1",
    "mouse x1": "xbutton1",
    "x1": "xbutton1",
    "xbutton1": "xbutton1",
    "鼠标侧键2": "xbutton2",
    "mouse x2": "xbutton2",
    "x2": "xbutton2",
    "xbutton2": "xbutton2",
}


def parse_hotkey(value: str) -> frozenset[str]:
    parts = [part.strip().lower() for part in value.replace("＋", "+").split("+") if part.strip()]
    return frozenset(ALIASES.get(part, part) for part in parts)


def format_hotkey(keys: Iterable[str]) -> str:
    order = ["lctrl", "rctrl", "ctrl", "lalt", "ralt", "alt", "lshift", "rshift", "shift", "lwin", "rwin", "win"]
    unique = list(dict.fromkeys(keys))
    unique.sort(key=lambda item: order.index(item) if item in order else 99)
    return "+".join(unique)


def key_name(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    key_map = {
        keyboard.Key.ctrl_l: "lctrl",
        keyboard.Key.ctrl_r: "rctrl",
        keyboard.Key.cmd_l: "lwin",
        keyboard.Key.cmd_r: "rwin",
        keyboard.Key.alt_l: "lalt",
        keyboard.Key.alt_r: "ralt",
        keyboard.Key.shift_l: "lshift",
        keyboard.Key.shift_r: "rshift",
        keyboard.Key.esc: "esc",
        keyboard.Key.enter: "enter",
        keyboard.Key.space: "space",
        keyboard.Key.tab: "tab",
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


class DesktopApp:
    def __init__(self, hidden: bool = False, show_help: bool = False) -> None:
        self.root = tk.Tk()
        self.root.title("豆包 ASR 助手")
        self.root.geometry("720x520")
        self.root.minsize(680, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.config = load_config()
        self.clipboard = Clipboard(self.root)
        self.active_keys: set[str] = set()
        self.recording_mode: str | None = None
        self.cancelled = False
        self.target_hwnd: int | None = None
        self.audio_queue: queue.Queue[bytes | None] | None = None
        self.audio_stream: sd.InputStream | None = None
        self.asr_thread: threading.Thread | None = None
        self.transcript = TranscriptAccumulator()
        self.final_text = ""
        self.entries: dict[str, tk.Entry] = {}
        self.vars: dict[str, tk.BooleanVar] = {}
        self.help_win: tk.Toplevel | None = None
        self.recording_field: str | None = None
        self.status_var = tk.StringVar(value="已就绪")
        self.transcript_var = tk.StringVar(value="")
        self._build_settings_ui()
        self._build_float_window()
        self._start_listeners()
        if hidden:
            self.root.withdraw()
        if show_help:
            self.root.after(100, self.show_help)

    def run(self) -> None:
        self.root.mainloop()

    def _build_settings_ui(self) -> None:
        outer = tk.Frame(self.root, padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="豆包 ASR 助手", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        tk.Label(outer, textvariable=self.status_var, fg="#5d6b82").pack(anchor="w", pady=(4, 16))

        table = tk.Frame(outer)
        table.pack(fill="x")
        fields = [
            ("hold_key", "按着说触发键", "按住说话，松开后识别并插入"),
            ("toggle_key", "自由说触发键", "按一次开始，再按一次结束"),
            ("hold_send_key", "按着说+自动发送触发键", "松开后插入并发送 Enter"),
            ("cancel_key", "取消键", "自动发送模式下取消本次输入"),
            ("doubao_hotkey", "豆包快捷键", "保留兼容配置，当前使用内置 ASR"),
            ("insert_delay_ms", "插入延迟", "松开后等待识别完成的时间，毫秒"),
            ("auto_send_delay_ms", "自动发送延迟", "粘贴后等待发送的时间，毫秒"),
            ("credential_path", "凭据文件", "设备注册和 token 缓存文件"),
        ]
        for row, (key, label, desc) in enumerate(fields):
            tk.Label(table, text=label, width=18, anchor="w").grid(row=row, column=0, sticky="w", pady=6)
            tk.Label(table, text=desc, anchor="w", fg="#5d6b82").grid(row=row, column=1, sticky="ew", padx=10)
            value_frame = tk.Frame(table)
            value_frame.grid(row=row, column=2, sticky="ew", pady=6)
            entry = tk.Entry(value_frame)
            entry.insert(0, str(getattr(self.config, key)))
            entry.pack(side="left", fill="x", expand=True)
            self.entries[key] = entry
            if key.endswith("_key"):
                tk.Button(value_frame, text="录制", command=lambda field=key: self.start_key_record(field), width=6).pack(side="left", padx=(6, 0))
            elif key == "credential_path":
                tk.Button(value_frame, text="选择", command=self.select_credential_file, width=6).pack(side="left", padx=(6, 0))
        table.columnconfigure(1, weight=1)
        table.columnconfigure(2, weight=0, minsize=180)

        checks = tk.Frame(outer)
        checks.pack(fill="x", pady=14)
        self.vars["protect_clipboard"] = tk.BooleanVar(value=self.config.protect_clipboard)
        self.vars["startup"] = tk.BooleanVar(value=self.config.startup)
        tk.Checkbutton(checks, text="剪贴板保护", variable=self.vars["protect_clipboard"]).pack(side="left")
        tk.Checkbutton(checks, text="开机自启动", variable=self.vars["startup"]).pack(side="left", padx=18)

        buttons = tk.Frame(outer)
        buttons.pack(fill="x", pady=(4, 16))
        tk.Button(buttons, text="保存配置", command=self.save_from_ui, width=14).pack(side="left")
        tk.Button(buttons, text="显示悬浮窗", command=lambda: self.show_float("")).pack(side="left", padx=10)
        tk.Button(buttons, text="使用说明", command=self.show_help, width=12).pack(side="left")
        tk.Button(buttons, text="打开配置目录", command=self.open_config_dir, width=14).pack(side="left", padx=10)
        tk.Button(buttons, text="隐藏窗口", command=self.root.withdraw, width=14).pack(side="right")

        help_text = (
            "默认热键：rctrl / xbutton1 / lctrl+lwin / z。"
            "录音结束后会把识别文字粘贴到开始录音前的窗口。"
        )
        tk.Label(outer, text=help_text, fg="#5d6b82", wraplength=660, justify="left").pack(anchor="w")

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

    def _build_float_window(self) -> None:
        self.float_win = tk.Toplevel(self.root)
        self.float_win.title("豆包 ASR")
        self.float_win.geometry("680x170+360+360")
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
        tk.Button(actions, text="清空", command=self.clear_float).pack(side="left")
        tk.Button(actions, text="复制", command=self.copy_float).pack(side="left", padx=8)
        tk.Button(actions, text="插入 ↵", command=lambda: self.insert_text(self.get_float_text(), auto_send=False)).pack(side="right")

    def save_from_ui(self) -> None:
        conflict = self.find_hotkey_conflict()
        if conflict:
            messagebox.showwarning("快捷键冲突", conflict)
            self.status_var.set("快捷键冲突，请调整后再保存")
            return
        for key, entry in self.entries.items():
            value: str | int = entry.get().strip()
            if key.endswith("_ms"):
                try:
                    value = int(value)
                except ValueError:
                    messagebox.showwarning("配置错误", f"{key} 必须是数字。")
                    self.status_var.set("配置错误，请检查数字项")
                    return
            elif key == "credential_path":
                value = str(resolve_user_path(value))
            setattr(self.config, key, value)
        self.config.protect_clipboard = self.vars["protect_clipboard"].get()
        self.config.startup = self.vars["startup"].get()
        save_config(self.config)
        self.status_var.set("配置已保存")

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
            self.status_var.set(f"正在录制：{format_hotkey(self.active_keys)}")
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
        self.active_keys.discard(name)
        self._handle_active_release()

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
            self.active_keys.discard(name)
            self._handle_active_release()

    def _finish_key_record(self, value: str) -> None:
        field = self.recording_field
        self.recording_field = None
        if field and value:
            for other_field in HOTKEY_LABELS:
                if other_field != field and parse_hotkey(self.entries[other_field].get()) == parse_hotkey(value):
                    messagebox.showwarning(
                        "快捷键冲突",
                        f"这个快捷键已被「{HOTKEY_LABELS.get(other_field, other_field)}」使用，请换一个。",
                    )
                    self.status_var.set("快捷键冲突，请重新录制")
                    return
            self.entries[field].delete(0, "end")
            self.entries[field].insert(0, value)
            self.status_var.set(f"已录制：{value}，点击保存配置生效")

    def _handle_active_press(self, name: str) -> None:
        if self.recording_mode and active_matches(self.active_keys, parse_hotkey(self.config.cancel_key)):
            self.cancelled = True
            self.stop_recording()
            return
        if self.recording_mode == "toggle" and active_matches(self.active_keys, parse_hotkey(self.config.toggle_key)):
            self.stop_recording()
            return
        if self.recording_mode:
            return
        if active_matches(self.active_keys, parse_hotkey(self.config.hold_send_key)):
            self.start_recording("hold_send")
        elif active_matches(self.active_keys, parse_hotkey(self.config.hold_key)):
            self.start_recording("hold")
        elif name in parse_hotkey(self.config.toggle_key) and active_matches(self.active_keys, parse_hotkey(self.config.toggle_key)):
            self.start_recording("toggle")

    def _handle_active_release(self) -> None:
        if self.recording_mode == "hold" and not active_matches(self.active_keys, parse_hotkey(self.config.hold_key)):
            self.stop_recording()
        elif self.recording_mode == "hold_send" and not active_matches(self.active_keys, parse_hotkey(self.config.hold_send_key)):
            self.stop_recording()

    def start_recording(self, mode: str) -> None:
        self.target_hwnd = get_foreground_window()
        self.recording_mode = mode
        self.cancelled = False
        self.final_text = ""
        self.transcript = TranscriptAccumulator()
        self.audio_queue = queue.Queue()
        self.root.after(0, lambda: self.show_float("正在听..."))
        self.audio_stream = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=320,
            callback=self._audio_callback,
        )
        self.audio_stream.start()
        self.asr_thread = threading.Thread(target=self._run_asr_thread, daemon=True)
        self.asr_thread.start()
        self.status_var.set("正在录音")

    def stop_recording(self) -> None:
        if not self.recording_mode:
            return
        mode = self.recording_mode
        self.recording_mode = None
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
        if self.audio_queue:
            self.audio_queue.put(None)
        self.status_var.set("正在识别")
        if self.cancelled:
            self.root.after(0, lambda: self.show_float("已取消"))
        self.pending_mode = mode

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            print(status)
        if self.audio_queue is not None:
            self.audio_queue.put(bytes(indata))

    def _run_asr_thread(self) -> None:
        async def source() -> Iterable[bytes]:
            while True:
                chunk = await asyncio.to_thread(self.audio_queue.get)
                if chunk is None:
                    break
                yield chunk

        async def runner() -> None:
            config = ASRConfig(credential_path=str(resolve_user_path(self.config.credential_path)))
            async for response in transcribe_realtime(source(), config=config):
                if response.type in {ResponseType.INTERIM_RESULT, ResponseType.FINAL_RESULT} and response.text:
                    text = self._update_asr_text(response)
                    self.root.after(0, lambda value=text: self.show_float(value))
                if response.type == ResponseType.ERROR:
                    self.root.after(0, lambda msg=response.error_msg: self.show_float(f"错误：{msg}"))

        try:
            asyncio.run(runner())
            self.root.after(0, self._finish_insert)
        except Exception as exc:
            self.root.after(0, lambda: self.show_float(f"错误：{exc}"))

    def _update_asr_text(self, response) -> str:
        if response.text:
            self.final_text = self.transcript.update(
                response.text,
                is_final=response.type == ResponseType.FINAL_RESULT,
            )
        return self.final_text

    def _finish_insert(self) -> None:
        self.status_var.set("识别完成")
        if self.cancelled or not self.final_text:
            return
        auto_send = getattr(self, "pending_mode", "") == "hold_send"
        self.root.after(self.config.insert_delay_ms, lambda: self.insert_text(self.final_text, auto_send=auto_send))

    def show_float(self, text: str) -> None:
        self.float_text.delete("1.0", "end")
        self.float_text.insert("1.0", text)
        self.float_win.deiconify()

    def get_float_text(self) -> str:
        return self.float_text.get("1.0", "end").strip()

    def clear_float(self) -> None:
        self.float_text.delete("1.0", "end")

    def copy_float(self) -> None:
        self.clipboard.set_text(self.get_float_text())
        self.status_var.set("已复制")

    def insert_text(self, text: str, auto_send: bool) -> None:
        if not text:
            return
        original = self.clipboard.get_text() if self.config.protect_clipboard else ""
        self.clipboard.set_text(text)
        if self.target_hwnd:
            set_foreground_window(self.target_hwnd)
            time.sleep(0.05)
        send_ctrl_v()
        if auto_send:
            self.root.after(self.config.auto_send_delay_ms, send_enter)
        if self.config.protect_clipboard:
            self.root.after(500, lambda: self.clipboard.set_text(original))


def get_foreground_window() -> int:
    try:
        import ctypes

        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return 0


def set_foreground_window(hwnd: int) -> None:
    try:
        import ctypes

        ctypes.windll.user32.SetForegroundWindow(hwnd)
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
    report["credential_path"] = str(credential_path)

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
        return "configured hotkeys are valid"

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

    def help_text_check() -> str:
        required = ["豆包 ASR 助手使用说明", "默认快捷键", "常见问题", "卸载"]
        missing = [item for item in required if item not in HELP_TEXT]
        if missing:
            raise RuntimeError(f"Help text is missing required section(s): {missing}")
        return f"embedded help has {len(HELP_TEXT)} characters"

    check("config_dir", config_dir_check)
    check("credential_path", credential_path_check)
    check("hotkeys", hotkey_check)
    check("opus_encoder", opus_check)
    check("audio_devices", sounddevice_check)
    check("input_control", input_control_check)
    check("help_text", help_text_check)

    destination = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "DoubaoASRHelper-self-test.json"
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

    result = {
        "ok": False,
        "runner": {
            "executable": sys.executable,
            "frozen": bool(getattr(sys, "frozen", False)),
        },
    }
    try:
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
    parser.add_argument("--show-help", action="store_true", help="Open the desktop help window on startup.")
    parser.add_argument("--self-test", action="store_true", help="Run packaged app diagnostics and exit.")
    parser.add_argument("--self-test-report", help="Write self-test JSON report to this path.")
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
    app = DesktopApp(hidden=args.hidden, show_help=args.show_help)
    app.run()


if __name__ == "__main__":
    main()
