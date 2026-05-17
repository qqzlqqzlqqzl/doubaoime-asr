from __future__ import annotations

from pathlib import Path

from doubaoime_asr.asr_bridge import BridgeState


class FakeSession:
    session_id = 42

    def __init__(self) -> None:
        self.cancelled = False
        self.waited = False

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, timeout: float) -> bool:
        self.waited = timeout > 0
        return True


def test_bridge_reset_clears_stale_session(tmp_path: Path) -> None:
    bridge = BridgeState(credential_path=tmp_path / "credentials.json")
    stale = FakeSession()
    bridge._session = stale

    result = bridge.reset()

    assert result.ok is True
    assert result.state == "idle"
    assert result.session_id == 42
    assert stale.cancelled is True
    assert stale.waited is True
    assert bridge.status()["state"] == "idle"
