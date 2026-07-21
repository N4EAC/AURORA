"""Soft symbol decisions for Aurora channel decoding."""

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from dsp.symbol_mapper import SUPPORTED_MODULATIONS


def soft_demapping(
    symbols: ArrayLike,
    modulation: str = "qpsk",
    *,
    noise_variance: float = 1.0,
) -> NDArray[np.float64]:
    """Return log-likelihood ratios where positive values favor bit zero."""
    received = np.asarray(symbols, dtype=np.complex128)
    if received.ndim != 1:
        raise ValueError("Soft demapper input must be one-dimensional")
    modulation = modulation.lower()
    if modulation not in SUPPORTED_MODULATIONS:
        raise ValueError(f"Unsupported modulation: {modulation}")
    if noise_variance <= 0.0:
        raise ValueError("Noise variance must be positive")

    if modulation == "bpsk":
        return 2.0 * received.real / noise_variance

    scale = 2.0 * math.sqrt(2.0) / noise_variance
    likelihoods = np.empty(len(received) * 2, dtype=np.float64)
    likelihoods[0::2] = scale * received.real
    likelihoods[1::2] = scale * received.imag
    return likelihoods
