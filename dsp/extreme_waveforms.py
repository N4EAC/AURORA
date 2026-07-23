"""Offline acquisition waveforms for Aurora extreme-mode research."""

from dataclasses import dataclass, replace
from functools import lru_cache
import math

import numpy as np
from numpy.typing import NDArray

from audio.buffer import AudioBuffer
from dsp.waveform import root_raised_cosine_taps


EXTREME_SAMPLE_RATE = 12_000
EXTREME_SYMBOL_RATE = 7.8125
EXTREME_CARRIER_HZ = 1_500.0
EXTREME_SAMPLES_PER_SYMBOL = 1_536
EXTREME_PREAMBLE_SYMBOLS = 127
SUPPORTED_EXTREME_MODULATIONS = ("bpsk", "4gfsk")


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    """Best sequence acquisition candidate from one offline audio buffer."""

    sample_index: int
    refined_sample_index: float
    frequency_offset_hz: float
    clock_error_ppm: float
    normalized_metric: float
    peak_to_median: float
    peak_curvature: float
    clock_metric_margin: float


def _lfsr_bits(count: int) -> NDArray[np.int8]:
    state = 0x7F
    bits = np.empty(count, dtype=np.int8)
    for index in range(count):
        bits[index] = state & 1
        feedback = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) & 0x7F) | feedback
    return bits


def extreme_bpsk_preamble() -> NDArray[np.complex128]:
    """Return the fixed 127-symbol BPSK research acquisition sequence."""
    return np.where(_lfsr_bits(EXTREME_PREAMBLE_SYMBOLS) == 0, 1.0, -1.0).astype(
        np.complex128
    )


def extreme_4gfsk_preamble() -> NDArray[np.int8]:
    """Return deterministic four-tone indices for research acquisition."""
    bits = _lfsr_bits(EXTREME_PREAMBLE_SYMBOLS * 2)
    return (2 * bits[0::2] + bits[1::2]).astype(np.int8)


@lru_cache(maxsize=1)
def _bpsk_baseband() -> NDArray[np.complex128]:
    symbols = extreme_bpsk_preamble()
    impulses = np.zeros(len(symbols) * EXTREME_SAMPLES_PER_SYMBOL, dtype=np.complex128)
    impulses[::EXTREME_SAMPLES_PER_SYMBOL] = symbols
    taps = root_raised_cosine_taps(EXTREME_SAMPLES_PER_SYMBOL, 0.35, 4)
    baseband = np.convolve(impulses, taps, mode="full") * math.sqrt(
        EXTREME_SAMPLES_PER_SYMBOL
    )
    baseband.setflags(write=False)
    return baseband


def _gaussian_kernel(bt: float = 0.5, span_symbols: int = 4) -> NDArray[np.float64]:
    half = span_symbols * EXTREME_SAMPLES_PER_SYMBOL // 2
    indices = np.arange(-half, half + 1, dtype=np.float64)
    sigma = EXTREME_SAMPLES_PER_SYMBOL * math.sqrt(math.log(2.0)) / (2.0 * math.pi * bt)
    kernel = np.exp(-0.5 * (indices / sigma) ** 2)
    kernel /= float(np.sum(kernel))
    return kernel


@lru_cache(maxsize=1)
def _gfsk_baseband() -> NDArray[np.complex128]:
    tones = extreme_4gfsk_preamble()
    deviations = (tones.astype(np.float64) - 1.5) * EXTREME_SYMBOL_RATE
    instantaneous = np.repeat(deviations, EXTREME_SAMPLES_PER_SYMBOL)
    padded = np.pad(instantaneous, (2 * EXTREME_SAMPLES_PER_SYMBOL,) * 2, mode="edge")
    smoothed = np.convolve(padded, _gaussian_kernel(), mode="same")
    phase = 2.0 * math.pi * np.cumsum(smoothed) / EXTREME_SAMPLE_RATE
    baseband = np.exp(1j * phase)
    baseband.setflags(write=False)
    return baseband


def acquisition_baseband(modulation: str) -> NDArray[np.complex128]:
    """Return the complex research preamble waveform for a candidate."""
    normalized = modulation.lower()
    if normalized == "bpsk":
        return _bpsk_baseband()
    if normalized == "4gfsk":
        return _gfsk_baseband()
    raise ValueError(f"Unsupported extreme modulation: {modulation}")


@lru_cache(maxsize=64)
def _clock_adjusted_template(
    modulation: str, clock_error_ppm: float
) -> NDArray[np.complex128]:
    template = acquisition_baseband(modulation)
    if clock_error_ppm == 0.0:
        return template
    indices = np.arange(len(template), dtype=np.float64)
    source_positions = indices * (1.0 + clock_error_ppm * 1e-6)
    real = np.interp(source_positions, indices, template.real, left=0.0, right=0.0)
    imaginary = np.interp(
        source_positions, indices, template.imag, left=0.0, right=0.0
    )
    adjusted = real + 1j * imaginary
    adjusted.setflags(write=False)
    return adjusted


