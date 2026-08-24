"""Responsive PySide6 operator interface for Aurora."""

from __future__ import annotations

import sys
import queue
import threading

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import SETTINGS, AppSettings
from audio.buffer import AudioBuffer
from audio.device import compatible_outputs, list_audio_devices
from audio.multichannel_receiver import MultichannelAudioReceiver, mode_at_frequency
from audio.playback import condition_playback, play_audio, stop_playback
from audio.streaming import AudioInputStream, AudioStreamStatus
from dsp.spectrum import SpectrumFrame, compute_spectrum
from dsp.waveform import modulate_audio
from modem.bandwidth_adaptation import fixed_bandwidth
from modem.chat_transport import encode_chat_transmission
from radio.hamlib_control import HamlibController
from radio.bundled_hamlib import BundledHamlibConfig, BundledHamlibService
from radio.device import list_serial_ports
from util.session_debug_log import SessionDebugLog


APPLICATION_VERSION = "0.1.0-dev"
BACKGROUND = QColor("#0b1016")
FIELD = QColor("#0d141c")
BORDER = QColor("#293846")
FOREGROUND = QColor("#eef5f7")
MUTED = QColor("#8fa2b3")
ACCENT = QColor("#47dbc6")
BLUE = QColor("#68a7ff")


class SpectrumWidget(QWidget):
    """Efficient spectrum plot with a shared clickable TX/RX marker."""

    frequency_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(110)
        self._frame: SpectrumFrame | None = None
        self._selected_hz = 1_500

    def set_frame(self, frame: SpectrumFrame) -> None:
        """Replace the spectrum data and schedule a repaint."""
        self._frame = frame
        self.update()

    def set_frequency(self, frequency_hz: int) -> None:
        """Move the shared TX/RX marker."""
        self._selected_hz = max(100, min(3_000, int(frequency_hz)))
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        fraction = max(0.0, min(1.0, event.position().x() / max(self.width(), 1)))
        frequency = round((100 + fraction * 2_900) / 100) * 100
        self.frequency_selected.emit(frequency)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), FIELD)
        painter.setRenderHint(QPainter.Antialiasing)
        plot_bottom = max(self.height() - 20, 1)
        painter.setPen(QPen(BORDER, 1))
        for frequency in range(500, 3_001, 500):
            x = (frequency - 100) / 2_900 * self.width()
            painter.drawLine(int(x), 0, int(x), plot_bottom)
            painter.setPen(MUTED)
            painter.drawText(int(x) + 3, self.height() - 4, str(frequency))
            painter.setPen(QPen(BORDER, 1))
        marker_x = (self._selected_hz - 100) / 2_900 * self.width()
        painter.setPen(QPen(BLUE, 2))
        painter.drawLine(int(marker_x), 0, int(marker_x), plot_bottom)
        painter.drawText(int(marker_x) + 5, 14, f"TX/RX {self._selected_hz} Hz")
        if self._frame is None:
            return
        visible = (
            (self._frame.frequencies_hz >= 100)
            & (self._frame.frequencies_hz <= 3_000)
        )
        frequencies = self._frame.frequencies_hz[visible]
        power = np.clip((self._frame.power_db[visible] + 120.0) / 120.0, 0.0, 1.0)
        if len(power) < 2:
            return
        path = QPainterPath()
        for index, (frequency, level) in enumerate(zip(frequencies, power, strict=True)):
            point = QPointF(
                (float(frequency) - 100.0) / 2_900.0 * self.width(),
                (1.0 - float(level)) * plot_bottom,
            )
            path.moveTo(point) if index == 0 else path.lineTo(point)
        painter.setPen(QPen(ACCENT, 1.25))
        painter.drawPath(path)


