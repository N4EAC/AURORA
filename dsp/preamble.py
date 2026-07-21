"""Deterministic acquisition sequence for the Aurora receiver."""

import numpy as np
from numpy.typing import NDArray


PREAMBLE_SYMBOL_COUNT = 63


def acquisition_symbols() -> NDArray[np.complex64]:
    """Return the fixed 63-symbol BPSK acquisition sequence."""
    state = 0x7F
    symbols: list[complex] = []
    for _ in range(PREAMBLE_SYMBOL_COUNT):
        bit = state & 1
        symbols.append(complex(1.0 if bit == 0 else -1.0))
        feedback = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) & 0x7F) | feedback
    return np.asarray(symbols, dtype=np.complex64)


def acquisition_preamble(samples_per_symbol: int = 1) -> NDArray[np.complex64]:
    """Return the acquisition sequence at an integer sampling ratio."""
    if samples_per_symbol < 1:
        raise ValueError("Samples per symbol must be positive")
    return np.repeat(acquisition_symbols(), samples_per_symbol)
