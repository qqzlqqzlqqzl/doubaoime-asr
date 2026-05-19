from __future__ import annotations

import tracemalloc

import numpy as np

from doubaoime_asr.audio_processing import AudioProcessor


def _tone(amplitude: int, samples: int = 320) -> bytes:
    wave = np.sin(np.linspace(0, np.pi * 8, samples, dtype=np.float32))
    return np.clip(wave * amplitude, -32768, 32767).astype(np.int16).tobytes()


def _rms(audio: bytes) -> float:
    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def test_audio_processor_keeps_silence_silent_and_same_length() -> None:
    processor = AudioProcessor()
    silence = b"\x00\x00" * 320

    processed, stats = processor.process(silence)

    assert processed == silence
    assert len(processed) == len(silence)
    assert stats.gated is True
    assert stats.output_rms == 0


def test_audio_processor_reduces_low_noise_without_amplifying_it() -> None:
    processor = AudioProcessor()
    noise = _tone(80)

    processed, stats = processor.process(noise)

    assert len(processed) == len(noise)
    assert stats.gated is True
    assert _rms(processed) < _rms(noise)


def test_audio_processor_agc_raises_quiet_speech_over_several_frames() -> None:
    processor = AudioProcessor()
    quiet = _tone(900)
    processed = quiet
    stats = None

    for _ in range(12):
        processed, stats = processor.process(quiet)

    assert stats is not None
    assert len(processed) == len(quiet)
    assert stats.gated is False
    assert _rms(processed) > _rms(quiet) * 1.6
    assert stats.gain > 1.0


def test_audio_processor_limits_loud_speech_without_clipping() -> None:
    processor = AudioProcessor()
    loud = _tone(30000)

    processed, stats = processor.process(loud)
    samples = np.frombuffer(processed, dtype=np.int16)

    assert len(processed) == len(loud)
    assert stats.output_peak <= 30146
    assert int(np.max(samples)) < 32767
    assert int(np.min(samples)) > -32768


def test_audio_processor_does_not_accumulate_large_memory() -> None:
    processor = AudioProcessor()
    frame = _tone(1000)
    tracemalloc.start()
    try:
        before_current, _before_peak = tracemalloc.get_traced_memory()
        for _ in range(2000):
            processed, _stats = processor.process(frame)
            assert len(processed) == len(frame)
        after_current, after_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert after_current - before_current < 256 * 1024
    assert after_peak < 2 * 1024 * 1024
