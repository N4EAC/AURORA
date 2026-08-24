"""Tkinter spectrum display for Aurora."""

import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

import numpy as np

from dsp.spectrum import SpectrumFrame
from gui.theme import PALETTE


class SpectrumView(ttk.Frame):
    """Canvas-based spectrum trace with an update-oriented public API."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        floor_db: float = -120.0,
        ceiling_db: float = 0.0,
        minimum_frequency_hz: int = 100,
        maximum_frequency_hz: int = 3_000,
        selected_frequency_hz: int = 1_500,
        selection_changed: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.floor_db = floor_db
        self.ceiling_db = ceiling_db
        self._frame: SpectrumFrame | None = None
        self.minimum_frequency_hz = minimum_frequency_hz
        self.maximum_frequency_hz = maximum_frequency_hz
        self.selected_frequency_hz = selected_frequency_hz
        self.selection_changed = selection_changed
        self.canvas = tk.Canvas(
            self,
            background=PALETTE.field,
            highlightthickness=1,
            highlightbackground=PALETTE.border,
            height=120,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda event: self._draw())
        self.canvas.bind("<Button-1>", self._select_from_pointer)

    def update_spectrum(self, frame: SpectrumFrame) -> None:
        """Display a newly computed spectrum frame."""
        self._frame = frame
        self._draw()

    def set_selected_frequency(self, frequency_hz: int) -> None:
        """Update the shared TX/RX frequency marker."""
        self.selected_frequency_hz = max(
            self.minimum_frequency_hz,
            min(self.maximum_frequency_hz, int(frequency_hz)),
        )
        self._draw()

    def _select_from_pointer(self, event: tk.Event) -> None:
        width = max(self.canvas.winfo_width() - 1, 1)
        fraction = max(0.0, min(1.0, event.x / width))
        frequency = round(
            self.minimum_frequency_hz
            + fraction * (self.maximum_frequency_hz - self.minimum_frequency_hz)
        )
        frequency = round(frequency / 100) * 100
        self.set_selected_frequency(frequency)
        if self.selection_changed is not None:
            self.selection_changed(frequency)

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 2)
        height = max(self.canvas.winfo_height(), 2)
        plot_height = max(height - 18, 2)
        marker_x = (
            (self.selected_frequency_hz - self.minimum_frequency_hz)
            / (self.maximum_frequency_hz - self.minimum_frequency_hz)
            * (width - 1)
        )
        self.canvas.create_line(
            marker_x, 0, marker_x, plot_height, fill=PALETTE.blue, width=2
        )
        self.canvas.create_text(
            marker_x,
            3,
            text=f"TX/RX {self.selected_frequency_hz} Hz",
            fill=PALETTE.blue,
            anchor=tk.N,
            font=("TkDefaultFont", 8),
        )
        for frequency in (100, 500, 1_000, 1_500, 2_000, 2_500, 3_000):
            x_value = (
                (frequency - self.minimum_frequency_hz)
                / (self.maximum_frequency_hz - self.minimum_frequency_hz)
                * (width - 1)
            )
            self.canvas.create_line(
                x_value, plot_height - 3, x_value, plot_height, fill=PALETTE.muted
            )
            self.canvas.create_text(
                x_value,
                height - 2,
                text=str(frequency),
                fill=PALETTE.muted,
                anchor=tk.S,
                font=("TkDefaultFont", 7),
            )
        if self._frame is None or len(self._frame.power_db) < 2:
            return
        visible = (
            (self._frame.frequencies_hz >= self.minimum_frequency_hz)
            & (self._frame.frequencies_hz <= self.maximum_frequency_hz)
        )
        power = self._frame.power_db[visible]
        frequencies = self._frame.frequencies_hz[visible]
        if len(power) < 2:
            return
        normalized = (power - self.floor_db) / (
            self.ceiling_db - self.floor_db
        )
        normalized = np.clip(normalized, 0.0, 1.0)
        x_values = (
            (frequencies - self.minimum_frequency_hz)
            / (self.maximum_frequency_hz - self.minimum_frequency_hz)
            * (width - 1)
        )
        y_values = (1.0 - normalized) * (plot_height - 1.0)
        points = [coordinate for pair in zip(x_values, y_values) for coordinate in pair]
        self.canvas.create_line(
            *points, fill=PALETTE.accent, width=1
        )
