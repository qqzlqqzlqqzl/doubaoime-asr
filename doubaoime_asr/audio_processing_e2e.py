from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any
import wave

import numpy as np

from doubaoime_asr.asr import ASRError, ResponseType, transcribe_realtime
from doubaoime_asr.audio_processing import AudioProcessor, AudioProcessingStats
from doubaoime_asr.config import ASRConfig
from doubaoime_asr.long_text_sample import (
    LONG_TEXT_SEGMENTS,
    SAMPLE_RATE,
    SILENCE_PATTERN,
    VOLUME_PATTERN,
    _decode_chunk,
    _shape_volume,
    _write_sapi_chunks,
    cjk_char_count,
    default_credential_path,
)
from doubaoime_asr.transcript import TranscriptAccumulator


SIMULATED_SEGMENTS = 3
SIMULATED_KEYWORDS = ["清晨", "会议室", "备用电池"]


@dataclass
class WavMetrics:
    path: str
    duration_seconds: float
    frames: int
    rms: float
    peak: int
    mean: float
    cjk_source_chars: int = 0


@dataclass
class StreamProcessingMetrics:
    frames: int = 0
    input_rms_mean: float = 0.0
    output_rms_mean: float = 0.0
    input_peak_max: int = 0
    output_peak_max: int = 0
    gain_min: float = 1.0
    gain_max: float = 1.0
    gain_mean: float = 1.0
    noise_floor_mean: float = 0.0
    gated_frames: int = 0
    limited_frames: int = 0


class ProcessingStatsCollector:
    def __init__(self) -> None:
        self.frames = 0
        self.input_rms_total = 0.0
        self.output_rms_total = 0.0
        self.input_peak_max = 0
        self.output_peak_max = 0
        self.gain_min = math.inf
        self.gain_max = 0.0
        self.gain_total = 0.0
        self.noise_floor_total = 0.0
        self.gated_frames = 0
        self.limited_frames = 0

    def add(self, stats: AudioProcessingStats) -> None:
        self.frames += 1
        self.input_rms_total += stats.input_rms
        self.output_rms_total += stats.output_rms
        self.input_peak_max = max(self.input_peak_max, stats.input_peak)
        self.output_peak_max = max(self.output_peak_max, stats.output_peak)
        self.gain_min = min(self.gain_min, stats.gain)
        self.gain_max = max(self.gain_max, stats.gain)
        self.gain_total += stats.gain
        self.noise_floor_total += stats.noise_floor
        if stats.gated:
            self.gated_frames += 1
        if stats.limited:
            self.limited_frames += 1

    def summary(self) -> StreamProcessingMetrics:
        if self.frames == 0:
            return StreamProcessingMetrics()
        return StreamProcessingMetrics(
            frames=self.frames,
            input_rms_mean=round(self.input_rms_total / self.frames, 3),
            output_rms_mean=round(self.output_rms_total / self.frames, 3),
            input_peak_max=self.input_peak_max,
            output_peak_max=self.output_peak_max,
            gain_min=round(self.gain_min if math.isfinite(self.gain_min) else 1.0, 3),
            gain_max=round(self.gain_max, 3),
            gain_mean=round(self.gain_total / self.frames, 3),
            noise_floor_mean=round(self.noise_floor_total / self.frames, 3),
            gated_frames=self.gated_frames,
            limited_frames=self.limited_frames,
        )


def source_text(segment_count: int = SIMULATED_SEGMENTS) -> str:
    return "".join(LONG_TEXT_SEGMENTS[:segment_count])


def default_clean_path() -> Path:
    return Path(".devtools") / "samples" / "simulated-clean-speech.wav"


def default_degraded_path() -> Path:
    return Path(".devtools") / "samples" / "simulated-degraded-speech.wav"


def default_report_path() -> Path:
    return Path("release") / "test-reports" / "simulated-audio-processing-asr.json"


def generate_simulated_speech_sample(output: str | Path, *, voice: str | None = None, segment_count: int = SIMULATED_SEGMENTS) -> WavMetrics:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    segment_count = max(1, min(segment_count, len(LONG_TEXT_SEGMENTS)))

    with tempfile.TemporaryDirectory(prefix="doubao-sim-audio-") as tmp:
        tmp_dir = Path(tmp)
        chunks = _write_sapi_chunks(tmp_dir, voice=voice)[:segment_count]
        pieces: list[np.ndarray] = []
        for index, chunk in enumerate(chunks):
            samples = _decode_chunk(chunk)
            pieces.append(_shape_volume(samples, VOLUME_PATTERN[index]))
            silence = np.zeros(int(SAMPLE_RATE * SILENCE_PATTERN[index]), dtype=np.int16)
            pieces.append(silence)

    combined = np.concatenate(pieces) if pieces else np.array([], dtype=np.int16)
    _write_wav(output_path, combined, SAMPLE_RATE)
    metrics = wav_metrics(output_path)
    metrics.cjk_source_chars = cjk_char_count(source_text(segment_count))
    return metrics


