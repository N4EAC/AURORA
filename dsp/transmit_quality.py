"""Measurable audio-linearity limits for Aurora radio transmissions."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from audio.buffer import AudioBuffer


@dataclass(frozen=True, slots=True)
class TransmitQualityLimits:
    """Conservative normalized-audio limits before a radio output device."""

    maximum_peak: float = 0.50
    maximum_active_rms: float = 0.15
    minimum_crest_factor: float = 3.0
    maximum_crest_factor: float = 6.0
    maximum_dc_offset: float = 0.005
    clipping_threshold: float = 0.98


@dataclass(frozen=True, slots=True)
class TransmitQualityReport:
    """Measured transmitter-audio properties and compliance result."""

    peak: float
    active_rms: float
    crest_factor: float
    dc_offset: float
    clipped_samples: int
    compliant: bool
    violations: tuple[str, ...]


DEFAULT_TRANSMIT_LIMITS = TransmitQualityLimits()


def analyze_transmit_audio(
    audio: AudioBuffer,
    limits: TransmitQualityLimits = DEFAULT_TRANSMIT_LIMITS,
) -> TransmitQualityReport:
    """Measure normalized transmit audio against Aurora's bounded limits."""
    samples = np.asarray(audio.samples, dtype=np.float64).reshape(-1)
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError("Transmit audio must contain finite samples")
    active = samples[np.abs(samples) > 1e-5]
    if not len(active):
        raise ValueError("Transmit audio contains no active waveform")
    peak = float(np.max(np.abs(active)))
    rms = math.sqrt(float(np.mean(active * active)))
    crest = peak / max(rms, np.finfo(float).tiny)
    dc = abs(float(np.mean(active)))
    clipped = int(np.count_nonzero(np.abs(samples) >= limits.clipping_threshold))
    violations = []
    if peak > limits.maximum_peak:
        violations.append("peak exceeds normalized audio limit")
    if rms > limits.maximum_active_rms:
        violations.append("active RMS exceeds normalized audio limit")
    if not limits.minimum_crest_factor <= crest <= limits.maximum_crest_factor:
        violations.append("crest factor is outside the OFDM linearity range")
    if dc > limits.maximum_dc_offset:
        violations.append("DC offset exceeds normalized audio limit")
    if clipped:
        violations.append("audio contains clipped samples")
    return TransmitQualityReport(
        peak,
        rms,
        crest,
        dc,
        clipped,
        not violations,
        tuple(violations),
    )


def validate_transmit_audio(
    audio: AudioBuffer,
    limits: TransmitQualityLimits = DEFAULT_TRANSMIT_LIMITS,
) -> TransmitQualityReport:
    """Return metrics or reject audio that could overdrive a linear transmitter."""
    report = analyze_transmit_audio(audio, limits)
    if not report.compliant:
        raise ValueError("; ".join(report.violations))
    return report
