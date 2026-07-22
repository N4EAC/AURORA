"""Main Tkinter application window for Aurora."""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from config import AppSettings, SETTINGS
from dsp.spectrum import compute_spectrum
from gui.diagnostics_panel import DiagnosticsPanel
from gui.spectrum_view import SpectrumView
from gui.testing_controller import (
    CHANNEL_IMPAIRMENT_PROFILES,
    CHANNEL_PRESETS,
    BenchmarkResult,
    RobustnessSweepResult,
    SweepConfig,
    TestingController,
)
from gui.waterfall_view import WaterfallView
from modem import AURORA_ROBUST_MODE
from waterfall.model import WaterfallModel
from util.session_debug_log import SessionDebugLog


APPLICATION_VERSION = "0.1.0-dev"


def _configure_styles(root: tk.Tk, settings: AppSettings) -> None:
    style = ttk.Style(root)
    style.configure("Aurora.TFrame", background=settings.background)
    style.configure("Aurora.Panel.TFrame", background="#20262e")
    style.configure(
        "Aurora.Title.TLabel",
        background=settings.background,
        foreground=settings.foreground,
        font=("Segoe UI", 22, "bold"),
    )
    style.configure(
        "Aurora.Status.TLabel",
        background=settings.background,
        foreground=settings.muted_foreground,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Aurora.Section.TLabel",
        background="#20262e",
        foreground=settings.foreground,
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "Aurora.Muted.TLabel",
        background="#20262e",
        foreground=settings.muted_foreground,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Aurora.Value.TLabel",
        background="#20262e",
        foreground="#52d6c7",
        font=("Consolas", 9, "bold"),
    )
    style.configure(
        "Aurora.Warning.TLabel",
        background="#392d17",
        foreground="#ffc857",
        padding=(10, 5),
        font=("Segoe UI", 9, "bold"),
    )


def _append_history(history: tk.Text, line: str, tag: str = "info") -> None:
    history.configure(state=tk.NORMAL)
    history.insert(tk.END, line + "\n", tag)
    history.see(tk.END)
    history.configure(state=tk.DISABLED)


def _show_channel_results(result_tabs: ttk.Notebook, benchmark_tab: ttk.Frame) -> None:
    """Reveal the channel-results workspace without requiring a completed test."""
    result_tabs.select(benchmark_tab)
    result_tabs.focus_set()


