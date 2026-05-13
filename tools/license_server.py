from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _utc_now() -> int:
    return int(time.time())


def _parse_expires_at(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T23:59:59+00:00"
    elif text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _sign_token(payload: dict[str, Any], secret: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return f"{_b64encode(body)}.{_b64encode(signature)}"


def _verify_token(token: str, secret: str) -> dict[str, Any]:
    try:
        body64, sig64 = token.split(".", 1)
        body = _b64decode(body64)
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        actual = _b64decode(sig64)
    except Exception as exc:
        raise ValueError("token 格式错误") from exc
    if not hmac.compare_digest(expected, actual):
        raise ValueError("token 签名无效")
    payload = json.loads(body.decode("utf-8"))
    exp = payload.get("exp")
    if exp is not None and int(exp) < _utc_now():
        raise ValueError("授权已过期")
    return payload


class LicenseServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], codes_path: Path, secret: str) -> None:
        super().__init__(address, LicenseHandler)
        self.codes_path = codes_path
        self.secret = secret
        self.lock = threading.RLock()
        self.data = self._load_codes()

    def _load_codes(self) -> dict[str, Any]:
        if not self.codes_path.exists():
            raise FileNotFoundError(f"找不到激活码文件：{self.codes_path}")
        data = json.loads(self.codes_path.read_text(encoding="utf-8"))
        data.setdefault("codes", {})
        return data

    def save_codes(self) -> None:
        self.codes_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


class LicenseHandler(BaseHTTPRequestHandler):
    server: LicenseServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            _json_response(self, 200, {"ok": True, "message": "license server is running"})
            return
        _json_response(self, 404, {"ok": False, "message": "not found"})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            _json_response(self, 400, {"ok": False, "message": "请求 JSON 无效", "code": "BAD_JSON"})
            return

        if self.path.rstrip("/") == "/api/activate":
            status, response = self._activate(payload)
        elif self.path.rstrip("/") == "/api/verify":
            status, response = self._verify(payload)
        else:
            status, response = 404, {"ok": False, "message": "not found"}
        _json_response(self, status, response)

    def _code_entry(self, activation_code: str) -> tuple[str, dict[str, Any] | None]:
        code = activation_code.strip().upper()
        return code, self.server.data["codes"].get(code)

    def _entry_error(self, entry: dict[str, Any] | None) -> tuple[int, dict[str, Any]] | None:
        if entry is None:
            return 404, {"ok": False, "message": "激活码不存在。", "code": "UNKNOWN_CODE"}
        if entry.get("disabled"):
            return 403, {"ok": False, "message": "激活码已停用。", "code": "DISABLED_CODE"}
        expires_at = entry.get("expires_at")
        expires_ts = _parse_expires_at(expires_at)
        if expires_ts is not None and expires_ts < _utc_now():
            return 403, {"ok": False, "message": "激活码已过期。", "code": "EXPIRED_CODE"}
        return None

    def _make_token(self, code: str, device_id: str, expires_at: str | None, app_version: str | None) -> str:
        expires_ts = _parse_expires_at(expires_at)
        payload = {
            "code": code,
            "device_id": device_id,
            "iat": _utc_now(),
            "exp": expires_ts,
            "app_version": app_version,
        }
        return _sign_token(payload, self.server.secret)

    def _activate(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        activation_code = str(payload.get("activation_code", "")).strip()
        device_id = str(payload.get("device_id", "")).strip()
        app_version = str(payload.get("app_version", "")).strip()
        if not activation_code or not device_id:
            return 400, {"ok": False, "message": "缺少激活码或设备码。", "code": "BAD_REQUEST"}

        with self.server.lock:
            code, entry = self._code_entry(activation_code)
            error = self._entry_error(entry)
            if error:
                return error

            devices = entry.setdefault("devices", {})
            max_devices = int(entry.get("max_devices", 1))
            if device_id not in devices and len(devices) >= max_devices:
                return 403, {"ok": False, "message": "这个激活码可绑定设备数已满。", "code": "DEVICE_LIMIT"}

            devices.setdefault(
                device_id,
                {
                    "activated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "app_version": app_version,
                },
            )
            devices[device_id]["last_activated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self.server.save_codes()

            expires_at = entry.get("expires_at")
            token = self._make_token(code, device_id, expires_at, app_version)
        return 200, {
            "ok": True,
            "message": "激活成功。",
            "token": token,
            "expires_at": expires_at,
        }

    def _verify(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        token = str(payload.get("token", "")).strip()
        device_id = str(payload.get("device_id", "")).strip()
        if not token or not device_id:
            return 400, {"ok": False, "message": "缺少 token 或设备码。", "code": "BAD_REQUEST"}

        try:
            token_payload = _verify_token(token, self.server.secret)
        except ValueError as exc:
            return 403, {"ok": False, "message": str(exc), "code": "BAD_TOKEN"}

        if token_payload.get("device_id") != device_id:
            return 403, {"ok": False, "message": "授权不属于这台电脑。", "code": "DEVICE_MISMATCH"}

        with self.server.lock:
            code, entry = self._code_entry(str(token_payload.get("code", "")))
            error = self._entry_error(entry)
            if error:
                return error

            if device_id not in entry.setdefault("devices", {}):
                return 403, {"ok": False, "message": "此设备未绑定该激活码。", "code": "UNBOUND_DEVICE"}

            expires_at = entry.get("expires_at")
            renewed_token = self._make_token(code, device_id, expires_at, str(payload.get("app_version", "")))
        return 200, {
            "ok": True,
            "message": "授权有效。",
            "token": renewed_token,
            "expires_at": expires_at,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal activation-code server for Doubao ASR Helper.")
    parser.add_argument("--codes", type=Path, default=Path("tools/license-codes.sample.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--secret", default=os.environ.get("DOUBAO_ASR_LICENSE_SECRET", "change-me-dev-secret"))
    args = parser.parse_args()

    server = LicenseServer((args.host, args.port), args.codes, args.secret)
    print(f"License server listening on http://{args.host}:{args.port}")
    print(f"Codes file: {args.codes}")
    if args.secret == "change-me-dev-secret":
        print("WARNING: using the demo secret. Set DOUBAO_ASR_LICENSE_SECRET in production.")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
