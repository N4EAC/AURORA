"""BPSK and QPSK symbol mapping for Aurora."""

from collections.abc import Iterable, Sequence
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


SUPPORTED_MODULATIONS = ("bpsk", "qpsk")
QPSK_SCALE = 1.0 / math.sqrt(2.0)


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


def map_bits(bits: Iterable[int], modulation: str = "qpsk") -> list[complex]:
    """Map binary values to normalized BPSK or Gray-coded QPSK symbols."""
    source = _validated_bits(bits)
    modulation = _normalized_modulation(modulation)
    if modulation == "bpsk":
        return [complex(1.0 if bit == 0 else -1.0, 0.0) for bit in source]
    if len(source) % 2:
        raise ValueError("QPSK mapping requires an even number of bits")

    return [
        complex(
            QPSK_SCALE if source[index] == 0 else -QPSK_SCALE,
            QPSK_SCALE if source[index + 1] == 0 else -QPSK_SCALE,
        )
        for index in range(0, len(source), 2)
    ]


def demap_symbols(
    symbols: Sequence[complex], modulation: str = "qpsk"
) -> list[int]:
    """Hard-decision demap BPSK or QPSK symbols to binary values."""
    modulation = _normalized_modulation(modulation)
    bits: list[int] = []
    for symbol in symbols:
        if modulation == "bpsk":
            bits.append(0 if symbol.real >= 0.0 else 1)
        else:
            bits.extend((0 if symbol.real >= 0.0 else 1, 0 if symbol.imag >= 0.0 else 1))
    return bits


def soft_demap_symbols(
    symbols: ArrayLike,
    modulation: str = "qpsk",
    *,
    noise_variance: float = 1.0,
) -> NDArray[np.float64]:
    """Return soft bit likelihoods for BPSK or QPSK symbols."""
    from dsp.soft_decision import soft_demapping

    return soft_demapping(
        symbols, modulation=modulation, noise_variance=noise_variance
    )