def degrade_wav(
    clean_path: str | Path,
    degraded_path: str | Path,
    *,
    gain: float = 0.18,
    noise_rms: float = 75.0,
    dc_offset: float = 80.0,
    seed: int = 20260519,
) -> WavMetrics:
    clean = _read_wav_int16(Path(clean_path))
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, noise_rms, clean.size).astype(np.float32)
    degraded = clean.astype(np.float32) * gain + noise + dc_offset
    degraded = np.clip(degraded, -32768, 32767).astype(np.int16)
    output = Path(degraded_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(output, degraded, SAMPLE_RATE)
    return wav_metrics(output)


def wav_metrics(audio_path: str | Path) -> WavMetrics:
    path = Path(audio_path)
    samples = _read_wav_int16(path)
    if samples.size == 0:
        return WavMetrics(str(path), 0.0, 0, 0.0, 0, 0.0)
    signal = samples.astype(np.float32)
    return WavMetrics(
        path=str(path),
        duration_seconds=round(samples.size / SAMPLE_RATE, 3),
        frames=int(samples.size),
        rms=round(float(math.sqrt(float(np.mean(signal * signal)))), 3),
        peak=int(np.max(np.abs(samples.astype(np.int32)))),
        mean=round(float(np.mean(signal)), 3),
    )


async def _pcm_chunks_from_wav(
    audio_path: Path,
    config: ASRConfig,
    *,
    processor: AudioProcessor | None = None,
    stats_collector: ProcessingStatsCollector | None = None,
):
    samples_per_frame = config.sample_rate * config.frame_duration_ms // 1000
    bytes_per_frame = samples_per_frame * 2
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != config.sample_rate:
            raise ValueError(
                f"Expected {config.sample_rate} Hz mono int16 WAV, got "
                f"channels={wav.getnchannels()}, width={wav.getsampwidth()}, rate={wav.getframerate()}"
            )
        while True:
            chunk = wav.readframes(samples_per_frame)
            if not chunk:
                break
            if len(chunk) < bytes_per_frame:
                chunk += b"\x00" * (bytes_per_frame - len(chunk))
            if processor is not None:
                chunk, stats = processor.process(chunk)
                if stats_collector is not None:
                    stats_collector.add(stats)
            yield chunk
            await asyncio.sleep(0)


async def run_streaming_asr_pass(
    audio_path: str | Path,
    credential_path: str | Path,
    *,
    process_audio: bool,
    min_chars: int,
    min_keywords: int,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    config = ASRConfig(credential_path=str(credential_path))
    processor = AudioProcessor() if process_audio else None
    stats_collector = ProcessingStatsCollector() if process_audio else None
    transcript = TranscriptAccumulator()
    finals: list[str] = []
    events: list[dict[str, Any]] = []

    try:
        source = _pcm_chunks_from_wav(Path(audio_path), config, processor=processor, stats_collector=stats_collector)
        async for response in transcribe_realtime(source, config=config):
            event = {
                "type": response.type.name,
                "text": response.text,
                "error_msg": response.error_msg,
                "packet_number": response.packet_number,
            }
            events.append(event)
            if response.type == ResponseType.FINAL_RESULT and response.text:
                finals.append(response.text)
            if response.type in {ResponseType.INTERIM_RESULT, ResponseType.FINAL_RESULT} and response.text:
                transcript.update(response.text, is_final=response.type == ResponseType.FINAL_RESULT)
            if response.type == ResponseType.ERROR:
                break
    except (ASRError, Exception) as exc:
        events.append({"type": "EXCEPTION", "text": "", "error_msg": repr(exc), "packet_number": -1})

    recognized_text = transcript.text or "".join(finals)
    keyword_set = keywords or SIMULATED_KEYWORDS
    matched_keywords = [keyword for keyword in keyword_set if keyword in recognized_text]
    errors = [event for event in events if event["type"] in {"ERROR", "EXCEPTION"}]
    passed = not errors and len(recognized_text) >= min_chars and len(matched_keywords) >= min_keywords
    result: dict[str, Any] = {
        "passed": passed,
        "process_audio": process_audio,
        "recognized_text": recognized_text,
        "recognized_chars": len(recognized_text),
        "final_segments": finals,
        "matched_keywords": matched_keywords,
        "required_min_chars": min_chars,
        "required_min_keywords": min_keywords,
        "errors": errors,
        "events": events,
    }
    if stats_collector is not None:
        result["processing_metrics"] = asdict(stats_collector.summary())
    return result


def run_simulated_audio_processing_test(
    *,
    clean_audio_path: str | Path | None = None,
    degraded_audio_path: str | Path | None = None,
    report_path: str | Path | None = None,
    credential_path: str | Path | None = None,
    generate_only: bool = False,
    segment_count: int = SIMULATED_SEGMENTS,
    gain: float = 0.18,
    noise_rms: float = 75.0,
    dc_offset: float = 80.0,
    seed: int = 20260519,
    min_processed_chars: int = 30,
    min_keywords: int = 1,
) -> int:
    clean_path = Path(clean_audio_path) if clean_audio_path else default_clean_path()
    degraded_path = Path(degraded_audio_path) if degraded_audio_path else default_degraded_path()
    report = Path(report_path) if report_path else default_report_path()
    credential = Path(credential_path) if credential_path else default_credential_path()
    text = source_text(segment_count)

    result: dict[str, Any] = {
        "ok": False,
        "runner": {
            "executable": sys.executable,
            "frozen": bool(getattr(sys, "frozen", False)),
            "component": "simulated_audio_processing_e2e",
        },
        "parameters": {
            "segment_count": segment_count,
            "gain": gain,
            "noise_rms": noise_rms,
            "dc_offset": dc_offset,
            "seed": seed,
            "min_processed_chars": min_processed_chars,
            "min_keywords": min_keywords,
        },
        "source_text": text,
        "source_cjk_chars": cjk_char_count(text),
        "keywords": SIMULATED_KEYWORDS,
    }

    try:
        result["clean_audio"] = asdict(generate_simulated_speech_sample(clean_path, segment_count=segment_count))
        result["degraded_audio"] = asdict(
            degrade_wav(degraded_path=degraded_path, clean_path=clean_path, gain=gain, noise_rms=noise_rms, dc_offset=dc_offset, seed=seed)
        )

        if generate_only:
            result["ok"] = True
        else:
            raw = asyncio.run(
                run_streaming_asr_pass(
                    degraded_path,
                    credential,
                    process_audio=False,
                    min_chars=0,
                    min_keywords=0,
                    keywords=SIMULATED_KEYWORDS,
                )
            )
            processed = asyncio.run(
                run_streaming_asr_pass(
                    degraded_path,
                    credential,
                    process_audio=True,
                    min_chars=min_processed_chars,
                    min_keywords=min_keywords,
                    keywords=SIMULATED_KEYWORDS,
                )
            )
            raw_chars = int(raw.get("recognized_chars", 0))
            processed_chars = int(processed.get("recognized_chars", 0))
            raw_keywords = len(raw.get("matched_keywords", []))
            processed_keywords = len(processed.get("matched_keywords", []))
            processing_metrics = processed.get("processing_metrics", {})
            result["asr"] = {"raw_degraded": raw, "processed_degraded": processed}
            result["comparison"] = {
                "recognized_char_delta": processed_chars - raw_chars,
                "matched_keyword_delta": processed_keywords - raw_keywords,
                "processed_has_no_errors": not bool(processed.get("errors")),
                "processed_audio_rms_delta": round(
                    float(processing_metrics.get("output_rms_mean", 0.0)) - float(processing_metrics.get("input_rms_mean", 0.0)),
                    3,
                ),
                "asr_text_improved_or_equal": processed_chars >= raw_chars and processed_keywords >= raw_keywords,
            }
            result["ok"] = bool(processed.get("passed")) and bool(result["comparison"]["processed_has_no_errors"])
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if result["ok"] else 1


def _read_wav_int16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
            raise ValueError(
                f"Expected {SAMPLE_RATE} Hz mono int16 WAV, got "
                f"channels={wav.getnchannels()}, width={wav.getsampwidth()}, rate={wav.getframerate()}"
            )
        data = wav.readframes(wav.getnframes())
    return np.frombuffer(data, dtype=np.int16).copy()


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.astype(np.int16).tobytes())
