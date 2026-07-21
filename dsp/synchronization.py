"""Known-sequence synchronization for Aurora baseband samples."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True, slots=True)
class SynchronizationResult:
    """Preamble acquisition location and normalized correlation metric."""

    locked: bool
    sample_index: int
    metric: float


class SynchronizationError(RuntimeError):
    """Raised when receiver synchronization cannot be established."""


def _normalized_correlation(
    samples: np.ndarray, reference: np.ndarray
) -> np.ndarray:
    correlation = np.correlate(samples, reference, mode="valid")
    reference_energy = float(np.vdot(reference, reference).real)
    sample_energy = np.convolve(
        np.abs(samples) ** 2, np.ones(len(reference)), mode="valid"
    )
    denominator = np.sqrt(reference_energy * sample_energy)
    return np.divide(
        np.abs(correlation),
        denominator,
        out=np.zeros_like(denominator, dtype=float),
        where=denominator > 0.0,
    )


def find_preamble(
    samples: ArrayLike, preamble: ArrayLike, threshold: float = 0.75
) -> SynchronizationResult:
    """Locate a known preamble using normalized complex correlation."""
    received = np.asarray(samples, dtype=np.complex128)
    reference = np.asarray(preamble, dtype=np.complex128)
    if received.ndim != 1 or reference.ndim != 1:
        raise ValueError("Synchronization inputs must be one-dimensional")
    if len(reference) == 0 or len(received) < len(reference):
        raise ValueError("Received samples must contain the complete preamble")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Synchronization threshold must be between zero and one")

    coherent_metrics = _normalized_correlation(received, reference)
    received_differential = received[1:] * np.conj(received[:-1])
    reference_differential = reference[1:] * np.conj(reference[:-1])
    differential_metrics = _normalized_correlation(
        received_differential, reference_differential
    )
    metrics = np.maximum(coherent_metrics, differential_metrics)
    sample_index = int(np.argmax(metrics))
    metric = float(metrics[sample_index])
    return SynchronizationResult(metric >= threshold, sample_index, metric)
