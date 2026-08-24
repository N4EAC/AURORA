"""Aurora's bounded-bandwidth orthogonal frequency-division waveform."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from audio.buffer import AudioBuffer


@dataclass(frozen=True, slots=True)
class OfdmConfig:
    """Fixed physical parameters for the provisional Aurora OFDM waveform."""

    sample_rate: int = 12_000
    audio_center_hz: float = 1_500.0
    fft_size: int = 256
    cyclic_prefix_samples: int = 64
    data_subcarriers: tuple[int, ...] = (
        -4,
        -3,
        -2,
        -1,
        1,
        2,
        3,
        4,
    )
    training_symbol_count: int = 2

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.fft_size <= 0:
            raise ValueError("OFDM sample rate and FFT size must be positive")
        if not 0 < self.cyclic_prefix_samples < self.fft_size:
            raise ValueError("OFDM cyclic prefix must be shorter than the FFT")
        if self.training_symbol_count < 2:
            raise ValueError("OFDM requires at least two training symbols")
        if not self.data_subcarriers or 0 in self.data_subcarriers:
            raise ValueError("OFDM data carriers must be non-empty and omit DC")
        if len(set(self.data_subcarriers)) != len(self.data_subcarriers):
            raise ValueError("OFDM data carriers must be unique")
        if max(abs(index) for index in self.data_subcarriers) >= self.fft_size // 2:
            raise ValueError("OFDM data carrier exceeds the FFT passband")

    @property
    def block_samples(self) -> int:
        """Return the cyclic-prefix plus useful-symbol sample count."""
        return self.fft_size + self.cyclic_prefix_samples

    @property
    def subcarrier_spacing_hz(self) -> float:
        """Return the orthogonal carrier spacing."""
        return self.sample_rate / self.fft_size

    @property
    def occupied_span_hz(self) -> float:
        """Return the edge-to-edge active-subcarrier span."""
        return 2.0 * max(abs(index) for index in self.data_subcarriers) * (
            self.subcarrier_spacing_hz
        )


DEFAULT_OFDM_CONFIG = OfdmConfig()


def _training_values(config: OfdmConfig) -> NDArray[np.complex128]:
    """Return deterministic BPSK training values for channel estimation."""
    values = np.asarray(
        [1.0 if ((index * 17 + 5) % 7) < 3 else -1.0 for index in range(len(config.data_subcarriers))],
        dtype=np.complex128,
    )
    values.setflags(write=False)
    return values


def _ifft_block(values: NDArray[np.complex128], config: OfdmConfig) -> NDArray[np.complex128]:
    bins = np.zeros(config.fft_size, dtype=np.complex128)
    for carrier, value in zip(config.data_subcarriers, values, strict=True):
        bins[carrier % config.fft_size] = value
    useful = np.fft.ifft(bins) * config.fft_size / math.sqrt(len(values))
    return np.concatenate((useful[-config.cyclic_prefix_samples :], useful))


def frame_sample_count(payload_symbol_count: int, config: OfdmConfig = DEFAULT_OFDM_CONFIG) -> int:
    """Return the exact audio sample count for a known payload geometry."""
    if payload_symbol_count <= 0:
        raise ValueError("OFDM payload symbol count must be positive")
    payload_blocks = math.ceil(payload_symbol_count / len(config.data_subcarriers))
    return (config.training_symbol_count + payload_blocks) * config.block_samples


def modulate_ofdm_audio(
    payload_symbols: ArrayLike,
    config: OfdmConfig = DEFAULT_OFDM_CONFIG,
    *,
    leading_silence_samples: int = 0,
    frequency_offset_hz: float = 0.0,
) -> AudioBuffer:
    """Map constellation symbols across Aurora OFDM blocks and create real audio."""
    payload = np.asarray(payload_symbols, dtype=np.complex128)
    if payload.ndim != 1 or len(payload) == 0:
        raise ValueError("OFDM payload symbols must be a non-empty sequence")
    if not np.isfinite(payload).all():
        raise ValueError("OFDM payload symbols must be finite")
    if leading_silence_samples < 0:
        raise ValueError("Leading silence must not be negative")

    training = _ifft_block(_training_values(config), config)
    blocks = [training.copy() for _ in range(config.training_symbol_count)]
    width = len(config.data_subcarriers)
    for offset in range(0, len(payload), width):
        values = np.zeros(width, dtype=np.complex128)
        chunk = payload[offset : offset + width]
        values[: len(chunk)] = chunk
        blocks.append(_ifft_block(values, config))
    baseband = np.concatenate(blocks)
    indices = np.arange(len(baseband), dtype=np.float64)
    carrier_hz = config.audio_center_hz + frequency_offset_hz
    audio = np.real(
        baseband * np.exp(2j * math.pi * carrier_hz * indices / config.sample_rate)
    )
    peak = float(np.max(np.abs(audio)))
    if peak <= np.finfo(float).tiny:
        raise ValueError("OFDM waveform has zero amplitude")
    audio *= 0.78 / peak
    if leading_silence_samples:
        audio = np.pad(audio, (leading_silence_samples, 0))
    return AudioBuffer(audio.astype(np.float32), config.sample_rate)


def _find_training(
    baseband: NDArray[np.complex128], config: OfdmConfig
) -> tuple[int, float]:
    reference_block = _ifft_block(_training_values(config), config)
    reference = np.tile(reference_block, config.training_symbol_count)
    correlation = np.correlate(baseband, reference, mode="valid")
    energy = np.convolve(
        np.abs(baseband) ** 2,
        np.ones(len(reference), dtype=np.float64),
        mode="valid",
    )
    reference_energy = float(np.vdot(reference, reference).real)
    metric = np.abs(correlation) / np.sqrt(
        np.maximum(energy * reference_energy, np.finfo(float).tiny)
    )
    peak = float(np.max(metric))
    near_peak = np.flatnonzero(metric >= peak * 0.9999)
    index = int(near_peak[0])
    return index, float(metric[index])


def demodulate_ofdm_audio(
    audio: AudioBuffer,
    payload_symbol_count: int,
    config: OfdmConfig = DEFAULT_OFDM_CONFIG,
    *,
    sync_threshold: float = 0.65,
) -> tuple[NDArray[np.complex128], float, float, int]:
    """Acquire, frequency-correct, equalize, and recover OFDM payload symbols."""
    if audio.channel_count != 1 or audio.sample_rate != config.sample_rate:
        raise ValueError("OFDM receiver requires matching mono audio")
    if payload_symbol_count <= 0:
        raise ValueError("OFDM payload symbol count must be positive")
    samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(samples), dtype=np.float64)
    baseband = 2.0 * samples * np.exp(
        -2j * math.pi * config.audio_center_hz * indices / config.sample_rate
    )
    start, metric = _find_training(baseband, config)
    if metric < sync_threshold:
        raise ValueError(f"OFDM training correlation {metric:.3f} is below threshold")
    required = frame_sample_count(payload_symbol_count, config)
    if start + required > len(baseband):
        raise ValueError("Audio ends before the complete OFDM frame")

    second_start = start + config.block_samples
    first_spectrum = np.fft.fft(
        baseband[
            start + config.cyclic_prefix_samples : start + config.block_samples
        ]
    )
    second_spectrum = np.fft.fft(
        baseband[
            second_start
            + config.cyclic_prefix_samples : second_start
            + config.block_samples
        ]
    )
    first_carriers = np.asarray(
        [first_spectrum[index % config.fft_size] for index in config.data_subcarriers]
    )
    second_carriers = np.asarray(
        [second_spectrum[index % config.fft_size] for index in config.data_subcarriers]
    )
    phase_step = float(np.angle(np.vdot(first_carriers, second_carriers)))
    frequency_offset = phase_step * config.sample_rate / (
        2.0 * math.pi * config.block_samples
    )
    frame = baseband[start : start + required].copy()
    frame *= np.exp(
        -2j
        * math.pi
        * frequency_offset
        * np.arange(len(frame), dtype=np.float64)
        / config.sample_rate
    )

    def carrier_values(block_index: int) -> NDArray[np.complex128]:
        offset = block_index * config.block_samples + config.cyclic_prefix_samples
        spectrum = np.fft.fft(frame[offset : offset + config.fft_size])
        return np.asarray(
            [spectrum[index % config.fft_size] for index in config.data_subcarriers],
            dtype=np.complex128,
        )

    expected = _training_values(config)
    training_values = np.mean(
        [carrier_values(index) for index in range(config.training_symbol_count)],
        axis=0,
    )
    channel = training_values / expected
    if np.any(np.abs(channel) <= np.finfo(float).tiny):
        raise ValueError("OFDM training produced a zero channel estimate")
    recovered = np.concatenate(
        [
            carrier_values(index) / channel
            for index in range(
                config.training_symbol_count,
                required // config.block_samples,
            )
        ]
    )[:payload_symbol_count]
    recovered.setflags(write=False)
    return recovered, metric, frequency_offset, start
