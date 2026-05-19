from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


INT16_MAX = 32767.0


@dataclass
class AudioProcessingConfig:
    enabled: bool = True
    target_rms: float = 3600.0
    max_gain: float = 4.0
    min_gain: float = 0.75
    limiter_peak: float = 0.92 * INT16_MAX
    noise_floor_initial: float = 120.0
    noise_gate_floor: float = 95.0
    noise_gate_ratio: float = 1.7
    noise_reduction_gain: float = 0.30
    dc_offset_removal: bool = True
    attack: float = 0.35
    release: float = 0.16


@dataclass
class AudioProcessingStats:
    input_rms: float = 0.0
    output_rms: float = 0.0
    input_peak: int = 0
    output_peak: int = 0
    gain: float = 1.0
    noise_floor: float = 0.0
    gated: bool = False
    limited: bool = False


class AudioProcessor:
    """Realtime int16 PCM enhancer for ASR input.

    This intentionally stays lightweight: a noise-floor tracker, downward
    expander/noise gate, AGC, and limiter. It avoids heavyweight spectral
    processing in the PortAudio callback path.
    """

    def __init__(self, config: AudioProcessingConfig | None = None) -> None:
        self.config = config or AudioProcessingConfig()
        self.noise_floor = float(self.config.noise_floor_initial)
        self._smoothed_gain = 1.0

    def process(self, audio_bytes: bytes) -> tuple[bytes, AudioProcessingStats]:
        if not audio_bytes:
            return audio_bytes, AudioProcessingStats(noise_floor=self.noise_floor)
        if not self.config.enabled:
            stats = self._measure(audio_bytes)
            return audio_bytes, stats

        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        if samples.size == 0:
            return audio_bytes, AudioProcessingStats(noise_floor=self.noise_floor)

        signal = samples.astype(np.float32)
        if self.config.dc_offset_removal:
            signal = signal - float(np.mean(signal))

        input_rms = self._rms(signal)
        input_peak = int(np.max(np.abs(signal))) if signal.size else 0
        self._update_noise_floor(input_rms)

        gate_threshold = max(self.config.noise_gate_floor, self.noise_floor * self.config.noise_gate_ratio)
        gated = input_rms < gate_threshold
        if gated:
            target_gain = self.config.noise_reduction_gain if input_rms >= self.noise_floor * 0.8 else 0.0
        else:
            target_gain = self.config.target_rms / max(input_rms, 1.0)
            target_gain = min(self.config.max_gain, max(self.config.min_gain, target_gain))

        smoothing = self.config.attack if target_gain < self._smoothed_gain else self.config.release
        self._smoothed_gain = (self._smoothed_gain * (1.0 - smoothing)) + (target_gain * smoothing)
        processed = signal * self._smoothed_gain

        limited = False
        output_peak_float = float(np.max(np.abs(processed))) if processed.size else 0.0
        if output_peak_float > self.config.limiter_peak:
            processed *= self.config.limiter_peak / output_peak_float
            limited = True

        processed = np.clip(processed, -32768, 32767).astype(np.int16)
        output_rms = self._rms(processed.astype(np.float32))
        output_peak = int(np.max(np.abs(processed))) if processed.size else 0
        stats = AudioProcessingStats(
            input_rms=input_rms,
            output_rms=output_rms,
            input_peak=input_peak,
            output_peak=output_peak,
            gain=self._smoothed_gain,
            noise_floor=self.noise_floor,
            gated=gated,
            limited=limited,
        )
        return processed.tobytes(), stats

    def _update_noise_floor(self, rms: float) -> None:
        if rms <= 0:
            self.noise_floor *= 0.995
            return
        if rms < max(self.config.noise_gate_floor * 1.5, self.noise_floor * 1.8):
            self.noise_floor = (self.noise_floor * 0.96) + (rms * 0.04)

    def _measure(self, audio_bytes: bytes) -> AudioProcessingStats:
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        if samples.size == 0:
            return AudioProcessingStats(noise_floor=self.noise_floor)
        signal = samples.astype(np.float32)
        rms = self._rms(signal)
        peak = int(np.max(np.abs(signal))) if signal.size else 0
        return AudioProcessingStats(
            input_rms=rms,
            output_rms=rms,
            input_peak=peak,
            output_peak=peak,
            gain=1.0,
            noise_floor=self.noise_floor,
            gated=False,
            limited=False,
        )

    @staticmethod
    def _rms(samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return float(math.sqrt(float(np.mean(samples.astype(np.float32) ** 2))))
