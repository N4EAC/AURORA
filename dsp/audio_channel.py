"""Deterministic offline real-audio channel impairments for Aurora."""

from dataclasses import dataclass
import math

import numpy as np

from audio.buffer import AudioBuffer


@dataclass(frozen=True, slots=True)
class AudioChannelConfig:
    """Parameters for one offline audio-channel realization."""

    snr_db: float | None = None
    reference_bandwidth_hz: float = 2_500.0
    amplitude_scale: float = 1.0
    timing_offset_samples: float = 0.0
    clock_error_ppm: float = 0.0
    multipath_delay_ms: float = 0.0
    multipath_gain: float = 0.0
    multipath_fading_depth: float = 0.0
    multipath_fading_cycles_per_frame: float = 0.0
    fading_depth: float = 0.0
    fading_cycles_per_frame: float = 0.0
    impulse_probability: float = 0.0
    impulse_scale: float = 0.0

    def __post_init__(self) -> None:
        if self.reference_bandwidth_hz <= 0.0:
            raise ValueError("Reference bandwidth must be positive")
        if self.amplitude_scale <= 0.0:
            raise ValueError("Amplitude scale must be positive")
        if not 0.0 <= self.timing_offset_samples < 1.0:
            raise ValueError("Timing offset must be within one audio sample")
        if self.multipath_delay_ms < 0.0 or self.multipath_gain < 0.0:
            raise ValueError("Multipath delay and gain must not be negative")
        if self.multipath_gain > 0.0 and self.multipath_delay_ms <= 0.0:
            raise ValueError("Active multipath requires a positive delay")
        if not 0.0 <= self.multipath_fading_depth < 1.0:
            raise ValueError("Multipath fading depth must be between zero and one")
        if self.multipath_fading_cycles_per_frame < 0.0:
            raise ValueError("Multipath fading cycles must not be negative")
        if self.multipath_fading_depth > 0.0 and self.multipath_gain == 0.0:
            raise ValueError("Multipath fading requires an active path")
        if not 0.0 <= self.fading_depth < 1.0:
            raise ValueError("Fading depth must be between zero and one")
        if self.fading_cycles_per_frame < 0.0:
            raise ValueError("Fading cycles must not be negative")
        if not 0.0 <= self.impulse_probability <= 1.0:
            raise ValueError("Impulse probability must be between zero and one")
        if self.impulse_scale < 0.0:
            raise ValueError("Impulse scale must not be negative")


def _fractional_delay(samples: np.ndarray, delay: float) -> np.ndarray:
    if delay == 0.0:
        return samples.copy()
    indices = np.arange(len(samples), dtype=np.float64)
    return np.interp(indices - delay, indices, samples, left=0.0, right=0.0)


def _apply_clock_error(samples: np.ndarray, ppm: float) -> np.ndarray:
    if ppm == 0.0:
        return samples.copy()
    indices = np.arange(len(samples), dtype=np.float64)
    source_positions = indices * (1.0 + ppm * 1e-6)
    return np.interp(source_positions, indices, samples, left=0.0, right=0.0)


def _add_multipath(
    samples: np.ndarray,
    sample_rate: int,
    delay_ms: float,
    gain: float,
    fading_depth: float,
    fading_cycles: float,
    random: np.random.Generator,
) -> np.ndarray:
    if gain == 0.0:
        return samples.copy()
    delay_samples = max(1, round(delay_ms * sample_rate / 1_000.0))
    echo = np.zeros_like(samples)
    if delay_samples < len(samples):
        echo[delay_samples:] = samples[:-delay_samples]
    if fading_depth > 0.0:
        phase = random.uniform(0.0, 2.0 * math.pi)
        positions = np.arange(len(samples), dtype=np.float64)
        envelope = 1.0 + fading_depth * np.sin(
            phase
            + 2.0
            * math.pi
            * fading_cycles
            * positions
            / max(1, len(samples))
        )
        echo *= envelope
    return (samples + gain * echo) / math.sqrt(1.0 + gain * gain)


def _apply_fading(
    samples: np.ndarray,
    depth: float,
    cycles: float,
    random: np.random.Generator,
) -> np.ndarray:
    if depth == 0.0:
        return samples.copy()
    indices = np.arange(len(samples), dtype=np.float64)
    phase = random.uniform(0.0, 2.0 * math.pi)
    envelope = 1.0 + depth * np.sin(
        phase + 2.0 * math.pi * cycles * indices / max(1, len(samples))
    )
    envelope /= math.sqrt(float(np.mean(envelope * envelope)))
    return samples * envelope


def _add_impulses(
    samples: np.ndarray,
    probability: float,
    scale: float,
    random: np.random.Generator,
) -> np.ndarray:
    if probability == 0.0 or scale == 0.0:
        return samples.copy()
    result = samples.copy()
    mask = random.random(len(result)) < probability
    result[mask] += random.normal(0.0, scale, int(np.count_nonzero(mask)))
    return result


def reference_noise_variance(
    signal_power: float,
    snr_db: float,
    sample_rate: int,
    reference_bandwidth_hz: float,
) -> float:
    """Return real white-noise variance for SNR in a reference bandwidth."""
    if signal_power < 0.0:
        raise ValueError("Signal power must not be negative")
    if sample_rate <= 0 or not 0.0 < reference_bandwidth_hz <= sample_rate / 2.0:
        raise ValueError("Reference bandwidth must be within audio Nyquist")
    snr_linear = 10.0 ** (snr_db / 10.0)
    return signal_power / snr_linear * sample_rate / (2.0 * reference_bandwidth_hz)


def apply_audio_channel(
    audio: AudioBuffer,
    config: AudioChannelConfig,
    random: np.random.Generator,
) -> AudioBuffer:
    """Apply seeded impairments without opening an audio device."""
    if audio.channel_count != 1:
        raise ValueError("Offline audio channel requires mono samples")
    if config.reference_bandwidth_hz > audio.sample_rate / 2.0:
        raise ValueError("Reference bandwidth exceeds audio Nyquist")

    working = np.asarray(audio.samples, dtype=np.float64) * config.amplitude_scale
    working = _fractional_delay(working, config.timing_offset_samples)
    working = _apply_clock_error(working, config.clock_error_ppm)
    working = _add_multipath(
        working,
        audio.sample_rate,
        config.multipath_delay_ms,
        config.multipath_gain,
        config.multipath_fading_depth,
        config.multipath_fading_cycles_per_frame,
        random,
    )
    working = _apply_fading(
        working,
        config.fading_depth,
        config.fading_cycles_per_frame,
        random,
    )
    working = _add_impulses(
        working,
        config.impulse_probability,
        config.impulse_scale,
        random,
    )
    if config.snr_db is not None:
        signal_power = float(np.mean(working * working))
        variance = reference_noise_variance(
            signal_power,
            config.snr_db,
            audio.sample_rate,
            config.reference_bandwidth_hz,
        )
        working += random.normal(0.0, math.sqrt(variance), len(working))
    return AudioBuffer(working.astype(np.float32), audio.sample_rate)