class WaterfallWidget(QWidget):
    """Compact rolling spectral history rendered without external plotting tools."""

    def __init__(self, rows: int = 72) -> None:
        super().__init__()
        self.setMinimumHeight(90)
        self._rows = rows
        self._history: np.ndarray | None = None
        self._image: QImage | None = None

    def add_frame(self, frame: SpectrumFrame) -> None:
        """Append the visible 100–3000 Hz power row."""
        visible = (
            (frame.frequencies_hz >= 100) & (frame.frequencies_hz <= 3_000)
        )
        values = np.asarray(frame.power_db[visible], dtype=np.float32)
        if self._history is None or self._history.shape[1] != len(values):
            self._history = np.full(
                (self._rows, len(values)), -120.0, dtype=np.float32
            )
        self._history[1:] = self._history[:-1]
        self._history[0] = values
        normalized = np.clip((self._history + 120.0) / 120.0, 0.0, 1.0)
        rgb = np.empty((*normalized.shape, 3), dtype=np.uint8)
        rgb[..., 0] = np.asarray(13 + 51 * normalized, dtype=np.uint8)
        rgb[..., 1] = np.asarray(26 + 191 * normalized, dtype=np.uint8)
        rgb[..., 2] = np.asarray(46 + 166 * normalized, dtype=np.uint8)
        height, width, _ = rgb.shape
        self._image = QImage(
            rgb.data,
            width,
            height,
            3 * width,
            QImage.Format_RGB888,
        ).copy()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), FIELD)
        if self._image is None:
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), self._image)


