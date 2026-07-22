"""Receiver diagnostic presentation for the Aurora operator interface."""

import tkinter as tk
from tkinter import ttk

from gui.testing_controller import BenchmarkResult, SimulationDiagnostics


class DiagnosticsPanel(ttk.Frame):
    """Compact diagnostic readout with stable field labels."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=12, style="Aurora.Panel.TFrame")
        self._values: dict[str, ttk.Label] = {}
        fields = (
            ("Sync", "SEARCHING"),
            ("SNR", "-- dB"),
            ("Frequency offset", "-- Hz"),
            ("Timing offset", "--"),
            ("CRC", "WAITING"),
            ("FEC", "IDLE"),
            ("Frames", "0 / 0"),
            ("Success rate", "-- %"),
            ("Channel bit errors", "0"),
        )
        for row, (name, initial) in enumerate(fields):
            ttk.Label(self, text=name, style="Aurora.Muted.TLabel").grid(
                row=row, column=0, sticky="w", pady=3
            )
            value = ttk.Label(self, text=initial, style="Aurora.Value.TLabel")
            value.grid(row=row, column=1, sticky="e", padx=(18, 0), pady=3)
            self._values[name] = value
        self.columnconfigure(1, weight=1)

    def update_diagnostics(self, diagnostics: SimulationDiagnostics) -> None:
        """Update every diagnostic field from one coherent snapshot."""
        self._values["Sync"].configure(
            text="LOCKED" if diagnostics.synchronized else "SEARCHING"
        )
        self._values["SNR"].configure(text=f"{diagnostics.snr_db:.1f} dB")
        self._values["Frequency offset"].configure(
            text=f"{diagnostics.frequency_offset_hz:+.1f} Hz"
        )
        self._values["Timing offset"].configure(
            text=f"{diagnostics.timing_offset:+.3f}"
        )
        self._values["CRC"].configure(text=diagnostics.crc_status)
        self._values["FEC"].configure(text=diagnostics.fec_status)

    def update_benchmark(self, result: BenchmarkResult) -> None:
        """Display aggregate results from a controlled channel benchmark."""
        self._values["Sync"].configure(text="N/A - SYMBOL TEST")
        self._values["SNR"].configure(text=f"{result.snr_db:.1f} dB injected")
        self._values["Frequency offset"].configure(
            text=f"{result.frequency_offset_hz:+.2f} Hz injected"
        )
        self._values["Timing offset"].configure(text="N/A - NO WAVEFORM")
        self._values["CRC"].configure(
            text=f"{result.successful_frames} PASS / {result.failed_frames} FAIL"
        )
        self._values["FEC"].configure(
            text=f"{result.corrected_bit_errors} ERRORS RECOVERED"
        )
        self._values["Frames"].configure(
            text=f"{result.successful_frames} / {result.frame_count}"
        )
        self._values["Success rate"].configure(text=f"{result.success_rate:.1f} %")
        self._values["Channel bit errors"].configure(
            text=str(result.channel_bit_errors)
        )
