"""Offline experimental audio waveform generation and recovery for Aurora."""

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from audio.buffer import AudioBuffer
from dsp.frequency_offset import estimate_frequency_offset
from dsp.preamble import acquisition_symbols
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


@dataclass(frozen=True, slots=True)
class WaveformDiagnostics:
    """Measurements from offline waveform acquisition and recovery."""

    synchronized: bool
    sync_metric: float
    frequency_offset_hz: float
    symbol_start_sample: int


@dataclass(frozen=True, slots=True)
class WaveformResult:
    """Recovered payload symbols and offline receiver diagnostics."""

    symbols: NDArray[np.complex128]
    diagnostics: WaveformDiagnostics


def samples_per_symbol(mode: ModeDefinition = AURORA_ROBUST_MODE) -> int:
    """Return the exact integer audio sampling ratio for a mode."""
    ratio = mode.audio_sample_rate / mode.symbol_rate
    if not ratio.is_integer():
        raise ValueError("Waveform requires an integer samples-per-symbol ratio")
    return int(ratio)


def root_raised_cosine_taps(
    samples_per_symbol_value: int,
    rolloff: float,
    span_symbols: int,
) -> NDArray[np.float64]:
    """Design an energy-normalized root-raised-cosine FIR pulse."""
    if samples_per_symbol_value <= 0:
        raise ValueError("Samples per symbol must be positive")
    if not 0.0 < rolloff <= 1.0:
        raise ValueError("Roll-off must be between zero and one")
    if span_symbols <= 0 or span_symbols % 2:
        raise ValueError("Span must be a positive even symbol count")

    half_length = span_symbols * samples_per_symbol_value // 2
    time = np.arange(-half_length, half_length + 1, dtype=np.float64)
    time /= samples_per_symbol_value
    taps = np.empty_like(time)
    singular = 1.0 / (4.0 * rolloff)
    for index, value in enumerate(time):
        if math.isclose(value, 0.0, abs_tol=1e-12):
            taps[index] = 1.0 + rolloff * (4.0 / math.pi - 1.0)
        elif math.isclose(abs(value), singular, rel_tol=0.0, abs_tol=1e-12):
            angle = math.pi / (4.0 * rolloff)
            taps[index] = rolloff / math.sqrt(2.0) * (
                (1.0 + 2.0 / math.pi) * math.sin(angle)
                + (1.0 - 2.0 / math.pi) * math.cos(angle)
            )
        else:
            numerator = (
                math.sin(math.pi * value * (1.0 - rolloff))
                + 4.0
                * rolloff
                * value
                * math.cos(math.pi * value * (1.0 + rolloff))
            )
            denominator = math.pi * value * (
                1.0 - (4.0 * rolloff * value) ** 2
            )
            taps[index] = numerator / denominator
    taps /= math.sqrt(float(np.sum(taps * taps)))
    taps.setflags(write=False)
    return taps


def _mode_taps(mode: ModeDefinition) -> NDArray[np.float64]:
    return root_raised_cosine_taps(
        samples_per_symbol(mode), mode.pulse_rolloff, mode.pulse_span_symbols
    )


def modulate_audio(
    payload_symbols: ArrayLike,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
    *,
    leading_silence_samples: int = 0,
    frequency_offset_hz: float = 0.0,
) -> AudioBuffer:
    """Pulse-shape BPSK payload symbols into real passband audio samples."""
    payload = np.asarray(payload_symbols, dtype=np.complex128)
    if payload.ndim != 1 or len(payload) == 0:
        raise ValueError("Payload symbols must be a non-empty one-dimensional sequence")
    if np.any(np.abs(payload.imag) > 1e-12) or np.any(
        ~np.isclose(np.abs(payload.real), 1.0)
    ):
        raise ValueError("Experimental waveform accepts normalized BPSK symbols only")
    if leading_silence_samples < 0:
        raise ValueError("Leading silence must not be negative")

    symbols = np.concatenate((acquisition_symbols(), payload))
    ratio = samples_per_symbol(mode)
    impulses = np.zeros(len(symbols) * ratio, dtype=np.complex128)
    impulses[::ratio] = symbols
    shaped = np.convolve(impulses, _mode_taps(mode), mode="full")
    indices = np.arange(len(shaped), dtype=np.float64)
    carrier = mode.audio_carrier_hz + frequency_offset_hz
    passband = np.real(
        shaped * np.exp(2j * math.pi * carrier * indices / mode.audio_sample_rate)
    )
    passband *= 0.5 * math.sqrt(ratio)
    if leading_silence_samples:
        passband = np.pad(passband, (leading_silence_samples, 0))
    if float(np.max(np.abs(passband))) > 1.0:
        raise ValueError("Generated waveform would clip normalized audio")
    return AudioBuffer(passband.astype(np.float32), mode.audio_sample_rate)


