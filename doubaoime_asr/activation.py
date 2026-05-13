from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


APP_NAME = "DoubaoASRHelper"
APP_VERSION = "0.2.0"
DEFAULT_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / APP_NAME
CONFIG_DIR = Path(os.environ.get("DOUBAO_ASR_CONFIG_DIR", DEFAULT_CONFIG_DIR))
LICENSE_STATE_PATH = CONFIG_DIR / "license.json"


@dataclass
class LicenseConfig:
    server_url: str = ""
    require_activation: bool = False


@dataclass
class LicenseResult:
    ok: bool
    message: str
    expires_at: str | None = None
    code: str | None = None


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resource_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "doubaoime_asr" / "license-config.json"
    return Path(__file__).with_name("license-config.json")


def load_license_config() -> LicenseConfig:
    data: dict[str, Any] = {}
    path = _resource_config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

    server_url = os.environ.get("DOUBAO_ASR_LICENSE_URL", data.get("server_url", "")).strip()
    if "DOUBAO_ASR_REQUIRE_ACTIVATION" in os.environ:
        require_activation = _truthy(os.environ.get("DOUBAO_ASR_REQUIRE_ACTIVATION"))
    else:
        raw_required = data.get("require_activation", False)
        require_activation = _truthy(raw_required) if isinstance(raw_required, str) else bool(raw_required)

    return LicenseConfig(server_url=server_url.rstrip("/"), require_activation=require_activation)


def _windows_machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def device_fingerprint() -> str:
    machine_guid = _windows_machine_guid()
    raw = "|".join(
        [
            "doubao-asr-helper-device-v1",
            machine_guid,
            platform.node(),
            socket.gethostname(),
            platform.system(),
            platform.machine(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _post_json(server_url: str, path: str, payload: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    if not server_url:
        raise RuntimeError("授权服务器地址为空。")
    url = f"{server_url.rstrip('/')}/{path.lstrip('/')}"
    response = requests.post(url, json=payload, timeout=timeout)
    try:
        data = response.json()
    except ValueError:
        data = {"ok": False, "message": response.text[:300]}
    if response.status_code >= 400:
        raise RuntimeError(data.get("message") or f"HTTP {response.status_code}")
    return data


def load_license_state() -> dict[str, Any]:
    if not LICENSE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(LICENSE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_license_state(state: dict[str, Any]) -> None:
    LICENSE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_license_state() -> None:
    LICENSE_STATE_PATH.unlink(missing_ok=True)


def activate_license(config: LicenseConfig, activation_code: str) -> LicenseResult:
    code = activation_code.strip()
    if not code:
        return LicenseResult(False, "请输入激活码。")
    if config.require_activation and not config.server_url:
        return LicenseResult(False, "此版本要求激活，但未配置授权服务器地址。")

    device_id = device_fingerprint()
    try:
        data = _post_json(
            config.server_url,
            "/api/activate",
            {
                "activation_code": code,
                "device_id": device_id,
                "app_version": APP_VERSION,
            },
        )
    except Exception as exc:
        return LicenseResult(False, f"激活失败：{exc}")

    if not data.get("ok"):
        return LicenseResult(False, data.get("message", "激活失败。"), code=data.get("code"))

    token = data.get("token")
    if not token:
        return LicenseResult(False, "授权服务器没有返回 token。")

    state = {
        "server_url": config.server_url,
        "device_id": device_id,
        "token": token,
        "expires_at": data.get("expires_at"),
        "activated_at": int(time.time()),
    }
    save_license_state(state)
    return LicenseResult(True, data.get("message", "激活成功。"), expires_at=data.get("expires_at"))


def verify_license(config: LicenseConfig) -> LicenseResult:
    if not config.require_activation:
        return LicenseResult(True, "当前构建未启用强制激活。")
    if not config.server_url:
        return LicenseResult(False, "此版本要求激活，但未配置授权服务器地址。")

    state = load_license_state()
    token = state.get("token")
    device_id = device_fingerprint()
    if not token:
        return LicenseResult(False, "尚未激活。")
    if state.get("device_id") != device_id:
        clear_license_state()
        return LicenseResult(False, "本地授权不属于这台电脑，请重新激活。")
    if state.get("server_url") != config.server_url:
        clear_license_state()
        return LicenseResult(False, "授权服务器已变更，请重新激活。")

    try:
        data = _post_json(
            config.server_url,
            "/api/verify",
            {
                "token": token,
                "device_id": device_id,
                "app_version": APP_VERSION,
            },
        )
    except Exception as exc:
        return LicenseResult(False, f"授权校验失败：{exc}")

    if not data.get("ok"):
        clear_license_state()
        return LicenseResult(False, data.get("message", "授权无效。"), code=data.get("code"))

    if data.get("token"):
        state["token"] = data["token"]
    state["expires_at"] = data.get("expires_at", state.get("expires_at"))
    state["last_verified_at"] = int(time.time())
    save_license_state(state)
    return LicenseResult(True, data.get("message", "授权有效。"), expires_at=state.get("expires_at"))
