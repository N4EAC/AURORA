"""Main Tkinter application window for Aurora."""

import tkinter as tk
from tkinter import ttk

from config import AppSettings, SETTINGS
from dsp.spectrum import SpectrumFrame
from gui.spectrum_view import SpectrumView
from gui.waterfall_view import WaterfallView
from waterfall.model import WaterfallModel

import numpy as np


def create_application(settings: AppSettings = SETTINGS) -> tk.Tk:
    """Create and configure the main Aurora application window."""
    root = tk.Tk()
    root.title(settings.window_title)
    root.geometry(settings.window_geometry)
    root.minsize(settings.minimum_width, settings.minimum_height)
    root.configure(background=settings.background)

    style = ttk.Style(root)
    style.configure("Aurora.TFrame", background=settings.background)
    style.configure(
        "Aurora.Title.TLabel",
        background=settings.background,
        foreground=settings.foreground,
        font=("Segoe UI", 24, "bold"),
    )
    style.configure(
        "Aurora.Status.TLabel",
        background=settings.background,
        foreground=settings.muted_foreground,
        font=("Segoe UI", 11),
    )

    content = ttk.Frame(root, padding=32, style="Aurora.TFrame")
    content.pack(fill=tk.BOTH, expand=True)

    ttk.Label(content, text="Aurora", style="Aurora.Title.TLabel").pack()
    ttk.Label(
        content,
        text="HF digital modem — initial development",
        style="Aurora.Status.TLabel",
    ).pack(pady=(8, 0))

    displays = ttk.Frame(content, style="Aurora.TFrame")
    displays.pack(fill=tk.BOTH, expand=True, pady=(28, 0))
    displays.columnconfigure(0, weight=1)
    displays.columnconfigure(1, weight=1)
    displays.rowconfigure(0, weight=1)

    spectrum = SpectrumView(
        displays,
        floor_db=settings.spectrum_floor_db,
        ceiling_db=settings.spectrum_ceiling_db,
    )
    spectrum.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    waterfall_model = WaterfallModel(
        settings.spectrum_fft_size // 2 + 1,
        history_size=settings.waterfall_history_size,
        floor_db=settings.spectrum_floor_db,
        ceiling_db=settings.spectrum_ceiling_db,
    )
    waterfall = WaterfallView(displays, waterfall_model)
    waterfall.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    empty_power = np.full(
        settings.spectrum_fft_size // 2 + 1,
        settings.spectrum_floor_db,
        dtype=float,
    )
    empty_frequencies = np.linspace(
        0.0,
        settings.audio_sample_rate / 2.0,
        len(empty_power),
    )
    spectrum.update_spectrum(SpectrumFrame(empty_frequencies, empty_power))
    waterfall.add_spectrum(empty_power)

    return root


def run() -> None:
    """Start the Aurora desktop application."""
    application = create_application()
    application.mainloop()
