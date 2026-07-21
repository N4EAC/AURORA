"""Complex-baseband receiver front end for Aurora."""

from dataclasses import dataclass, field
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from dsp.frequency_offset import correct_frequency_offset, estimate_frequency_offset
from dsp.preamble import acquisition_preamble
from dsp.synchronization import SynchronizationError, find_preamble
from dsp.timing_recovery import gardner_timing_recovery


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    """Sampling and loop settings for the Aurora receiver front end."""

    sample_rate: float = 12_000.0
    symbol_rate: float = 3_000.0
    sync_threshold: float = 0.75
    timing_loop_gain: float = 0.02
    preamble: NDArray[np.complex64] = field(
        default_factory=lambda: acquisition_preamble(4)
    )

    def __post_init__(self) -> None:
        if self.sample_rate <= 0.0 or self.symbol_rate <= 0.0:
            raise ValueError("Receiver sample and symbol rates must be positive")
        if self.sample_rate / self.symbol_rate < 2.0:
            raise ValueError("Receiver timing recovery requires at least two samples per symbol")
        preamble = np.asarray(self.preamble, dtype=np.complex64).copy()
        if preamble.ndim != 1 or len(preamble) < 2:
            raise ValueError("Receiver preamble must be a one-dimensional sequence")
        preamble.setflags(write=False)
        object.__setattr__(self, "preamble", preamble)


@dataclass(frozen=True, slots=True)
class ReceiverDiagnostics:
    """Measurements produced during receiver acquisition and recovery."""

    synchronized: bool
    sync_metric: float
    frequency_offset_hz: float
    timing_error: float
    timing_offset: float
    snr_db: float


@dataclass(frozen=True, slots=True)
class ReceiverResult:
    """Recovered symbols and their receiver diagnostics."""

    symbols: NDArray[np.complex128]
    diagnostics: ReceiverDiagnostics


def _estimate_preamble_snr(
    received: NDArray[np.complex128], reference: NDArray[np.complex64]
) -> float:
    reference_energy = float(np.vdot(reference, reference).real)
    gain = np.vdot(reference, received) / reference_energy
    signal = gain * reference
    noise = received - signal
    signal_power = float(np.mean(np.abs(signal) ** 2))
    noise_power = float(np.mean(np.abs(noise) ** 2))
    if noise_power == 0.0:
        return math.inf
    return 10.0 * math.log10(signal_power / noise_power)


class AuroraReceiver:
    """Acquire and correct a stream of complex Aurora baseband samples."""

    def __init__(self, config: ReceiverConfig | None = None) -> None:
        self.config = config or ReceiverConfig()

    def process(self, samples: ArrayLike) -> ReceiverResult:
        """Synchronize, frequency-correct, and timing-recover baseband samples."""
        received = np.asarray(samples, dtype=np.complex128)
        sync = find_preamble(
            received, self.config.preamble, self.config.sync_threshold
        )
        if not sync.locked:
            raise SynchronizationError(
                f"Preamble correlation {sync.metric:.3f} is below threshold"
            )

        aligned = received[sync.sample_index :]
        preamble_size = len(self.config.preamble)
        received_preamble = aligned[:preamble_size]
        offset = estimate_frequency_offset(
            received_preamble, self.config.preamble, self.config.sample_rate
        )
        corrected = correct_frequency_offset(
            aligned, offset, self.config.sample_rate
        )
        snr_db = _estimate_preamble_snr(
            corrected[:preamble_size], self.config.preamble
        )

        payload = corrected[preamble_size:]
        timing = gardner_timing_recovery(
            payload,
            self.config.sample_rate / self.config.symbol_rate,
            loop_gain=self.config.timing_loop_gain,
        )
        diagnostics = ReceiverDiagnostics(
            synchronized=True,
            sync_metric=sync.metric,
            frequency_offset_hz=offset,
            timing_error=timing.mean_error,
            timing_offset=timing.final_fractional_offset,
            snr_db=snr_db,
        )
        return ReceiverResult(timing.symbols, diagnostics)
