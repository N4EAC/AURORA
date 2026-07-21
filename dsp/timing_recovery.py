"""Symbol timing recovery for Aurora complex baseband signals."""

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True, slots=True)
class TimingRecoveryResult:
    """Recovered symbols and timing-loop diagnostic values."""

    symbols: NDArray[np.complex128]
    mean_error: float
    final_fractional_offset: float


def _interpolate(samples: NDArray[np.complex128], position: float) -> complex:
    index = int(math.floor(position))
    fraction = position - index
    return samples[index] * (1.0 - fraction) + samples[index + 1] * fraction


def gardner_timing_recovery(
    samples: ArrayLike,
    samples_per_symbol: float,
    *,
    loop_gain: float = 0.02,
    initial_offset: float = 0.0,
) -> TimingRecoveryResult:
    """Recover symbols with a first-order Gardner timing loop."""
    received = np.asarray(samples, dtype=np.complex128)
    if received.ndim != 1:
        raise ValueError("Timing recovery input must be one-dimensional")
    if samples_per_symbol < 2.0:
        raise ValueError("Gardner recovery requires at least two samples per symbol")
    if not 0.0 <= initial_offset < samples_per_symbol:
        raise ValueError("Initial timing offset must be within one symbol")
    if loop_gain <= 0.0:
        raise ValueError("Timing loop gain must be positive")
    if len(received) < math.ceil(samples_per_symbol * 2.0) + 2:
        raise ValueError("Timing recovery input is too short")

    position = initial_offset
    previous = _interpolate(received, position)
    recovered = [previous]
    errors: list[float] = []
    position += samples_per_symbol

    while position < len(received) - 1:
        current = _interpolate(received, position)
        midpoint = _interpolate(received, position - samples_per_symbol / 2.0)
        error = float(np.real((previous - current) * np.conj(midpoint)))
        errors.append(error)
        recovered.append(current)
        previous = current
        position += samples_per_symbol + loop_gain * error

    fractional_offset = position % samples_per_symbol
    return TimingRecoveryResult(
        np.asarray(recovered, dtype=np.complex128),
        float(np.mean(errors)) if errors else 0.0,
        float(fractional_offset),
    )
