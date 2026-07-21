"""Tkinter spectrum display for Aurora."""

import tkinter as tk
from tkinter import ttk

import numpy as np

from dsp.spectrum import SpectrumFrame


class SpectrumView(ttk.Frame):
    """Canvas-based spectrum trace with an update-oriented public API."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        floor_db: float = -120.0,
        ceiling_db: float = 0.0,
    ) -> None:
        super().__init__(parent)
        self.floor_db = floor_db
        self.ceiling_db = ceiling_db
        self._frame: SpectrumFrame | None = None
        self.canvas = tk.Canvas(
            self,
            background="#0b1015",
            highlightthickness=1,
            highlightbackground="#2a3540",
            height=180,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda event: self._draw())

    def update_spectrum(self, frame: SpectrumFrame) -> None:
        """Display a newly computed spectrum frame."""
        self._frame = frame
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("spectrum")
        if self._frame is None or len(self._frame.power_db) < 2:
            return
        width = max(self.canvas.winfo_width(), 2)
        height = max(self.canvas.winfo_height(), 2)
        normalized = (self._frame.power_db - self.floor_db) / (
            self.ceiling_db - self.floor_db
        )
        normalized = np.clip(normalized, 0.0, 1.0)
        x_values = np.linspace(0.0, width - 1.0, len(normalized))
        y_values = (1.0 - normalized) * (height - 1.0)
        points = [coordinate for pair in zip(x_values, y_values) for coordinate in pair]
        self.canvas.create_line(
            *points, fill="#52d6c7", width=1, tags="spectrum"
        )