def generate_acquisition_audio(
    modulation: str,
    *,
    leading_silence_samples: int = 731,
    trailing_silence_samples: int | None = None,
    frequency_offset_hz: float = 0.0,
) -> AudioBuffer:
    """Generate one real passband acquisition waveform without payload data."""
    if leading_silence_samples < 0:
        raise ValueError("Leading silence must not be negative")
    baseband = acquisition_baseband(modulation)
    if trailing_silence_samples is None:
        trailing_silence_samples = len(baseband)
    if trailing_silence_samples < 0:
        raise ValueError("Trailing silence must not be negative")
    indices = np.arange(len(baseband), dtype=np.float64)
    carrier = EXTREME_CARRIER_HZ + frequency_offset_hz
    audio = 0.45 * np.real(
        baseband * np.exp(2j * math.pi * carrier * indices / EXTREME_SAMPLE_RATE)
    )
    peak = float(np.max(np.abs(audio)))
    if peak > 0.95:
        audio *= 0.95 / peak
    audio = np.pad(audio, (leading_silence_samples, trailing_silence_samples))
    return AudioBuffer(audio.astype(np.float32), EXTREME_SAMPLE_RATE)


def _fft_valid_correlation(
    samples: NDArray[np.complex128], template: NDArray[np.complex128]
) -> NDArray[np.complex128]:
    full_length = len(samples) + len(template) - 1
    fft_length = 1 << (full_length - 1).bit_length()
    correlation = np.fft.ifft(
        np.fft.fft(samples, fft_length)
        * np.fft.fft(np.conj(template[::-1]), fft_length)
    )[:full_length]
    return correlation[len(template) - 1 : len(samples)]


def _refine_peak(values: NDArray[np.float64], index: int) -> tuple[float, float]:
    """Return parabolic peak offset and normalized local curvature."""
    if index == 0 or index == len(values) - 1:
        return float(index), 0.0
    left, center, right = values[index - 1 : index + 2]
    denominator = left - 2.0 * center + right
    if denominator >= 0.0 or center <= 0.0:
        return float(index), 0.0
    offset = 0.5 * (left - right) / denominator
    offset = float(np.clip(offset, -1.0, 1.0))
    curvature = float((2.0 * center - left - right) / center)
    return index + offset, curvature


def search_acquisition(
    audio: AudioBuffer,
    modulation: str,
    *,
    frequency_search_hz: tuple[float, ...] = (-1.0, -0.5, 0.0, 0.5, 1.0),
    clock_search_ppm: tuple[float, ...] = (0.0,),
) -> AcquisitionResult:
    """Search time and frequency using phase-invariant sequence correlation."""
    if audio.channel_count != 1 or audio.sample_rate != EXTREME_SAMPLE_RATE:
        raise ValueError("Extreme acquisition requires mono 12 kHz audio")
    if not frequency_search_hz:
        raise ValueError("Frequency search grid must not be empty")
    if not clock_search_ppm:
        raise ValueError("Clock search grid must not be empty")
    real_samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(real_samples), dtype=np.float64)
    baseband = 2.0 * real_samples * np.exp(
        -2j * math.pi * EXTREME_CARRIER_HZ * indices / EXTREME_SAMPLE_RATE
    )
    sample_power = np.abs(baseband) ** 2
    cumulative = np.concatenate(([0.0], np.cumsum(sample_power)))

    best: AcquisitionResult | None = None
    clock_metrics: dict[float, float] = {}
    for clock_error_ppm in clock_search_ppm:
        template = _clock_adjusted_template(modulation, clock_error_ppm)
        template_energy = float(np.vdot(template, template).real)
        window_energy = cumulative[len(template) :] - cumulative[: -len(template)]
        denominator = np.sqrt(
            np.maximum(window_energy * template_energy, np.finfo(float).tiny)
        )
        clock_peak = 0.0
        for offset in frequency_search_hz:
            clock_carrier_shift_hz = (
                EXTREME_CARRIER_HZ * clock_error_ppm * 1e-6
            )
            shifted = baseband * np.exp(
                -2j
                * math.pi
                * (offset + clock_carrier_shift_hz)
                * indices
                / EXTREME_SAMPLE_RATE
            )
            correlation = np.abs(_fft_valid_correlation(shifted, template))
            metrics = correlation / denominator
            peak_index = int(np.argmax(correlation))
            refined_index, curvature = _refine_peak(correlation, peak_index)
            peak = float(metrics[peak_index])
            median = float(np.median(metrics))
            result = AcquisitionResult(
                peak_index,
                refined_index,
                offset,
                clock_error_ppm,
                peak,
                peak / max(median, np.finfo(float).tiny),
                curvature,
                0.0,
            )
            clock_peak = max(clock_peak, peak)
            if best is None or result.normalized_metric > best.normalized_metric:
                best = result
        clock_metrics[clock_error_ppm] = clock_peak
    if best is None:
        raise ValueError("Acquisition search produced no candidates")
    ranked_clock_metrics = sorted(clock_metrics.values(), reverse=True)
    margin = (
        ranked_clock_metrics[0] - ranked_clock_metrics[1]
        if len(ranked_clock_metrics) > 1
        else ranked_clock_metrics[0]
    )
    return replace(best, clock_metric_margin=float(margin))
