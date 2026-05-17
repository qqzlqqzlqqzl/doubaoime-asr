from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bridge_warmup_marks_launching_before_run_to_avoid_duplicate_backend() -> None:
    source = _read("ahk_client/src/bridge.ahk")

    assert "static LaunchInProgress := false" in source
    assert 'this.LaunchBridge("bridge_warmup_launch", "bridge_warmup_pid")' in source
    assert 'this.LaunchBridge("bridge_launch", "bridge_launch_pid")' in source
    assert source.index("this.LaunchInProgress := true") < source.index("Run(")
    assert "if this.WarmupStarted || this.LaunchInProgress" in source


def test_bridge_recovers_stale_already_recording_session_before_retrying_start() -> None:
    source = _read("ahk_client/src/bridge.ahk")

    assert 'result.error = "already_recording"' in source
    assert "bridge_start_already_recording_recover" in source
    recovery = source[source.index("static RecoverAlreadyRecording") :]
    assert recovery.index("this.Cancel()") < recovery.index('this.Request("POST", "/start"')
    assert "bridge_start_recovered" in recovery


def test_voice_release_during_bridge_start_is_queued_until_start_returns() -> None:
    source = _read("ahk_client/src/main.ahk")

    assert "static StartInProgress := false" in source
    assert "static ReleasePending := false" in source
    assert "static CancelPending := false" in source
    assert source.index("result := BridgeClient.Start(mode)") < source.index("if this.ReleasePending")

    hold_end = source[source.index("static OnHoldEnd()") : source.index("static OnFreeToggle")]
    assert "if this.StartInProgress" in hold_end
    assert "this.ReleasePending := true" in hold_end
    assert "voice_release_queued" in hold_end

    auto_send_end = source[source.index("static OnAutoSendHoldEnd()") : source.index("static OnCancel")]
    assert "if this.StartInProgress" in auto_send_end
    assert "this.ReleasePending := true" in auto_send_end
    assert "voice_auto_send_release_queued" in auto_send_end

    insert_process = source[source.index("static DoInsertProcess()") : source.index("static StartStatusPolling")]
    assert "if this.StartInProgress" in insert_process
    assert "voice_stop_queued_while_starting" in insert_process


def test_internal_bridge_race_errors_are_not_shown_raw_to_user() -> None:
    source = _read("ahk_client/src/main.ahk")

    assert 'ShowTrayTip("错误", result.error)' not in source
    assert 'ShowTrayTip("错误", status.error)' not in source
    assert "this.ShowErrorTip(result.error)" in source
    assert 'BridgeClient.Repair("recording_status_error")' in source
    assert 'BridgeClient.Repair("finish_status_error")' in source
    assert "ASR 出错，已自动自检修复，请重试" in source
    assert 'if message = "already_recording"' in source
    assert 'if message = "no_active_session"' in source
