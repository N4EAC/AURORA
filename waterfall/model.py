"""Bounded waterfall history for Aurora spectrum frames."""

from collections import deque

import numpy as np
from numpy.typing import ArrayLike, NDArray


class WaterfallModel:
    """Store recent spectrum rows and normalize them for display."""

    def __init__(
        self,
        bin_count: int,
        *,
        history_size: int = 128,
        floor_db: float = -120.0,
        ceiling_db: float = 0.0,
    ) -> None:
        if bin_count <= 0 or history_size <= 0:
            raise ValueError("Waterfall dimensions must be positive")
        if floor_db >= ceiling_db:
            raise ValueError("Waterfall floor must be below its ceiling")
        self.bin_count = bin_count
        self.history_size = history_size
        self.floor_db = floor_db
        self.ceiling_db = ceiling_db
        self._rows: deque[NDArray[np.float32]] = deque(maxlen=history_size)

    def add(self, power_db: ArrayLike) -> None:
        """Append one power-spectrum row."""
        row = np.asarray(power_db, dtype=np.float32)
        if row.ndim != 1 or len(row) != self.bin_count:
            raise ValueError("Waterfall row does not match the configured bin count")
        self._rows.append(row.copy())

    @property
    def row_count(self) -> int:
        """Return the current number of stored rows."""
        return len(self._rows)

    def normalized_image(self) -> NDArray[np.uint8]:
        """Return oldest-to-newest rows normalized to unsigned bytes."""
        if not self._rows:
            return np.empty((0, self.bin_count), dtype=np.uint8)
        values = np.stack(self._rows)
        normalized = (values - self.floor_db) / (self.ceiling_db - self.floor_db)
        return np.rint(np.clip(normalized, 0.0, 1.0) * 255.0).astype(np.uint8)
