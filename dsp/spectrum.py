"""Frequency-spectrum analysis for Aurora displays."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True, slots=True)
class SpectrumFrame:
    """Frequency bins and their normalized power in decibels."""

    frequencies_hz: NDArray[np.float64]
    power_db: NDArray[np.float64]


def compute_spectrum(
    samples: ArrayLike,
    sample_rate: float,
    *,
    fft_size: int = 1_024,
    floor_db: float = -140.0,
) -> SpectrumFrame:
    """Compute a Hann-windowed, normalized spectrum frame."""
    values = np.asarray(samples)
    if values.ndim != 1:
        raise ValueError("Spectrum input must be one-dimensional")
    if sample_rate <= 0.0 or fft_size < 8:
        raise ValueError("Spectrum sample rate and FFT size must be valid")

    segment = np.zeros(fft_size, dtype=values.dtype)
    copied = min(len(values), fft_size)
    if copied:
        segment[-copied:] = values[-copied:]
    window = np.hanning(fft_size)
    normalization = float(np.sum(window))

    if np.iscomplexobj(segment):
        spectrum = np.fft.fftshift(np.fft.fft(segment * window))
        frequencies = np.fft.fftshift(np.fft.fftfreq(fft_size, 1.0 / sample_rate))
    else:
        spectrum = np.fft.rfft(segment * window)
        frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)

    magnitude = np.abs(spectrum) / normalization
    power_db = 20.0 * np.log10(np.maximum(magnitude, 10.0 ** (floor_db / 20.0)))
    return SpectrumFrame(frequencies.astype(np.float64), power_db.astype(np.float64))