class AuroraQtWindow(QMainWindow):
    """Cross-platform Aurora operator window optimized for compact displays."""

    def __init__(self, settings: AppSettings = SETTINGS) -> None:
        super().__init__()
        self.settings = settings
        self.session_log = SessionDebugLog(settings.log_directory, APPLICATION_VERSION)
        self.setWindowTitle("Aurora • Adaptive HF communications")
        self.resize(1_080, 680)
        self.setMinimumSize(760, 500)
        self._input_devices = {}
        self._output_devices = {}
        self._audio_blocks: queue.Queue[AudioBuffer | AudioStreamStatus] = queue.Queue()
        self._display_blocks: queue.Queue[AudioBuffer] = queue.Queue(maxsize=1)
        self._decode_events: queue.Queue[object] = queue.Queue()
        self._cat_events: queue.Queue[object] = queue.Queue()
        self._receiver: MultichannelAudioReceiver | None = None
        self._stream: AudioInputStream | None = None
        self._hamlib: HamlibController | None = None
        self._hamlib_service: BundledHamlibService | None = None
        self._cat_request_pending = False
        self._receiver_stop = threading.Event()
        self._build_ui()
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(200)
        self._display_timer.timeout.connect(self._update_live_display)
        self._display_timer.start()
        self._event_timer = QTimer(self)
        self._event_timer.setInterval(100)
        self._event_timer.timeout.connect(self._poll_decode_events)
        self._event_timer.start()
        self._cat_timer = QTimer(self)
        self._cat_timer.setInterval(1_000)
        self._cat_timer.timeout.connect(self._request_cat_status)
        self._cat_timer.start()
        self._refresh_audio()
        self._append("[READY] Select radio audio input and connect Hamlib rigctld.")
        self._append(f"[LOG] Session debug: {self.session_log.path.name}")

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        title = QLabel("Aurora")
        title.setObjectName("title")
        header.addWidget(title)
        header.addWidget(QLabel("Adaptive HF communications"))
        header.addStretch()
        self.radio_badge = QLabel("RADIO DISCONNECTED")
        self.radio_badge.setObjectName("badge")
        header.addWidget(self.radio_badge)
        outer.addLayout(header)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_controls())
        split.addWidget(self._build_workspace())
        split.setSizes((240, 820))
        outer.addWidget(split, 1)

        composer = QHBoxLayout()
        self.message = QLineEdit("CQ CQ from Aurora")
        self.message.returnPressed.connect(self._transmit)
        composer.addWidget(self.message, 1)
        self.transmit_button = QPushButton("TRANSMIT")
        self.transmit_button.setObjectName("primary")
        self.transmit_button.setEnabled(False)
        self.transmit_button.clicked.connect(self._transmit)
        composer.addWidget(self.transmit_button)
        outer.addLayout(composer)

    def _build_controls(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setMinimumWidth(205)
        panel.setMaximumWidth(280)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("SIGNAL CONTROLS"))
        form = QFormLayout()
        self.bandwidth = QComboBox()
        self.bandwidth.addItems(("AUTO", "500 Hz", "2.3 kHz", "2.8 kHz"))
        form.addRow("Bandwidth", self.bandwidth)
        self.frequency = QSpinBox()
        self.frequency.setRange(100, 3_000)
        self.frequency.setSingleStep(100)
        self.frequency.setValue(1_500)
        self.frequency.setSuffix(" Hz")
        self.frequency.valueChanged.connect(self._frequency_changed)
        form.addRow("TX/RX", self.frequency)
        self.callsign = QLineEdit("N4EAC")
        form.addRow("Callsign", self.callsign)
        self.grid = QLineEdit()
        form.addRow("Grid", self.grid)
        layout.addLayout(form)
        layout.addWidget(QLabel("RADIO AUDIO"))
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        layout.addWidget(self.input_device)
        layout.addWidget(self.output_device)
        self.rx_button = QPushButton("START SPECTRUM RX")
        self.rx_button.clicked.connect(self._toggle_receiver)
        layout.addWidget(self.rx_button)
        layout.addSpacing(8)
        layout.addWidget(QLabel("HAMLIB CAT"))
        cat_form = QFormLayout()
        self.hamlib_host = QLineEdit("127.0.0.1")
        self.external_hamlib = QCheckBox("Use external rigctld")
        self.hamlib_model = QSpinBox()
        self.hamlib_model.setRange(1, 99_999)
        self.hamlib_model.setValue(1)
        self.cat_device = QComboBox()
        self.cat_device.setEditable(True)
        self.cat_device.addItems(port.device for port in list_serial_ports())
        self.cat_baud = QComboBox()
        self.cat_baud.addItems(("4800", "9600", "19200", "38400", "57600", "115200"))
        self.cat_baud.setCurrentText("9600")
        self.hamlib_port = QSpinBox()
        self.hamlib_port.setRange(1, 65_535)
        self.hamlib_port.setValue(4_532)
        self.radio_frequency = QSpinBox()
        self.radio_frequency.setRange(100_000, 2_000_000_000)
        self.radio_frequency.setValue(14_074_000)
        self.radio_frequency.setSuffix(" Hz")
        self.radio_mode = QComboBox()
        self.radio_mode.addItems(("USB-D", "USB", "LSB-D", "LSB", "CW", "CW-R"))
        cat_form.addRow("Model #", self.hamlib_model)
        cat_form.addRow("CAT device", self.cat_device)
        cat_form.addRow("Baud", self.cat_baud)
        cat_form.addRow(self.external_hamlib)
        cat_form.addRow("External host", self.hamlib_host)
        cat_form.addRow("Service port", self.hamlib_port)
        cat_form.addRow("Radio", self.radio_frequency)
        cat_form.addRow("Mode", self.radio_mode)
        layout.addLayout(cat_form)
        self.cat_button = QPushButton("CONNECT HAMLIB")
        self.cat_button.clicked.connect(self._toggle_cat)
        layout.addWidget(self.cat_button)
        self.apply_radio_button = QPushButton("APPLY FREQUENCY / MODE")
        self.apply_radio_button.setEnabled(False)
        self.apply_radio_button.clicked.connect(self._apply_radio_settings)
        layout.addWidget(self.apply_radio_button)
        self.ptt_arm = QCheckBox("Arm PTT control")
        self.ptt_arm.toggled.connect(self._ptt_arm_changed)
        layout.addWidget(self.ptt_arm)
        layout.addSpacing(8)
        layout.addWidget(QLabel("DIAGNOSTICS"))
        self.diagnostics: dict[str, QLabel] = {}
        diagnostic_form = QFormLayout()
        for name, initial in (
            ("Sync", "SEARCHING"),
            ("SNR", "-- dB"),
            ("Offset", "-- Hz"),
            ("Timing", "--"),
            ("CRC", "WAITING"),
            ("FEC", "IDLE"),
        ):
            value = QLabel(initial)
            value.setObjectName("value")
            self.diagnostics[name] = value
            diagnostic_form.addRow(name, value)
        layout.addLayout(diagnostic_form)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(215)
        scroll.setMaximumWidth(290)
        scroll.setWidget(panel)
        return scroll

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(QLabel("SIGNAL SPECTRUM • click to tune"))
        self.spectrum = SpectrumWidget()
        self.spectrum.frequency_selected.connect(self.frequency.setValue)
        layout.addWidget(self.spectrum, 2)
        layout.addWidget(QLabel("SIGNAL HISTORY"))
        self.waterfall = WaterfallWidget()
        layout.addWidget(self.waterfall, 2)
        self.tabs = QTabWidget()
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.tabs.addTab(self.history, "Messages")
        self.other_signals = QTableWidget(0, 3)
        self.other_signals.setHorizontalHeaderLabels(("Frequency", "Callsign", "Message"))
        self.other_signals.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabs.addTab(self.other_signals, "Other Signals")
        layout.addWidget(self.tabs, 2)
        return workspace

    def _frequency_changed(self, frequency_hz: int) -> None:
        self.spectrum.set_frequency(frequency_hz)

    def _append(self, text: str) -> None:
        self.history.append(text)

    def add_other_signal(self, frequency_hz: int, callsign: str, message: str) -> None:
        """Insert an off-frequency CRC-valid decode into the activity list."""
        self.other_signals.insertRow(0)
        for column, value in enumerate((f"{frequency_hz} Hz", callsign, message)):
            self.other_signals.setItem(0, column, QTableWidgetItem(value))

    def _receive_audio(self, audio: AudioBuffer) -> None:
        """Fan one radio-audio block out to decoding and latest-frame display."""
        self._audio_blocks.put(audio)
        try:
            self._display_blocks.put_nowait(audio)
        except queue.Full:
            try:
                self._display_blocks.get_nowait()
            except queue.Empty:
                pass
            self._display_blocks.put_nowait(audio)

    def _update_live_display(self) -> None:
        latest = None
        while True:
            try:
                latest = self._display_blocks.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return
        display_samples = np.asarray(latest.samples, dtype=np.float32).reshape(-1)
        frame = compute_spectrum(
            display_samples,
            self.settings.audio_sample_rate,
            fft_size=self.settings.spectrum_fft_size,
            floor_db=self.settings.spectrum_floor_db,
        )
        self.spectrum.set_frame(frame)
        self.waterfall.add_frame(frame)
        peak = float(np.max(np.abs(display_samples)))
        self.diagnostics["SNR"].setText(f"Input peak {peak:.3f}")

    def _selected_mode(self):
        selection = self.bandwidth.currentText()
        bandwidth = {
            "AUTO": 500,
            "500 Hz": 500,
            "2.3 kHz": 2_300,
            "2.8 kHz": 2_800,
        }[selection]
        return fixed_bandwidth(bandwidth).mode

    def _refresh_audio(self) -> None:
        try:
            inputs = list_audio_devices("input")
            outputs = list_audio_devices("output")
        except Exception as error:
            self._append(f"[AUDIO ERROR] {error}")
            return
        self._input_devices = {f"{item.index}: {item.name}": item for item in inputs}
        self.input_device.clear()
        self.input_device.addItems(self._input_devices)
        selected_input = next(iter(self._input_devices.values()), None)
        compatible = () if selected_input is None else compatible_outputs(selected_input, outputs)
        self._output_devices = {f"{item.index}: {item.name}": item for item in compatible}
        self.output_device.clear()
        self.output_device.addItems(self._output_devices)

    def _toggle_receiver(self) -> None:
        if self._stream is not None:
            self._stop_receiver()
            return
        try:
            device = self._input_devices[self.input_device.currentText()]
            mode = self._selected_mode()
            self._receiver = MultichannelAudioReceiver(
                tuple(range(100, 3_001, 100)), mode
            )
            self._receiver_stop.clear()
            self._stream = AudioInputStream(
                self._receive_audio,
                settings=self.settings,
                device=device.index,
                status_consumer=self._audio_blocks.put,
            )
            self._stream.start()
        except Exception as error:
            self._receiver = None
            self._stream = None
            self._append(f"[SPECTRUM RX ERROR] {error}")
            return

        def worker() -> None:
            discontinuity = False
            while not self._receiver_stop.is_set():
                try:
                    item = self._audio_blocks.get(timeout=0.2)
                except queue.Empty:
                    continue
                if isinstance(item, AudioStreamStatus):
                    discontinuity = discontinuity or item.input_discontinuity
                    continue
                try:
                    events = self._receiver.feed(item, discontinuity=discontinuity)
                    discontinuity = False
                    for decoded in events:
                        self._decode_events.put(decoded)
                except Exception as error:
                    self._decode_events.put(error)
                    return

        threading.Thread(target=worker, name="AuroraQtSpectrumReceiver", daemon=True).start()
        self.rx_button.setText("STOP SPECTRUM RX")
        self._append(f"[RX] Live radio audio: {device.name}; scanning 100–3000 Hz.")

    def _stop_receiver(self) -> None:
        self._receiver_stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        self._stream = None
        self._receiver = None
        stop_playback()
        self.rx_button.setText("START SPECTRUM RX")

    def _poll_decode_events(self) -> None:
        while True:
            try:
                event = self._decode_events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, Exception):
                self._append(f"[SPECTRUM RX ERROR] {event}")
                self._stop_receiver()
                return
            if event.frequency_hz == self.frequency.value():
                self._append(
                    f"[RX {event.frequency_hz} Hz/{event.message.callsign}] "
                    f"{event.message.text}"
                )
            else:
                self.add_other_signal(
                    event.frequency_hz, event.message.callsign, event.message.text
                )
            self.diagnostics["Sync"].setText("LOCKED")
            self.diagnostics["Offset"].setText(f"{event.frequency_offset_hz:+.2f} Hz")
            self.diagnostics["CRC"].setText("PASS")
            self.diagnostics["FEC"].setText("CORRECTED")
        self._poll_cat_events()

    def _toggle_cat(self) -> None:
        if self._hamlib is not None:
            self._disconnect_cat()
            return
        self.cat_button.setEnabled(False)
        external = self.external_hamlib.isChecked()
        host = self.hamlib_host.text() if external else "127.0.0.1"
        port = self.hamlib_port.value()
        model = self.hamlib_model.value()
        device = self.cat_device.currentText()
        baud = int(self.cat_baud.currentText())

        def worker() -> None:
            service = None
            try:
                if not external:
                    service = BundledHamlibService()
                    service.start(BundledHamlibConfig(model, device, baud, port))
                controller = HamlibController(host, port)
                status = (
                    controller.get_frequency(),
                    *controller.get_mode(),
                    controller.get_ptt(),
                )
                self._cat_events.put(("connected", controller, service, status))
            except Exception as error:
                if service is not None:
                    service.stop()
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraHamlibConnect", daemon=True).start()

    def _disconnect_cat(self) -> None:
        controller = self._hamlib
        service = self._hamlib_service
        self._hamlib = None
        self._hamlib_service = None
        self.ptt_arm.setChecked(False)
        if controller is not None:
            try:
                controller.set_ptt(False)
            except Exception:
                pass
            controller.close()
        if service is not None:
            service.stop()
        self.cat_button.setText("CONNECT HAMLIB")
        self.cat_button.setEnabled(True)
        self.apply_radio_button.setEnabled(False)
        self.radio_badge.setText("RADIO DISCONNECTED")

    def _request_cat_status(self) -> None:
        if self._hamlib is None or self._cat_request_pending:
            return
        self._cat_request_pending = True
        controller = self._hamlib

        def worker() -> None:
            try:
                status = (
                    controller.get_frequency(),
                    *controller.get_mode(),
                    controller.get_ptt(),
                )
                self._cat_events.put(("status", status))
            except Exception as error:
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraHamlibPoll", daemon=True).start()

    def _apply_radio_settings(self) -> None:
        if self._hamlib is None:
            return
        controller = self._hamlib
        frequency = self.radio_frequency.value()
        mode = self.radio_mode.currentText()
        passband = self._selected_mode().occupied_bandwidth_hz

        def worker() -> None:
            try:
                controller.set_frequency(frequency)
                controller.set_mode(mode, passband)
                self._cat_events.put(("settings_applied", None))
            except Exception as error:
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraHamlibSet", daemon=True).start()

    def _ptt_arm_changed(self, armed: bool) -> None:
        self.transmit_button.setEnabled(armed and self._hamlib is not None)

    def _show_cat_status(self, status: tuple[int, str, int, bool]) -> None:
        frequency, mode, passband, ptt = status
        self.radio_frequency.setValue(frequency)
        if self.radio_mode.findText(mode) < 0:
            self.radio_mode.addItem(mode)
        self.radio_mode.setCurrentText(mode)
        state = "TX" if ptt else "RX"
        self.radio_badge.setText(f"HAMLIB {state} • {frequency / 1_000_000:.6f} MHz")
        self.diagnostics["Sync"].setText(f"CAT {state}")
        self.session_log.record(
            "HAMLIB_STATUS",
            frequency_hz=frequency,
            mode=mode,
            passband_hz=passband,
            ptt=ptt,
        )

    def _poll_cat_events(self) -> None:
        while True:
            try:
                event = self._cat_events.get_nowait()
            except queue.Empty:
                return
            kind, *values = event
            self._cat_request_pending = False
            if kind == "connected":
                self._hamlib = values[0]
                self._hamlib_service = values[1]
                self.cat_button.setText("DISCONNECT HAMLIB")
                self.cat_button.setEnabled(True)
                self.apply_radio_button.setEnabled(True)
                self._show_cat_status(values[2])
                source = "external" if self._hamlib_service is None else "bundled"
                self._append(
                    f"[CAT] {source.title()} Hamlib connected; PTT remains disarmed."
                )
            elif kind == "status":
                self._show_cat_status(values[0])
            elif kind == "settings_applied":
                self._append("[CAT] Radio frequency and mode applied.")
            elif kind == "tx_complete":
                self.transmit_button.setEnabled(self.ptt_arm.isChecked())
                if values[0] is not None:
                    self._append(f"[TX ERROR] {values[0]}")
            elif kind == "cat_error":
                self.cat_button.setEnabled(True)
                self._append(f"[CAT ERROR] {values[0]}")

    def _build_transmit_audio(self) -> AudioBuffer:
        """Build conditioned radio audio for the current operator message."""
        mode = mode_at_frequency(self._selected_mode(), self.frequency.value())
        transmission = encode_chat_transmission(
            self.callsign.text(), self.message.text(), mode=mode
        )
        waveform = modulate_audio(
            transmission.symbols,
            mode,
            leading_silence_samples=self.settings.audio_sample_rate // 5,
        )
        return condition_playback(
            waveform,
            gain=0.55,
            fade_seconds=0.02,
            trailing_silence_seconds=0.10,
        )

    def _transmit(self) -> None:
        if self._hamlib is None or not self.ptt_arm.isChecked():
            self._append("[TX BLOCKED] Connect Hamlib and explicitly arm PTT.")
            return
        try:
            output = self._output_devices[self.output_device.currentText()]
            audio = self._build_transmit_audio()
        except Exception as error:
            self._append(f"[AUDIO TX ERROR] {error}")
            return
        self.transmit_button.setEnabled(False)

        def worker() -> None:
            try:
                self._hamlib.set_ptt(True)
                play_audio(audio, blocking=True, device=output.index)
                self._cat_events.put(("tx_complete", None))
            except Exception as error:
                self._cat_events.put(("tx_complete", error))
            finally:
                try:
                    self._hamlib.set_ptt(False)
                except Exception as error:
                    self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraRadioTransmit", daemon=True).start()
        self._append(
            f"[TX {self.frequency.value()} Hz/{self.callsign.text()}] "
            f"{self.message.text().strip()}"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._display_timer.stop()
        self._event_timer.stop()
        self._cat_timer.stop()
        if self._stream is not None:
            self._stop_receiver()
        if self._hamlib is not None:
            self._disconnect_cat()
        self.session_log.close()
        event.accept()


def _stylesheet() -> str:
    return """
        QWidget { background: #0b1016; color: #eef5f7; font-size: 12px; }
        QFrame#panel { background: #121a23; border: 1px solid #293846; border-radius: 6px; }
        QLabel#title { font-size: 25px; font-weight: 700; }
        QLabel#badge { background: #18232e; color: #f5bd4f; padding: 7px 11px; border-radius: 4px; }
        QLabel#value { color: #47dbc6; font-family: monospace; font-weight: 600; }
        QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget { background: #0d141c; border: 1px solid #293846; padding: 5px; }
        QPushButton { background: #18232e; border: 1px solid #293846; padding: 7px; border-radius: 4px; }
        QPushButton:hover { border-color: #47dbc6; }
        QPushButton#primary { background: #1d756c; border-color: #47dbc6; font-weight: 700; }
        QTabBar::tab { background: #121a23; padding: 7px 12px; }
        QTabBar::tab:selected { color: #47dbc6; border-bottom: 2px solid #47dbc6; }
    """


def run(settings: AppSettings = SETTINGS) -> None:
    """Start the responsive Qt Aurora interface."""
    application = QApplication.instance() or QApplication(sys.argv)
    application.setStyle("Fusion")
    application.setStyleSheet(_stylesheet())
    window = AuroraQtWindow(settings)
    window.show()
    application.exec()
