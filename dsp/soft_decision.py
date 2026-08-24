"""Soft symbol decisions for Aurora channel decoding."""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from dsp.symbol_mapper import SUPPORTED_MODULATIONS


def soft_demapping(
    symbols: ArrayLike,
    modulation: str = "bpsk",
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

    return 2.0 * received.real / noise_variance
