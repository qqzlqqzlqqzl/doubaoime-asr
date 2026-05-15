from __future__ import annotations

import importlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
import requests

from tools.license_server import LicenseServer


@contextmanager
def run_license_server(tmp_path: Path, codes: dict[str, Any]) -> Iterator[tuple[str, Path]]:
    codes_path = tmp_path / "codes.json"
    codes_path.write_text(json.dumps({"codes": codes}, ensure_ascii=False), encoding="utf-8")
    server = LicenseServer(("127.0.0.1", 0), codes_path, "test-secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", codes_path
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def sample_codes(max_devices: int = 1, disabled: bool = False, expires_at: str = "2027-12-31T23:59:59Z") -> dict[str, Any]:
    return {
        "TEST-2026-0001": {
            "max_devices": max_devices,
            "expires_at": expires_at,
            "disabled": disabled,
            "devices": {},
        }
    }


def load_activation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, require: str | None, server_url: str | None):
    monkeypatch.setenv("DOUBAO_ASR_CONFIG_DIR", str(tmp_path / "appdata"))
    if require is None:
        monkeypatch.delenv("DOUBAO_ASR_REQUIRE_ACTIVATION", raising=False)
    else:
        monkeypatch.setenv("DOUBAO_ASR_REQUIRE_ACTIVATION", require)
    if server_url is None:
        monkeypatch.delenv("DOUBAO_ASR_LICENSE_URL", raising=False)
    else:
        monkeypatch.setenv("DOUBAO_ASR_LICENSE_URL", server_url)

    import doubaoime_asr.activation as activation

    return importlib.reload(activation)


def test_default_license_config_does_not_require_activation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    activation = load_activation(monkeypatch, tmp_path, require=None, server_url=None)

    config = activation.load_license_config()
    result = activation.verify_license(config)

    assert config.require_activation is False
    assert config.server_url == ""
    assert result.ok is True


def test_env_license_config_requires_server_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    activation = load_activation(monkeypatch, tmp_path, require="yes", server_url="https://license.example.com/")

    config = activation.load_license_config()

    assert config.require_activation is True
    assert config.server_url == "https://license.example.com"


def test_missing_server_blocks_required_activation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    activation = load_activation(monkeypatch, tmp_path, require="1", server_url="")

    result = activation.verify_license(activation.load_license_config())

    assert result.ok is False
    assert "未配置授权服务器" in result.message


def test_activation_success_persists_and_verifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes()) as (server_url, _codes_path):
        activation = load_activation(monkeypatch, tmp_path, require="1", server_url=server_url)
        config = activation.load_license_config()

        before = activation.verify_license(config)
        activated = activation.activate_license(config, "test-2026-0001")
        verified = activation.verify_license(config)
        state = activation.load_license_state()

    assert before.ok is False
    assert "尚未激活" in before.message
    assert activated.ok is True
    assert verified.ok is True
    assert state["server_url"] == server_url
    assert state["device_id"] == activation.device_fingerprint()
    assert state["token"]


def test_invalid_activation_code_does_not_save_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes()) as (server_url, _codes_path):
        activation = load_activation(monkeypatch, tmp_path, require="1", server_url=server_url)
        result = activation.activate_license(activation.load_license_config(), "NOPE-0000")

    assert result.ok is False
    assert result.code == "UNKNOWN_CODE"
    assert activation.load_license_state() == {}


def test_server_enforces_device_limit(tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes(max_devices=1)) as (server_url, _codes_path):
        first = requests.post(
            f"{server_url}/api/activate",
            json={"activation_code": "TEST-2026-0001", "device_id": "device-a", "app_version": "0.2.0"},
            timeout=5,
        )
        second = requests.post(
            f"{server_url}/api/activate",
            json={"activation_code": "TEST-2026-0001", "device_id": "device-b", "app_version": "0.2.0"},
            timeout=5,
        )

    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert second.status_code == 403
    assert second.json()["code"] == "DEVICE_LIMIT"


def test_disabled_code_is_rejected(tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes(disabled=True)) as (server_url, _codes_path):
        response = requests.post(
            f"{server_url}/api/activate",
            json={"activation_code": "TEST-2026-0001", "device_id": "device-a", "app_version": "0.2.0"},
            timeout=5,
        )

    assert response.status_code == 403
    assert response.json()["code"] == "DISABLED_CODE"


def test_expired_code_is_rejected(tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes(expires_at="2020-01-01T00:00:00Z")) as (server_url, _codes_path):
        response = requests.post(
            f"{server_url}/api/activate",
            json={"activation_code": "TEST-2026-0001", "device_id": "device-a", "app_version": "0.2.0"},
            timeout=5,
        )

    assert response.status_code == 403
    assert response.json()["code"] == "EXPIRED_CODE"


def test_copied_license_is_cleared_on_device_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes()) as (server_url, _codes_path):
        activation = load_activation(monkeypatch, tmp_path, require="1", server_url=server_url)
        config = activation.load_license_config()
        assert activation.activate_license(config, "TEST-2026-0001").ok
        state = activation.load_license_state()
        state["device_id"] = "copied-from-another-machine"
        activation.save_license_state(state)

        result = activation.verify_license(config)

    assert result.ok is False
    assert "不属于这台电脑" in result.message
    assert activation.load_license_state() == {}


def test_license_is_cleared_when_server_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes()) as (server_url, _codes_path):
        activation = load_activation(monkeypatch, tmp_path, require="1", server_url=server_url)
        assert activation.activate_license(activation.load_license_config(), "TEST-2026-0001").ok

        changed = load_activation(monkeypatch, tmp_path, require="1", server_url=f"{server_url}/changed")
        result = changed.verify_license(changed.load_license_config())

    assert result.ok is False
    assert "授权服务器已变更" in result.message
    assert changed.load_license_state() == {}


def test_bad_token_is_rejected_and_clears_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with run_license_server(tmp_path, sample_codes()) as (server_url, _codes_path):
        activation = load_activation(monkeypatch, tmp_path, require="1", server_url=server_url)
        activation.save_license_state(
            {
                "server_url": server_url,
                "device_id": activation.device_fingerprint(),
                "token": "not-a-valid-token",
            }
        )

        result = activation.verify_license(activation.load_license_config())

    assert result.ok is False
    assert result.code == "BAD_TOKEN"
    assert activation.load_license_state() == {}


def test_network_failure_does_not_clear_existing_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    activation = load_activation(monkeypatch, tmp_path, require="1", server_url="http://127.0.0.1:9")
    activation.save_license_state(
        {
            "server_url": "http://127.0.0.1:9",
            "device_id": activation.device_fingerprint(),
            "token": "cached-token",
        }
    )

    result = activation.verify_license(activation.load_license_config())

    assert result.ok is False
    assert "授权校验失败" in result.message
    assert activation.load_license_state()["token"] == "cached-token"
