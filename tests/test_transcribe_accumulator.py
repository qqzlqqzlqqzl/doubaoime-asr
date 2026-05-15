from __future__ import annotations

import pytest

from doubaoime_asr.asr import ASRResponse, DoubaoASR, ResponseType


@pytest.mark.asyncio
async def test_transcribe_accumulates_multiple_final_results(monkeypatch) -> None:
    async def fake_stream(self: DoubaoASR, audio: bytes, realtime: bool = False):
        yield ASRResponse(type=ResponseType.INTERIM_RESULT, text="第一段")
        yield ASRResponse(type=ResponseType.FINAL_RESULT, text="第一段")
        yield ASRResponse(type=ResponseType.INTERIM_RESULT, text="第二段")
        yield ASRResponse(type=ResponseType.FINAL_RESULT, text="第二段")

    monkeypatch.setattr(DoubaoASR, "transcribe_stream", fake_stream)

    text = await DoubaoASR().transcribe(b"pcm")

    assert text == "第一段第二段"