def _find_preamble(
    matched: NDArray[np.complex128], mode: ModeDefinition
) -> tuple[int, float]:
    ratio = samples_per_symbol(mode)
    reference = acquisition_symbols().astype(np.complex128)
    reference_energy = float(np.vdot(reference, reference).real)
    best_start = 0
    best_metric = -1.0
    for phase in range(ratio):
        symbols = matched[phase::ratio]
        if len(symbols) < len(reference):
            continue
        correlation = np.correlate(symbols, reference, mode="valid")
        energy = np.convolve(
            np.abs(symbols) ** 2,
            np.ones(len(reference), dtype=np.float64),
            mode="valid",
        )
        metrics = np.abs(correlation) / np.sqrt(
            np.maximum(energy * reference_energy, np.finfo(float).tiny)
        )
        index = int(np.argmax(metrics))
        metric = float(metrics[index])
        if metric > best_metric:
            best_metric = metric
            best_start = phase + index * ratio
    return best_start, best_metric


def demodulate_audio(
    audio: AudioBuffer,
    payload_symbol_count: int,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
    *,
    sync_threshold: float = 0.70,
) -> WaveformResult:
    """Acquire and recover a known-length BPSK payload from offline audio."""
    if audio.channel_count != 1:
        raise ValueError("Experimental waveform receiver requires mono audio")
    if audio.sample_rate != mode.audio_sample_rate:
        raise ValueError("Audio sample rate does not match the waveform mode")
    if payload_symbol_count <= 0:
        raise ValueError("Payload symbol count must be positive")
    samples = np.asarray(audio.samples, dtype=np.float64)
    indices = np.arange(len(samples), dtype=np.float64)
    baseband = 2.0 * samples * np.exp(
        -2j * math.pi * mode.audio_carrier_hz * indices / mode.audio_sample_rate
    )
    matched = np.convolve(baseband, _mode_taps(mode), mode="full")
    start, metric = _find_preamble(matched, mode)
    if metric < sync_threshold:
        raise ValueError(f"Waveform preamble correlation {metric:.3f} is below threshold")

    ratio = samples_per_symbol(mode)
    count = len(acquisition_symbols()) + payload_symbol_count
    recovered = matched[start : start + count * ratio : ratio]
    if len(recovered) != count:
        raise ValueError("Audio ends before the complete payload is available")
    reference = acquisition_symbols().astype(np.complex128)
    received_preamble = recovered[: len(reference)]
    offset = estimate_frequency_offset(
        received_preamble, reference, mode.symbol_rate
    )
    correction = np.exp(
        -2j * math.pi * offset * np.arange(count, dtype=float) / mode.symbol_rate
    )
    corrected = recovered * correction
    gain = np.vdot(reference, corrected[: len(reference)]) / float(len(reference))
    if abs(gain) <= np.finfo(float).tiny:
        raise ValueError("Waveform preamble has zero recovered gain")
    payload = corrected[len(reference) :] / gain
    payload.setflags(write=False)
    return WaveformResult(
        payload,
        WaveformDiagnostics(True, metric, offset, start),
    )


def occupied_bandwidth_hz(
    audio: AudioBuffer,
    *,
    power_fraction: float = 0.99,
) -> float:
    """Return the central positive-frequency interval containing power."""
    if audio.channel_count != 1:
        raise ValueError("Bandwidth measurement requires mono audio")
    if not 0.0 < power_fraction < 1.0:
        raise ValueError("Power fraction must be between zero and one")
    samples = np.asarray(audio.samples, dtype=np.float64)
    spectrum = np.fft.rfft(samples * np.hanning(len(samples)))
    power = np.abs(spectrum) ** 2
    cumulative = np.cumsum(power)
    total = float(cumulative[-1])
    if total <= 0.0:
        return 0.0
    tail = (1.0 - power_fraction) / 2.0
    lower = int(np.searchsorted(cumulative, tail * total))
    upper = int(np.searchsorted(cumulative, (1.0 - tail) * total))
    bin_width = audio.sample_rate / len(samples)
    return (upper - lower) * bin_width
