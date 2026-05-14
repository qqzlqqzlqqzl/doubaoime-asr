from __future__ import annotations

import queue
from typing import Callable

from doubaoime_asr.desktop_app import DesktopApp, DesktopConfig


class FakeVar:
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
    app.recording_session_id = 7
    app.recording_mode = mode
    app.pending_mode = None
    app.cancelled = False
    app.final_text = ""
    app.target_hwnd = 12345
    app.active_keys = {"rctrl"} if mode == "hold" else {"lctrl", "lwin"}
    app.audio_queue = queue.Queue()
    stream = FakeStream()
    app.audio_stream = stream
    app.status_var = FakeVar()

    scheduled: list[dict[str, object]] = []
    inserted: list[dict[str, object]] = []
    hidden: list[bool] = []

    def schedule_ui(delay_ms: int, callback: Callable[[], None]) -> object:
        scheduled.append({"delay_ms": delay_ms, "callback": callback})
        if auto_run_callbacks:
            callback()
        return object()

    app.schedule_ui = schedule_ui  # type: ignore[method-assign]
    app.hide_float = lambda: hidden.append(True)  # type: ignore[method-assign]
    app.show_float = lambda _text: None  # type: ignore[method-assign]

    def insert_text(text: str, auto_send: bool, target_hwnd: int | None = None) -> None:
        inserted.append({"text": text, "auto_send": auto_send, "target_hwnd": target_hwnd})

    app.insert_text = insert_text  # type: ignore[method-assign]
    app._test_hidden = hidden  # type: ignore[attr-defined]
    return app, scheduled, inserted, stream


def test_hold_release_automatically_inserts_final_text_without_float_button() -> None:
    app, scheduled, inserted, stream = build_app("hold")

    app._handle_active_release("rctrl")
    app.final_text = "松手后自动插入"
    app._finish_insert(app.recording_session_id)

    assert app.recording_mode is None
    assert app.pending_mode is None
    assert stream.stopped is True
    assert stream.closed is True
    assert any(item["delay_ms"] == 0 for item in scheduled)
    assert inserted == [{"text": "松手后自动插入", "auto_send": False, "target_hwnd": 12345}]
    assert app._test_hidden  # type: ignore[attr-defined]


def test_hold_send_release_automatically_inserts_and_sends() -> None:
    app, _scheduled, inserted, _stream = build_app("hold_send")

    app._handle_active_release("lwin")
    app.final_text = "松手后自动插入并发送"
    app._finish_insert(app.recording_session_id)

    assert inserted == [{"text": "松手后自动插入并发送", "auto_send": True, "target_hwnd": 12345}]


def test_hold_release_does_not_insert_when_cancelled_or_empty() -> None:
    cancelled_app, _scheduled, cancelled_inserted, _stream = build_app("hold")
    cancelled_app.cancelled = True
    cancelled_app._handle_active_release("rctrl")
    cancelled_app.final_text = "这句不应该插入"
    cancelled_app._finish_insert(cancelled_app.recording_session_id)
    assert cancelled_inserted == []

    empty_app, _scheduled, empty_inserted, _stream = build_app("hold")
    empty_app._handle_active_release("rctrl")
    empty_app._finish_insert(empty_app.recording_session_id)
    assert empty_inserted == []


def test_hold_release_delayed_insert_survives_fast_next_recording() -> None:
    app, scheduled, inserted, _stream = build_app("hold", auto_run_callbacks=False)

    app._handle_active_release("rctrl")
    app.final_text = "上一句不能被下一段吞掉"
    original_session_id = app.recording_session_id
    app._finish_insert(original_session_id)
    app.recording_session_id += 1
    for item in scheduled:
        if item["delay_ms"] == 0:
            callback = item["callback"]
            assert callable(callback)
            callback()

    assert inserted == [{"text": "上一句不能被下一段吞掉", "auto_send": False, "target_hwnd": 12345}]
