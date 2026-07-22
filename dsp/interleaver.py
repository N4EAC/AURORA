"""Deterministic block interleaving for Aurora coded values."""

from collections.abc import Sequence
from typing import TypeVar


Value = TypeVar("Value")


def _column_major_indices(length: int, columns: int) -> list[int]:
    if columns <= 0:
        raise ValueError("Interleaver columns must be positive")
    if length < 0:
        raise ValueError("Interleaver length must not be negative")
    rows = (length + columns - 1) // columns
    return [
        row * columns + column
        for column in range(columns)
        for row in range(rows)
        if row * columns + column < length
    ]


def block_interleave(values: Sequence[Value], columns: int = 16) -> list[Value]:
    """Write values by rows and return them read by columns without padding."""
    source = list(values)
    return [source[index] for index in _column_major_indices(len(source), columns)]


def block_deinterleave(values: Sequence[Value], columns: int = 16) -> list[Value]:
    """Invert :func:`block_interleave` for hard bits or soft likelihoods."""
    source = list(values)
    indices = _column_major_indices(len(source), columns)
    restored = source.copy()
    for value, original_index in zip(source, indices, strict=True):
        restored[original_index] = value
    return restored
