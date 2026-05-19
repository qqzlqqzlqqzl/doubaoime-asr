from __future__ import annotations

from pathlib import Path
import wave

import numpy as np

from doubaoime_asr.audio_processing_e2e import (
    ProcessingStatsCollector,
    degrade_wav,
    wav_metrics,
)
from doubaoime_asr.audio_processing import AudioProcessor
from doubaoime_asr.long_text_sample import SAMPLE_RATE


def _write_test_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.astype(np.int16).tobytes())


def test_degrade_wav_is_deterministic_and_keeps_format(tmp_path: Path) -> None:
    clean = tmp_path / "clean.wav"
    degraded_1 = tmp_path / "degraded-1.wav"
    degraded_2 = tmp_path / "degraded-2.wav"
    tone = np.sin(np.linspace(0, np.pi * 20, SAMPLE_RATE, dtype=np.float32)) * 6000
    _write_test_wav(clean, tone.astype(np.int16))

    metrics_1 = degrade_wav(clean, degraded_1, gain=0.2, noise_rms=40.0, dc_offset=30.0, seed=7)
    metrics_2 = degrade_wav(clean, degraded_2, gain=0.2, noise_rms=40.0, dc_offset=30.0, seed=7)

    assert degraded_1.read_bytes() == degraded_2.read_bytes()
    assert metrics_1.frames == SAMPLE_RATE
    assert metrics_1.duration_seconds == 1.0
    assert metrics_1.rms < wav_metrics(clean).rms
    assert metrics_2.peak < 32767


def test_processing_stats_collector_tracks_streaming_gain() -> None:
    processor = AudioProcessor()
    collector = ProcessingStatsCollector()
    frame = (
        np.sin(np.linspace(0, np.pi * 8, 320, dtype=np.float32)) * 850
    ).astype(np.int16).tobytes()

    for _ in range(16):
        processed, stats = processor.process(frame)
        assert len(processed) == len(frame)
        collector.add(stats)

    summary = collector.summary()
    assert summary.frames == 16
    assert summary.output_rms_mean > summary.input_rms_mean
    assert summary.gain_max > 1.0
    assert summary.input_peak_max > 0
    assert summary.output_peak_max > 0
