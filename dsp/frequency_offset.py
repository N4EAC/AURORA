"""Carrier frequency-offset estimation and correction."""

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


def estimate_frequency_offset(
    received_preamble: ArrayLike,
    reference_preamble: ArrayLike,
    sample_rate: float,
) -> float:
    """Estimate frequency offset in hertz from preamble phase slope."""
    received = np.asarray(received_preamble, dtype=np.complex128)
    reference = np.asarray(reference_preamble, dtype=np.complex128)
    if received.ndim != 1 or reference.ndim != 1:
        raise ValueError("Frequency estimator inputs must be one-dimensional")
    if len(received) != len(reference) or len(received) < 2:
        raise ValueError("Received and reference preambles must have equal length")
    if sample_rate <= 0.0:
        raise ValueError("Sample rate must be positive")

    usable = np.abs(reference) > 0.0
    if np.count_nonzero(usable) < 2:
        raise ValueError("Reference preamble has insufficient non-zero samples")
    phase = np.unwrap(np.angle(received[usable] * np.conj(reference[usable])))
    indices = np.arange(len(received), dtype=float)[usable]
    slope = float(np.polyfit(indices, phase, 1)[0])
    return slope * sample_rate / (2.0 * math.pi)


def correct_frequency_offset(
    samples: ArrayLike, frequency_offset: float, sample_rate: float
) -> NDArray[np.complex128]:
    """Remove a frequency offset from complex baseband samples."""
    received = np.asarray(samples, dtype=np.complex128)
    if received.ndim != 1:
        raise ValueError("Frequency correction input must be one-dimensional")
    if sample_rate <= 0.0:
        raise ValueError("Sample rate must be positive")
    indices = np.arange(len(received), dtype=float)
    correction = np.exp(-2j * math.pi * frequency_offset * indices / sample_rate)
    return received * correction
