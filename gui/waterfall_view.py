"""Tkinter waterfall display for Aurora."""

import tkinter as tk
from tkinter import ttk

import numpy as np

from waterfall.model import WaterfallModel


def _color(value: int) -> str:
    normalized = value / 255.0
    red = int(255.0 * max(0.0, (normalized - 0.55) / 0.45))
    green = int(255.0 * min(1.0, normalized / 0.65))
    blue = int(255.0 * min(1.0, normalized * 2.2))
    return f"#{red:02x}{green:02x}{blue:02x}"


class WaterfallView(ttk.Frame):
    """PhotoImage-based waterfall with a spectrum-row update API."""

    def __init__(self, parent: tk.Misc, model: WaterfallModel) -> None:
        super().__init__(parent)
        self.model = model
        self._image: tk.PhotoImage | None = None
        self.canvas = tk.Canvas(
            self,
            background="#0b1015",
            highlightthickness=1,
            highlightbackground="#2a3540",
            height=model.history_size,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def add_spectrum(self, power_db: np.ndarray) -> None:
        """Append and render one waterfall spectrum row."""
        self.model.add(power_db)
        self._render()

    def _render(self) -> None:
        values = self.model.normalized_image()
        if values.size == 0:
            return
        rows = ["{" + " ".join(_color(int(value)) for value in row) + "}" for row in values]
        image = tk.PhotoImage(width=values.shape[1], height=values.shape[0])
        image.put(" ".join(rows))
        self._image = image
        self.canvas.delete("waterfall")
        self.canvas.create_image(0, 0, image=image, anchor=tk.NW, tags="waterfall")