def create_application(settings: AppSettings = SETTINGS) -> tk.Tk:
    """Create the simulation-only Aurora operator application."""
    root = tk.Tk()
    root.title(settings.window_title)
    root.geometry(settings.window_geometry)
    root.minsize(900, 720)
    root.configure(background=settings.background)
    _configure_styles(root, settings)
    session_log = SessionDebugLog(settings.log_directory, APPLICATION_VERSION)

    controller = TestingController(
        settings.audio_sample_rate, settings.audio_block_size
    )
    content = ttk.Frame(root, padding=18, style="Aurora.TFrame")
    content.pack(fill=tk.BOTH, expand=True)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(1, weight=1)

    header = ttk.Frame(content, style="Aurora.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
    ttk.Label(header, text="Aurora", style="Aurora.Title.TLabel").pack(side=tk.LEFT)
    ttk.Label(
        header,
        text="SIMULATION - NO RADIO",
        style="Aurora.Warning.TLabel",
    ).pack(side=tk.RIGHT)

    sidebar = ttk.Frame(content, padding=14, style="Aurora.Panel.TFrame")
    sidebar.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
    ttk.Label(sidebar, text="LOCAL TEST", style="Aurora.Section.TLabel").pack(
        anchor=tk.W
    )
    ttk.Label(
        sidebar,
        text="Exercises Aurora framing, FEC, mapping, soft decoding, and CRC locally.",
        style="Aurora.Muted.TLabel",
        wraplength=215,
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(6, 12))

    ttk.Label(sidebar, text="Modulation", style="Aurora.Muted.TLabel").pack(
        anchor=tk.W
    )
    modulation = tk.StringVar(value="QPSK")
    ttk.Combobox(
        sidebar,
        textvariable=modulation,
        values=("QPSK", "BPSK"),
        state="readonly",
        width=18,
    ).pack(fill=tk.X, pady=(4, 12))

    ttk.Label(sidebar, text="Channel preset", style="Aurora.Muted.TLabel").pack(
        anchor=tk.W
    )
    preset_name = tk.StringVar(value="Moderate HF")
    preset_box = ttk.Combobox(
        sidebar,
        textvariable=preset_name,
        values=tuple(CHANNEL_PRESETS),
        state="readonly",
        width=18,
    )
    preset_box.pack(fill=tk.X, pady=(4, 8))

    channel_fields = ttk.Frame(sidebar, style="Aurora.Panel.TFrame")
    channel_fields.pack(fill=tk.X, pady=(0, 10))
    channel_fields.columnconfigure(1, weight=1)
    snr_db = tk.DoubleVar(value=CHANNEL_PRESETS["Moderate HF"].snr_db)
    frequency_offset = tk.DoubleVar(
        value=CHANNEL_PRESETS["Moderate HF"].frequency_offset_hz
    )
    frame_count = tk.IntVar(value=10)
    for row, (label, variable, start, end, increment) in enumerate(
        (
            ("SNR dB", snr_db, -10.0, 40.0, 1.0),
            ("Offset Hz", frequency_offset, -20.0, 20.0, 0.05),
            ("Frames", frame_count, 1, 1_000, 1),
        )
    ):
        ttk.Label(
            channel_fields, text=label, style="Aurora.Muted.TLabel"
        ).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            channel_fields,
            textvariable=variable,
            from_=start,
            to=end,
            increment=increment,
            width=10,
        ).grid(row=row, column=1, sticky="e", pady=2)

    run_channel_button = ttk.Button(sidebar, text="RUN CHANNEL TEST")
    run_channel_button.pack(fill=tk.X, pady=(0, 6))
    run_hundred_button = ttk.Button(sidebar, text="RUN 100 FRAMES")
    run_hundred_button.pack(fill=tk.X, pady=(0, 6))
    show_results_button = ttk.Button(sidebar, text="OPEN CHANNEL RESULTS")
    show_results_button.pack(fill=tk.X, pady=(0, 3))
    ttk.Label(
        sidebar,
        text="Available before running a test",
        style="Aurora.Muted.TLabel",
    ).pack(anchor=tk.W, pady=(0, 10))

    simulation_button = ttk.Button(sidebar, text="START SYNTHETIC SIGNAL")
    simulation_button.pack(fill=tk.X, pady=(0, 16))
    ttk.Separator(sidebar).pack(fill=tk.X, pady=(0, 12))
    ttk.Label(sidebar, text="DIAGNOSTICS", style="Aurora.Section.TLabel").pack(
        anchor=tk.W, pady=(0, 6)
    )
    diagnostics = DiagnosticsPanel(sidebar)
    diagnostics.pack(fill=tk.X)

    workspace = ttk.Frame(content, style="Aurora.TFrame")
    workspace.grid(row=1, column=1, sticky="nsew")
    workspace.columnconfigure(0, weight=1)
    workspace.rowconfigure(1, weight=2)
    workspace.rowconfigure(3, weight=2)
    workspace.rowconfigure(5, weight=1)

    ttk.Label(
        workspace, text="SPECTRUM - SYNTHETIC INPUT", style="Aurora.Status.TLabel"
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))
    spectrum = SpectrumView(
        workspace,
        floor_db=settings.spectrum_floor_db,
        ceiling_db=settings.spectrum_ceiling_db,
    )
    spectrum.grid(row=1, column=0, sticky="nsew")

    ttk.Label(
        workspace, text="WATERFALL - SYNTHETIC INPUT", style="Aurora.Status.TLabel"
    ).grid(row=2, column=0, sticky="w", pady=(10, 4))
    waterfall_model = WaterfallModel(
        settings.spectrum_fft_size // 2 + 1,
        history_size=settings.waterfall_history_size,
        floor_db=settings.spectrum_floor_db,
        ceiling_db=settings.spectrum_ceiling_db,
    )
    waterfall = WaterfallView(workspace, waterfall_model)
    waterfall.grid(row=3, column=0, sticky="nsew")

    ttk.Label(
        workspace, text="LOCAL MESSAGE HISTORY", style="Aurora.Status.TLabel"
    ).grid(row=4, column=0, sticky="w", pady=(10, 4))
    result_tabs = ttk.Notebook(workspace)
    result_tabs.grid(row=5, column=0, sticky="nsew")
    history_tab = ttk.Frame(result_tabs)
    benchmark_tab = ttk.Frame(result_tabs)
    result_tabs.add(history_tab, text="Messages")
    result_tabs.add(benchmark_tab, text="Channel Results")

    history = tk.Text(
        history_tab,
        height=5,
        state=tk.DISABLED,
        background="#0b1015",
        foreground=settings.foreground,
        insertbackground=settings.foreground,
        relief=tk.FLAT,
        padx=8,
        pady=6,
        font=("Consolas", 9),
    )
    history.tag_configure("tx", foreground="#58a6ff")
    history.tag_configure("rx", foreground="#52d6c7")
    history.tag_configure("error", foreground="#ff6b6b")
    history.pack(fill=tk.BOTH, expand=True)

    sweep_controls = ttk.Frame(benchmark_tab, padding=(4, 4))
    sweep_controls.grid(row=0, column=0, columnspan=2, sticky="ew")
    sweep_start = tk.DoubleVar(value=-24.0)
    sweep_stop = tk.DoubleVar(value=10.0)
    sweep_step = tk.DoubleVar(value=2.0)
    sweep_frames = tk.IntVar(value=200)
    sweep_symbol_rate = tk.DoubleVar(value=AURORA_ROBUST_MODE.symbol_rate)
    sweep_bandwidth = tk.DoubleVar(value=2_500.0)
    sweep_profile = tk.StringVar(value="AWGN only")
    sweep_interleaver = tk.StringVar(value="Mode fixed (16)")
    sweep_variables = (
        ("Start dB", sweep_start, -40.0, 20.0, 1.0),
        ("Stop dB", sweep_stop, -40.0, 30.0, 1.0),
        ("Step dB", sweep_step, 0.5, 10.0, 0.5),
        ("Frames/point", sweep_frames, 4, 2_000, 10),
        ("Symbol rate", sweep_symbol_rate, 1.0, 3_000.0, 1.0),
        ("Ref BW Hz", sweep_bandwidth, 100.0, 5_000.0, 100.0),
    )
    for column, (label, variable, start, end, increment) in enumerate(
        sweep_variables
    ):
        field = ttk.Frame(sweep_controls)
        field.grid(row=0, column=column, padx=(0, 5), sticky="w")
        ttk.Label(field, text=label).pack(anchor=tk.W)
        ttk.Spinbox(
            field,
            textvariable=variable,
            from_=start,
            to=end,
            increment=increment,
            width=9,
        ).pack()
    profile_field = ttk.Frame(sweep_controls)
    profile_field.grid(row=1, column=0, columnspan=3, pady=(5, 0), sticky="w")
    ttk.Label(profile_field, text="Channel profile").pack(side=tk.LEFT, padx=(0, 5))
    ttk.Combobox(
        profile_field,
        textvariable=sweep_profile,
        values=tuple(CHANNEL_IMPAIRMENT_PROFILES),
        state="readonly",
        width=24,
    ).pack(side=tk.LEFT)
    interleaver_field = ttk.Frame(sweep_controls)
    interleaver_field.grid(row=1, column=2, pady=(5, 0), sticky="w")
    ttk.Label(interleaver_field, text="Interleaver test override").pack(
        side=tk.LEFT, padx=(0, 5)
    )
    ttk.Combobox(
        interleaver_field,
        textvariable=sweep_interleaver,
        values=("Mode fixed (16)", "Diagnostic off"),
        state="readonly",
        width=16,
    ).pack(side=tk.LEFT)
    run_sweep_button = ttk.Button(sweep_controls, text="RUN ROBUSTNESS SWEEP")
    run_sweep_button.grid(row=1, column=3, columnspan=2, padx=(8, 4), sticky="e")
    cancel_sweep_button = ttk.Button(
        sweep_controls, text="CANCEL", state=tk.DISABLED
    )
    cancel_sweep_button.grid(
        row=1, column=5, padx=(0, 4), sticky="e"
    )
    sweep_progress = tk.StringVar(value="SYMBOL-DOMAIN AWGN | Sweep idle; no audio/RF")
    ttk.Label(benchmark_tab, textvariable=sweep_progress).grid(
        row=1, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 3)
    )

    result_columns = (
        "preset",
        "modulation",
        "interleaver",
        "snr",
        "esn0",
        "coded_ebn0",
        "frames",
        "passed",
        "rate",
        "confidence",
        "ber",
        "errors",
        "recovered",
        "throughput",
        "milliseconds",
    )
    results = ttk.Treeview(
        benchmark_tab,
        columns=result_columns,
        show="headings",
        height=5,
    )
    headings = (
        "Preset",
        "Mode",
        "Interleaver",
        "SNR ref",
        "Es/N0",
        "Coded Eb/N0",
        "Frames",
        "Passed",
        "Success",
        "95% CI",
        "BER",
        "Bit errors",
        "Recovered",
        "Net bps",
        "ms/frame",
    )
    widths = (105, 55, 75, 60, 60, 85, 55, 55, 65, 100, 75, 70, 70, 65, 70)
    for column, heading, width in zip(result_columns, headings, widths, strict=True):
        results.heading(column, text=heading)
        results.column(column, width=width, minwidth=45, anchor=tk.CENTER)
    result_scroll = ttk.Scrollbar(
        benchmark_tab, orient=tk.HORIZONTAL, command=results.xview
    )
    results.configure(xscrollcommand=result_scroll.set)
    results.grid(row=2, column=0, sticky="nsew")
    result_scroll.grid(row=3, column=0, sticky="ew")
    benchmark_tab.columnconfigure(0, weight=1)
    benchmark_tab.rowconfigure(2, weight=1)

    composer = ttk.Frame(content, style="Aurora.TFrame")
    composer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    composer.columnconfigure(0, weight=1)
    message = tk.StringVar(value="CQ CQ from Aurora")
    entry = ttk.Entry(composer, textvariable=message)
    entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    send_button = ttk.Button(composer, text="RUN LOCAL CODEC TEST")
    send_button.grid(row=0, column=1)

    simulation_running = False
    animation_job: str | None = None
    benchmark_job: str | None = None
    benchmark_running = False
    benchmark_results: queue.Queue[object] = queue.Queue()
    sweep_cancel = threading.Event()
    profile_thresholds: dict[str, dict[str, dict[str, float | None]]] = {}

    def animate_signal() -> None:
        nonlocal animation_job
        if not simulation_running:
            animation_job = None
            return
        samples, snapshot = controller.generate_samples()
        frame = compute_spectrum(
            samples,
            settings.audio_sample_rate,
            fft_size=settings.spectrum_fft_size,
            floor_db=settings.spectrum_floor_db,
        )
        spectrum.update_spectrum(frame)
        waterfall.add_spectrum(frame.power_db)
        diagnostics.update_diagnostics(snapshot)
        animation_job = root.after(120, animate_signal)

    def toggle_simulation() -> None:
        nonlocal simulation_running
        simulation_running = not simulation_running
        simulation_button.configure(
            text="STOP SYNTHETIC SIGNAL"
            if simulation_running
            else "START SYNTHETIC SIGNAL"
        )
        if simulation_running:
            session_log.record(
                "SYNTHETIC_SIGNAL_START",
                sample_rate=settings.audio_sample_rate,
                block_size=settings.audio_block_size,
            )
            _append_history(history, "[TEST] Synthetic display signal started.")
            animate_signal()
        else:
            session_log.record("SYNTHETIC_SIGNAL_STOP")
            _append_history(history, "[TEST] Synthetic display signal stopped.")

    def run_local_test() -> None:
        started = time.perf_counter()
        try:
            result = controller.local_round_trip(message.get(), modulation.get())
            elapsed_ms = (time.perf_counter() - started) * 1_000.0
            session_log.record(
                "LOCAL_CODEC_RESULT",
                modulation=result.modulation,
                message_length=len(result.transmitted_text),
                crc=result.diagnostics.crc_status,
                fec=result.diagnostics.fec_status,
                success=result.received_text == result.transmitted_text,
                elapsed_ms=round(elapsed_ms, 3),
            )
            _append_history(
                history,
                f"[TX/{result.modulation}] {result.transmitted_text}",
                "tx",
            )
            _append_history(history, f"[RX/CRC PASS] {result.received_text}", "rx")
            diagnostics.update_diagnostics(result.diagnostics)
        except (UnicodeDecodeError, ValueError) as error:
            session_log.record(
                "LOCAL_CODEC_ERROR",
                modulation=modulation.get(),
                message_length=len(message.get()),
                error_type=type(error).__name__,
                error=str(error),
            )
            _append_history(history, f"[TEST ERROR] {error}", "error")

    def apply_preset(event: object | None = None) -> None:
        del event
        preset = CHANNEL_PRESETS[preset_name.get()]
        snr_db.set(preset.snr_db)
        frequency_offset.set(preset.frequency_offset_hz)

    def display_benchmark_result(
        result: BenchmarkResult, event_name: str = "CHANNEL_TEST_RESULT"
    ) -> None:
        confidence_low, confidence_high = result.success_confidence_95
        diagnostics.update_benchmark(result)
        session_log.record(
            event_name,
            preset=result.preset_name,
            modulation=result.modulation,
            injected_snr_db=result.snr_db,
            injected_frequency_offset_hz=result.frequency_offset_hz,
            reference_bandwidth_hz=result.reference_bandwidth_hz,
            symbol_rate=result.symbol_rate,
            esn0_db=result.esn0_db,
            coded_ebn0_db=result.coded_ebn0_db,
            interleaver_columns=result.interleaver_columns,
            measurement_domain=result.impairments.measurement_domain,
            **result.impairments.log_fields(),
            timing_tested=False,
            frame_count=result.frame_count,
            successful_frames=result.successful_frames,
            failed_frames=result.failed_frames,
            success_rate_percent=round(result.success_rate, 3),
            success_confidence_95_percent=(
                round(confidence_low, 3),
                round(confidence_high, 3),
            ),
            channel_ber=round(result.channel_ber, 9),
            channel_bit_errors=result.channel_bit_errors,
            recovered_bit_errors=result.corrected_bit_errors,
            net_throughput_bps=round(result.net_throughput_bps, 3),
            simulated_airtime_seconds=round(result.simulated_airtime_seconds, 6),
            elapsed_seconds=round(result.elapsed_seconds, 6),
            average_frame_ms=round(result.average_frame_ms, 3),
            cancelled=result.cancelled,
        )
        results.insert(
            "",
            0,
            values=(
                result.preset_name,
                result.modulation,
                (
                    "Off"
                    if result.interleaver_columns is None
                    else str(result.interleaver_columns)
                ),
                f"{result.snr_db:.1f}",
                f"{(result.esn0_db if result.esn0_db is not None else result.snr_db):.1f}",
                (
                    f"{result.coded_ebn0_db:.1f}"
                    if result.coded_ebn0_db is not None
                    else "n/a"
                ),
                result.frame_count,
                result.successful_frames,
                f"{result.success_rate:.1f}%",
                f"{confidence_low:.1f}-{confidence_high:.1f}%",
                f"{result.channel_ber:.3e}",
                result.channel_bit_errors,
                result.corrected_bit_errors,
                f"{result.net_throughput_bps:.1f}",
                f"{result.average_frame_ms:.1f}",
            ),
        )
        _show_channel_results(result_tabs, benchmark_tab)
        _append_history(
            history,
            f"[CHANNEL/{result.modulation}] {result.preset_name}: "
            f"{result.successful_frames}/{result.frame_count} passed, "
            f"{result.channel_bit_errors} pre-FEC bit errors.",
            "rx" if result.failed_frames == 0 else "error",
        )

    def finish_benchmark(result: BenchmarkResult) -> None:
        nonlocal benchmark_running
        benchmark_running = False
        run_channel_button.configure(state=tk.NORMAL)
        run_hundred_button.configure(state=tk.NORMAL)
        run_sweep_button.configure(state=tk.NORMAL)
        cancel_sweep_button.configure(state=tk.DISABLED)
        display_benchmark_result(result)

    def poll_benchmark() -> None:
        nonlocal benchmark_job, benchmark_running
        try:
            outcome = benchmark_results.get_nowait()
        except queue.Empty:
            if benchmark_running:
                benchmark_job = root.after(100, poll_benchmark)
            else:
                benchmark_job = None
            return
        benchmark_job = None
        if isinstance(outcome, tuple) and outcome and outcome[0] == "sweep_point":
            _, point, point_index, point_count = outcome
            display_benchmark_result(point, "ROBUSTNESS_SWEEP_POINT")
            sweep_progress.set(
                f"{point.impairments.name} | Point {point_index}/{point_count}: "
                f"{point.snr_db:+.1f} dB, {point.success_rate:.1f}% success"
            )
            benchmark_job = root.after(10, poll_benchmark)
            return
        if isinstance(outcome, RobustnessSweepResult):
            benchmark_running = False
            run_channel_button.configure(state=tk.NORMAL)
            run_hundred_button.configure(state=tk.NORMAL)
            run_sweep_button.configure(state=tk.NORMAL)
            cancel_sweep_button.configure(state=tk.DISABLED)
            status = "cancelled" if outcome.cancelled else "complete"
            threshold_50 = outcome.threshold_snr_db(50.0)
            threshold_90 = outcome.threshold_snr_db(90.0)
            threshold_95 = outcome.threshold_snr_db(95.0)

            def format_threshold(value: float | None) -> str:
                return "n/a" if value is None else f"{value:+.2f} dB"

            sweep_progress.set(
                f"{outcome.config.impairments.name} | interleaver "
                f"{outcome.config.interleaver_columns or 'Off'} | {status}: "
                f"{len(outcome.points)} points; "
                f"50% {format_threshold(threshold_50)}, "
                f"90% {format_threshold(threshold_90)}, "
                f"95% {format_threshold(threshold_95)}"
            )
            session_log.record(
                "ROBUSTNESS_SWEEP_END",
                modulation=outcome.modulation,
                status=status,
                measurement_domain=outcome.config.impairments.measurement_domain,
                interleaver_columns=outcome.config.interleaver_columns,
                completed_points=len(outcome.points),
                elapsed_seconds=round(outcome.elapsed_seconds, 6),
                threshold_50_percent_snr_db=threshold_50,
                threshold_90_percent_snr_db=threshold_90,
                threshold_95_percent_snr_db=threshold_95,
                **outcome.config.impairments.log_fields(),
            )
            if not outcome.cancelled:
                modulation_thresholds = profile_thresholds.setdefault(
                    outcome.modulation, {}
                )
                comparison_key = (
                    f"{outcome.config.impairments.name} | interleaver "
                    f"{outcome.config.interleaver_columns or 'Off'}"
                )
                modulation_thresholds[comparison_key] = {
                    "threshold_50_percent_snr_db": threshold_50,
                    "threshold_90_percent_snr_db": threshold_90,
                    "threshold_95_percent_snr_db": threshold_95,
                }
                session_log.record(
                    "ROBUSTNESS_PROFILE_COMPARISON",
                    modulation=outcome.modulation,
                    tested_profile_count=len(modulation_thresholds),
                    thresholds_by_profile=modulation_thresholds,
                )
            _append_history(
                history,
                f"[SWEEP] {outcome.modulation} {status}; "
                f"{len(outcome.points)} points; 50/90/95% thresholds "
                f"{format_threshold(threshold_50)} / "
                f"{format_threshold(threshold_90)} / "
                f"{format_threshold(threshold_95)}.",
                "rx" if not outcome.cancelled else "error",
            )
            return
        if isinstance(outcome, Exception):
            benchmark_running = False
            run_channel_button.configure(state=tk.NORMAL)
            run_hundred_button.configure(state=tk.NORMAL)
            run_sweep_button.configure(state=tk.NORMAL)
            cancel_sweep_button.configure(state=tk.DISABLED)
            session_log.record(
                "CHANNEL_TEST_ERROR",
                error_type=type(outcome).__name__,
                error=str(outcome),
            )
            _append_history(history, f"[CHANNEL ERROR] {outcome}", "error")
            return
        finish_benchmark(outcome)

    def start_benchmark(requested_frames: int | None = None) -> None:
        nonlocal benchmark_running, benchmark_job
        if benchmark_running:
            return
        try:
            frames = requested_frames if requested_frames is not None else frame_count.get()
            selected_snr = float(snr_db.get())
            selected_offset = float(frequency_offset.get())
            selected_message = message.get().strip()
            if not selected_message:
                raise ValueError("Enter a message for the channel test")
            if not 1 <= frames <= 1_000:
                raise ValueError("Frame count must be between 1 and 1000")
        except (tk.TclError, ValueError) as error:
            _append_history(history, f"[CHANNEL ERROR] {error}", "error")
            return

        benchmark_running = True
        run_channel_button.configure(state=tk.DISABLED)
        run_hundred_button.configure(state=tk.DISABLED)
        session_log.record(
            "CHANNEL_TEST_START",
            preset=preset_name.get(),
            modulation=modulation.get(),
            injected_snr_db=selected_snr,
            injected_frequency_offset_hz=selected_offset,
            frame_count=frames,
            message_length=len(selected_message),
            timing_tested=False,
        )
        _append_history(
            history,
            f"[CHANNEL] Running {frames} {modulation.get()} frames at "
            f"{selected_snr:.1f} dB SNR, {selected_offset:+.2f} Hz rotation.",
        )

        def worker() -> None:
            try:
                benchmark_results.put(
                    controller.run_benchmark(
                        selected_message,
                        modulation.get(),
                        snr_db=selected_snr,
                        frequency_offset_hz=selected_offset,
                        frame_count=frames,
                        preset_name=preset_name.get(),
                        symbol_rate=3_000.0,
                        reference_bandwidth_hz=2_500.0,
                    )
                )
            except Exception as error:
                benchmark_results.put(error)

        threading.Thread(
            target=worker,
            name="AuroraChannelTest",
            daemon=True,
        ).start()
        benchmark_job = root.after(100, poll_benchmark)

    def start_robustness_sweep() -> None:
        nonlocal benchmark_running, benchmark_job
        if benchmark_running:
            return
        try:
            selected_message = message.get().strip()
            if not selected_message:
                raise ValueError("Enter a message for the robustness sweep")
            config = SweepConfig(
                start_snr_db=float(sweep_start.get()),
                stop_snr_db=float(sweep_stop.get()),
                step_snr_db=float(sweep_step.get()),
                frames_per_point=int(sweep_frames.get()),
                reference_bandwidth_hz=float(sweep_bandwidth.get()),
                symbol_rate=float(sweep_symbol_rate.get()),
                impairments=CHANNEL_IMPAIRMENT_PROFILES[sweep_profile.get()],
                interleaver_columns=(
                    None
                    if sweep_interleaver.get() == "Diagnostic off"
                    else AURORA_ROBUST_MODE.interleaver_columns
                ),
            )
            if config.frames_per_point < len(config.seeds):
                raise ValueError("Frames per point must cover every random seed")
        except (tk.TclError, ValueError) as error:
            _append_history(history, f"[SWEEP ERROR] {error}", "error")
            return

        sweep_cancel.clear()
        benchmark_running = True
        run_channel_button.configure(state=tk.DISABLED)
        run_hundred_button.configure(state=tk.DISABLED)
        run_sweep_button.configure(state=tk.DISABLED)
        cancel_sweep_button.configure(state=tk.NORMAL)
        sweep_progress.set(
            f"{config.impairments.name} | Symbol-domain sweep starting; no audio/RF"
        )
        session_log.record(
            "ROBUSTNESS_SWEEP_START",
            modulation=AURORA_ROBUST_MODE.modulation.upper(),
            start_snr_db=config.start_snr_db,
            stop_snr_db=config.stop_snr_db,
            step_snr_db=config.step_snr_db,
            frames_per_point=config.frames_per_point,
            seeds=config.seeds,
            reference_bandwidth_hz=config.reference_bandwidth_hz,
            symbol_rate=config.symbol_rate,
            frequency_offset_hz=config.frequency_offset_hz,
            message_length=len(selected_message),
            measurement_domain=config.impairments.measurement_domain,
            interleaver_columns=config.interleaver_columns,
            **config.impairments.log_fields(),
        )
        _append_history(
            history,
            f"[SWEEP] {AURORA_ROBUST_MODE.modulation.upper()} "
            f"{config.start_snr_db:+.1f} to "
            f"{config.stop_snr_db:+.1f} dB, {config.frames_per_point} frames/point, "
            f"{config.impairments.name}, interleaver "
            f"{config.interleaver_columns or 'Off'}.",
        )

        def on_point(point: BenchmarkResult, index: int, total: int) -> None:
            benchmark_results.put(("sweep_point", point, index, total))

        def worker() -> None:
            try:
                benchmark_results.put(
                    controller.run_snr_sweep(
                        selected_message,
                        AURORA_ROBUST_MODE.modulation,
                        config,
                        should_continue=lambda: not sweep_cancel.is_set(),
                        on_point=on_point,
                    )
                )
            except Exception as error:
                benchmark_results.put(error)

        threading.Thread(
            target=worker,
            name="AuroraRobustnessSweep",
            daemon=True,
        ).start()
        benchmark_job = root.after(100, poll_benchmark)

    def cancel_robustness_sweep() -> None:
        if not benchmark_running:
            return
        sweep_cancel.set()
        cancel_sweep_button.configure(state=tk.DISABLED)
        sweep_progress.set("Cancellation requested; finishing current frame...")
        session_log.record("ROBUSTNESS_SWEEP_CANCEL_REQUEST")

    def close_application() -> None:
        if simulation_running:
            session_log.record("SYNTHETIC_SIGNAL_STOP", reason="application_close")
        if benchmark_running:
            session_log.record("CHANNEL_TEST_INTERRUPTED", reason="application_close")
            sweep_cancel.set()
        if animation_job is not None:
            root.after_cancel(animation_job)
        if benchmark_job is not None:
            root.after_cancel(benchmark_job)
        session_log.close()
        root.destroy()

    simulation_button.configure(command=toggle_simulation)
    send_button.configure(command=run_local_test)
    run_channel_button.configure(command=start_benchmark)
    run_hundred_button.configure(command=lambda: start_benchmark(100))
    show_results_button.configure(
        command=lambda: _show_channel_results(result_tabs, benchmark_tab)
    )
    run_sweep_button.configure(command=start_robustness_sweep)
    cancel_sweep_button.configure(command=cancel_robustness_sweep)
    preset_box.bind("<<ComboboxSelected>>", apply_preset)
    entry.bind("<Return>", lambda event: run_local_test())
    root.protocol("WM_DELETE_WINDOW", close_application)
    _append_history(
        history,
        "[READY] Local simulation only. Audio, CAT, PTT, and RF are inactive.",
    )
    _append_history(history, f"[LOG] Session debug: {session_log.path.name}")
    session_log.record("GUI_READY", session_log=session_log.path.name)
    return root


def run() -> None:
    """Start the Aurora desktop application."""
    application = create_application()
    application.mainloop()
