from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
from typing import Any

import sounddevice as sd

if getattr(sys, "frozen", False):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = str(bundle_dir) + os.pathsep + os.environ.get("PATH", "")

from doubaoime_asr.asr import ASRError, ResponseType, transcribe_realtime
from doubaoime_asr.config import ASRConfig
from doubaoime_asr.transcript import TranscriptAccumulator


APP_CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "DoubaoASRHelper"
DEFAULT_CREDENTIAL_PATH = APP_CONFIG_DIR / "credentials.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765


@dataclass
class BridgeResult:
    ok: bool
    text: str = ""
    error: str = ""
    state: str = "idle"
    session_id: int = 0


class RecordingSession:
    def __init__(self, session_id: int, config: ASRConfig, device: int | str | None = None) -> None:
        self.session_id = session_id
        self.config = config
        self.device = device
        self.audio_queue: queue.Queue[bytes | None] = queue.Queue()
        self.transcript = TranscriptAccumulator()
        self.final_text = ""
        self.error = ""
        self.cancelled = False
        self.state = "starting"
        self.done = threading.Event()
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream: sd.InputStream | None = None
        self._thread = threading.Thread(target=self._run_asr_thread, name=f"asr-bridge-{session_id}", daemon=True)

    def start(self) -> None:
        samples_per_frame = self.config.sample_rate * self.config.frame_duration_ms // 1000

        def callback(indata, _frames, _time_info, status) -> None:
            if status:
                with self._lock:
                    self.error = str(status)
            self.audio_queue.put(bytes(indata))

        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            blocksize=samples_per_frame,
            callback=callback,
            device=self.device,
        )
        self._stream.start()
        with self._lock:
            self.state = "recording"
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self.state in {"finishing", "finished", "cancelled", "error"}:
                return
            self.state = "finishing"
        self._close_stream()
        self.audio_queue.put(None)

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            self.state = "cancelled"
        self._close_stream()
        self.audio_queue.put(None)

    def wait(self, timeout: float) -> bool:
        return self.done.wait(timeout)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "state": self.state,
                "cancelled": self.cancelled,
                "text": "" if self.cancelled else self.transcript.text,
                "final_text": "" if self.cancelled else self.final_text,
                "error": self.error,
                "thread_alive": self._thread.is_alive(),
                "done": self.done.is_set(),
            }

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()

    async def _audio_source(self):
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, self.audio_queue.get)
            if item is None:
                break
            yield item

    def _run_asr_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_asr())
        finally:
            self._loop.close()
            self.done.set()

    async def _run_asr(self) -> None:
        try:
            async for response in transcribe_realtime(self._audio_source(), config=self.config):
                if response.type in {ResponseType.INTERIM_RESULT, ResponseType.FINAL_RESULT}:
                    text = self.transcript.update(response.text, is_final=response.type == ResponseType.FINAL_RESULT)
                    with self._lock:
                        if not self.cancelled:
                            self.final_text = text
                elif response.type == ResponseType.ERROR:
                    with self._lock:
                        self.error = response.error_msg
                        self.state = "error"
                    return
            self.transcript.commit()
            with self._lock:
                if self.cancelled:
                    self.final_text = ""
                    self.state = "cancelled"
                else:
                    self.final_text = self.transcript.text
                    self.state = "finished"
        except ASRError as exc:
            with self._lock:
                self.error = str(exc)
                self.state = "error"
        except Exception as exc:  # pragma: no cover - defensive bridge boundary
            with self._lock:
                self.error = repr(exc)
                self.state = "error"


class BridgeState:
    def __init__(self, credential_path: str | Path = DEFAULT_CREDENTIAL_PATH, device: int | str | None = None) -> None:
        self.credential_path = str(Path(credential_path).expanduser())
        self.device = device
        self._lock = threading.RLock()
        self._session: RecordingSession | None = None
        self._session_id = 0

    def start(self) -> BridgeResult:
        with self._lock:
            if self._session is not None and self._session.snapshot()["state"] in {"starting", "recording", "finishing"}:
                return BridgeResult(False, error="already_recording", state=self._session.snapshot()["state"], session_id=self._session.session_id)
            self._session_id += 1
            config = ASRConfig(credential_path=self.credential_path)
            session = RecordingSession(self._session_id, config, self.device)
            self._session = session
        try:
            session.start()
            return BridgeResult(True, state="recording", session_id=session.session_id)
        except Exception as exc:
            with self._lock:
                self._session = None
            return BridgeResult(False, error=repr(exc), state="error", session_id=session.session_id)

    def stop(self, timeout: float = 30.0, wait: bool = True) -> BridgeResult:
        session = self._session
        if session is None:
            return BridgeResult(False, error="no_active_session", state="idle")
        session.stop()
        if wait:
            session.wait(timeout)
        snapshot = session.snapshot()
        text = str(snapshot.get("final_text") or snapshot.get("text") or "")
        ok = (not wait or bool(snapshot.get("done"))) and not snapshot.get("error")
        if snapshot.get("cancelled"):
            text = ""
            ok = True
        return BridgeResult(ok, text=text, error=str(snapshot.get("error") or ""), state=str(snapshot.get("state") or ""), session_id=session.session_id)

    def cancel(self) -> BridgeResult:
        session = self._session
        if session is None:
            return BridgeResult(True, state="idle")
        session.cancel()
        return BridgeResult(True, state="cancelled", session_id=session.session_id)

    def status(self) -> dict[str, Any]:
        session = self._session
        if session is None:
            return {"ok": True, "state": "idle", "session_id": self._session_id}
        snapshot = session.snapshot()
        snapshot["ok"] = not bool(snapshot.get("error"))
        return snapshot


class BridgeRequestHandler(BaseHTTPRequestHandler):
    server_version = "DoubaoASRBridge/0.1"

    @property
    def bridge(self) -> BridgeState:
        return self.server.bridge_state  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/status":
            self._send_json(self.bridge.status())
            return
        if self.path.split("?", 1)[0] == "/health":
            self._send_json({"ok": True, "state": "ready"})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        payload = self._read_json()
        if path == "/start":
            self._send_json(self.bridge.start().__dict__)
            return
        if path == "/stop":
            timeout_ms = int(payload.get("timeout_ms", 30000))
            wait = bool(payload.get("wait", True))
            self._send_json(self.bridge.stop(timeout=max(timeout_ms, 1) / 1000, wait=wait).__dict__)
            return
        if path == "/cancel":
            self._send_json(self.bridge.cancel().__dict__)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_json(self, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BridgeServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], state: BridgeState) -> None:
        super().__init__(server_address, BridgeRequestHandler)
        self.bridge_state = state


def run_self_test() -> int:
    state = BridgeState(credential_path=Path(os.getenv("TEMP", ".")) / f"doubao-bridge-self-test-{os.getpid()}.json")
    status = state.status()
    if status["state"] != "idle":
        raise SystemExit("initial bridge state is not idle")
    result = state.cancel()
    if not result.ok:
        raise SystemExit("cancel without active session failed")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Doubao ASR bridge.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--credential-path", default=str(DEFAULT_CREDENTIAL_PATH))
    parser.add_argument("--device", default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        raise SystemExit(run_self_test())

    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state = BridgeState(args.credential_path, args.device)
    server = BridgeServer((args.host, args.port), state)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        state.cancel()
        time.sleep(0.1)
        server.server_close()


if __name__ == "__main__":
    main()
