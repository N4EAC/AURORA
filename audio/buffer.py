"""In-memory audio sample representation for Aurora."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """Immutable floating-point audio samples and their sample rate."""

    samples: NDArray[np.float32]
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("Sample rate must be positive")

        samples = np.asarray(self.samples, dtype=np.float32)
        if samples.ndim not in (1, 2):
            raise ValueError("Audio samples must be mono or frame-by-channel data")
        if samples.ndim == 2 and samples.shape[1] == 0:
            raise ValueError("Audio data must contain at least one channel")
        if not np.isfinite(samples).all():
            raise ValueError("Audio samples must contain only finite values")

        samples = samples.copy()
        samples.setflags(write=False)
        object.__setattr__(self, "samples", samples)

    @property
    def frame_count(self) -> int:
        """Return the number of sample frames."""
        return len(self.samples)

    @property
    def channel_count(self) -> int:
        """Return the number of audio channels."""
        return 1 if self.samples.ndim == 1 else self.samples.shape[1]

    @property
    def duration_seconds(self) -> float:
        """Return the buffer duration in seconds."""
        return self.frame_count / self.sample_rate
