"""BPSK symbol mapping for Aurora."""

from collections.abc import Iterable, Sequence
import numpy as np
from numpy.typing import ArrayLike, NDArray


SUPPORTED_MODULATIONS = ("bpsk",)


def _normalized_modulation(modulation: str) -> str:
    normalized = modulation.lower()
    if normalized not in SUPPORTED_MODULATIONS:
        raise ValueError(f"Unsupported modulation: {modulation}")
    return normalized


def _validated_bits(bits: Iterable[int]) -> list[int]:
    result = list(bits)
    if any(bit not in (0, 1) for bit in result):
        raise ValueError("Symbol mapper input must contain only binary values")
    return result


def map_bits(bits: Iterable[int], modulation: str = "bpsk") -> list[complex]:
    """Map binary values to normalized BPSK symbols."""
    source = _validated_bits(bits)
    _normalized_modulation(modulation)
    return [complex(1.0 if bit == 0 else -1.0, 0.0) for bit in source]


def demap_symbols(symbols: Sequence[complex], modulation: str = "bpsk") -> list[int]:
    """Hard-decision demap BPSK symbols to binary values."""
    _normalized_modulation(modulation)
    return [0 if symbol.real >= 0.0 else 1 for symbol in symbols]


def soft_demap_symbols(
    symbols: ArrayLike,
    modulation: str = "bpsk",
    *,
    noise_variance: float = 1.0,
) -> NDArray[np.float64]:
    """Return soft bit likelihoods for BPSK symbols."""
    from dsp.soft_decision import soft_demapping

    return soft_demapping(
        symbols, modulation=modulation, noise_variance=noise_variance
    )
