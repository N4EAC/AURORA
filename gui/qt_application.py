"""Responsive PySide6 operator interface for Aurora."""

from __future__ import annotations

import sys
import queue
import threading

import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
from radio.hamlib_models import list_radio_models
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

THEMES = {
    "Dark": ("#0b1016", "#0d141c", "#293846", "#eef5f7", "#8fa2b3", "#47dbc6", "#68a7ff"),
    "Amber": ("#171108", "#21180b", "#5f4821", "#ffe9bd", "#c4a66a", "#ffb52e", "#ffd166"),
    "Green": ("#07130c", "#0a1c10", "#255538", "#dfffea", "#80b894", "#35e878", "#8cffad"),
}


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
        self.setMinimumHeight(42)
        self.setMaximumHeight(72)
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

    def __init__(
        self,
        settings: AppSettings = SETTINGS,
        preferences: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.preferences = preferences or QSettings("N4EAC", "Aurora")
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
        self._radio_models = list_radio_models()
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
        self._restore_preferences()
        self._append("[READY] Select radio audio input and connect Hamlib rigctld.")
        self._append(f"[LOG] Session debug: {self.session_log.path.name}")

    def _build_ui(self) -> None:
        self._build_setup_dialog()
        self._build_menus()
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

        summary = QFrame()
        summary.setObjectName("panel")
        summary_layout = QVBoxLayout(summary)
        operating_row = QHBoxLayout()
        self.radio_frequency = QSpinBox()
        self.radio_frequency.setRange(100_000, 2_000_000_000)
        self.radio_frequency.setValue(14_074_000)
        self.radio_frequency.setSuffix(" Hz")
        self.radio_mode = QComboBox()
        self.radio_mode.addItems(("USB-D", "USB", "LSB-D", "LSB", "CW", "CW-R"))
        self.callsign_display = QLabel("N4EAC")
        self.callsign_display.setObjectName("value")
        self.bandwidth = QComboBox()
        self.bandwidth.addItems(("AUTO", "500 Hz", "2.3 kHz", "2.8 kHz"))
        for label, widget in (
            ("Frequency", self.radio_frequency),
            ("Mode", self.radio_mode),
            ("Station", self.callsign_display),
            ("Bandwidth", self.bandwidth),
        ):
            operating_row.addWidget(QLabel(label))
            operating_row.addWidget(widget)
        operating_row.addStretch()
        summary_layout.addLayout(operating_row)
        diagnostic_row = QHBoxLayout()
        self.diagnostics: dict[str, QLabel] = {}
        for name, initial in (
            ("Sync", "SEARCHING"), ("SNR", "-- dB"), ("Offset", "-- Hz"),
            ("Timing", "--"), ("CRC", "WAITING"), ("FEC", "IDLE"),
        ):
            value = QLabel(f"{name}: {initial}")
            value.setObjectName("value")
            self.diagnostics[name] = value
            diagnostic_row.addWidget(value)
        diagnostic_row.addStretch()
        summary_layout.addLayout(diagnostic_row)
        outer.addWidget(summary)

        outer.addWidget(self._build_workspace(), 1)

        composer = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText("Type a message and press Enter to send")
        self.message.returnPressed.connect(self._transmit)
        composer.addWidget(self.message, 1)
        self.transmit_button = QPushButton("SEND")
        self.transmit_button.setObjectName("primary")
        self.transmit_button.setEnabled(False)
        self.transmit_button.clicked.connect(self._transmit)
        composer.addWidget(self.transmit_button)
        outer.addLayout(composer)

        self._build_message_docks()

    def _build_setup_dialog(self) -> None:
        self.setup_dialog = QDialog(self)
        self.setup_dialog.setWindowTitle("Aurora Setup")
        self.setup_dialog.resize(560, 430)
        dialog_layout = QVBoxLayout(self.setup_dialog)
        tabs = QTabWidget()
        dialog_layout.addWidget(tabs)

        station_tab = QWidget()
        station_form = QFormLayout(station_tab)
        self.callsign = QLineEdit("N4EAC")
        self.callsign.textChanged.connect(self._station_identity_changed)
        self.grid = QLineEdit()
        station_form.addRow("Callsign", self.callsign)
        station_form.addRow("Grid", self.grid)
        tabs.addTab(station_tab, "Station ID")

        cat_tab = QWidget()
        cat_layout = QVBoxLayout(cat_tab)
        cat_form = QFormLayout()
        self.hamlib_model = QComboBox()
        for model in self._radio_models:
            self.hamlib_model.addItem(model.display_name, model.model_id)
        default_model = self.hamlib_model.findData(3073)
        if default_model >= 0:
            self.hamlib_model.setCurrentIndex(default_model)
        self.cat_device = QComboBox()
        self.cat_device.setEditable(True)
        self.cat_device.addItems(port.device for port in list_serial_ports())
        self.cat_baud = QComboBox()
        self.cat_baud.addItems(("4800", "9600", "19200", "38400", "57600", "115200"))
        self.cat_baud.setCurrentText("9600")
        self.external_hamlib = QCheckBox("Use external rigctld")
        self.hamlib_host = QLineEdit("127.0.0.1")
        self.hamlib_port = QSpinBox()
        self.hamlib_port.setRange(1, 65_535)
        self.hamlib_port.setValue(4_532)
        cat_form.addRow("Radio", self.hamlib_model)
        cat_form.addRow("CAT device", self.cat_device)
        cat_form.addRow("Baud", self.cat_baud)
        cat_form.addRow(self.external_hamlib)
        cat_form.addRow("External host", self.hamlib_host)
        cat_form.addRow("rigctld port", self.hamlib_port)
        cat_layout.addLayout(cat_form)
        self.cat_button = QPushButton("CONNECT HAMLIB")
        self.cat_button.clicked.connect(self._toggle_cat)
        cat_layout.addWidget(self.cat_button)
        self.apply_radio_button = QPushButton("APPLY FREQUENCY / MODE")
        self.apply_radio_button.setEnabled(False)
        self.apply_radio_button.clicked.connect(self._apply_radio_settings)
        cat_layout.addWidget(self.apply_radio_button)
        self.ptt_arm = QCheckBox("PTT Control")
        self.ptt_arm.setChecked(True)
        self.ptt_arm.toggled.connect(self._ptt_arm_changed)
        cat_layout.addWidget(self.ptt_arm)
        cat_layout.addStretch()
        tabs.addTab(cat_tab, "CAT Control")

        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        audio_form = QFormLayout()
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        audio_form.addRow("Radio input", self.input_device)
        audio_form.addRow("Radio output", self.output_device)
        audio_layout.addLayout(audio_form)
        refresh = QPushButton("REFRESH AUDIO DEVICES")
        refresh.clicked.connect(self._refresh_audio)
        audio_layout.addWidget(refresh)
        self.rx_button = QPushButton("START SPECTRUM RX")
        self.rx_button.clicked.connect(self._toggle_receiver)
        audio_layout.addWidget(self.rx_button)
        audio_layout.addStretch()
        tabs.addTab(audio_tab, "Audio")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.setup_dialog.accept)
        dialog_layout.addWidget(buttons)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.setMenuRole(QAction.NoRole)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        setup_menu = self.menuBar().addMenu("Setup")
        setup_action = QAction("Setup…", self)
        setup_action.setMenuRole(QAction.NoRole)
        setup_action.triggered.connect(self.setup_dialog.show)
        setup_menu.addAction(setup_action)

        view_menu = self.menuBar().addMenu("Theme")
        for theme_name in THEMES:
            action = QAction(theme_name, self)
            action.triggered.connect(
                lambda checked=False, name=theme_name: self._apply_theme(name)
            )
            view_menu.addAction(action)

        help_menu = self.menuBar().addMenu("About")
        about_action = QAction("About Aurora", self)
        about_action.setMenuRole(QAction.NoRole)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_message_docks(self) -> None:
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.messages_dock = QDockWidget("Messages", self)
        self.messages_dock.setObjectName("messagesDock")
        self.messages_dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.messages_dock.setWidget(self.history)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.messages_dock)

        self.other_signals = QTableWidget(0, 3)
        self.other_signals.setHorizontalHeaderLabels(("Frequency", "Callsign", "Message"))
        self.other_signals.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.other_signals_dock = QDockWidget("Other Signals", self)
        self.other_signals_dock.setObjectName("otherSignalsDock")
        self.other_signals_dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.other_signals_dock.setWidget(self.other_signals)
        self.addDockWidget(Qt.RightDockWidgetArea, self.other_signals_dock)

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        tuning = QHBoxLayout()
        tuning.addWidget(QLabel("Audio TX/RX"))
        self.frequency = QSpinBox()
        self.frequency.setRange(100, 3_000)
        self.frequency.setSingleStep(100)
        self.frequency.setValue(1_500)
        self.frequency.setSuffix(" Hz")
        self.frequency.valueChanged.connect(self._frequency_changed)
        tuning.addWidget(self.frequency)
        tuning.addStretch()
        layout.addLayout(tuning)
        layout.addWidget(QLabel("SIGNAL SPECTRUM • click to tune"))
        self.spectrum = SpectrumWidget()
        self.spectrum.frequency_selected.connect(self.frequency.setValue)
        layout.addWidget(self.spectrum, 1)
        layout.addWidget(QLabel("WATERFALL"))
        self.waterfall = WaterfallWidget()
        layout.addWidget(self.waterfall)
        return workspace

    def _frequency_changed(self, frequency_hz: int) -> None:
        self.spectrum.set_frequency(frequency_hz)

    def _station_identity_changed(self, callsign: str) -> None:
        self.callsign_display.setText(callsign.strip().upper() or "NOT SET")

    def _set_diagnostic(self, name: str, value: str) -> None:
        self.diagnostics[name].setText(f"{name}: {value}")

    def _apply_theme(self, name: str) -> None:
        """Apply and remember one of Aurora's operator display themes."""
        global BACKGROUND, FIELD, BORDER, FOREGROUND, MUTED, ACCENT, BLUE
        selected = name if name in THEMES else "Dark"
        colors = THEMES[selected]
        BACKGROUND, FIELD, BORDER, FOREGROUND, MUTED, ACCENT, BLUE = map(QColor, colors)
        QApplication.instance().setStyleSheet(_stylesheet(selected))
        self.preferences.setValue("appearance/theme", selected)
        self.spectrum.update()
        self.waterfall.update()

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Aurora",
            f"{APPLICATION_VERSION}\n\nby N4EAC, EDUARDO",
            QMessageBox.Ok,
        )

    @staticmethod
    def _stored_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        return str(value).lower() in {"1", "true", "yes"}

    def _restore_preferences(self) -> None:
        """Restore operator, radio, audio, theme, geometry, and dock settings."""
        p = self.preferences
        self.callsign.setText(str(p.value("station/callsign", "N4EAC")))
        self.grid.setText(str(p.value("station/grid", "")))
        self.frequency.setValue(int(p.value("signal/audio_frequency_hz", 1_500)))
        self.bandwidth.setCurrentText(str(p.value("signal/bandwidth", "AUTO")))
        self.radio_frequency.setValue(int(p.value("radio/frequency_hz", 14_074_000)))
        self.radio_mode.setCurrentText(str(p.value("radio/mode", "USB-D")))
        model_index = self.hamlib_model.findData(int(p.value("cat/model_id", 3073)))
        if model_index >= 0:
            self.hamlib_model.setCurrentIndex(model_index)
        self.cat_device.setCurrentText(str(p.value("cat/device", self.cat_device.currentText())))
        self.cat_baud.setCurrentText(str(p.value("cat/baud", "9600")))
        self.external_hamlib.setChecked(self._stored_bool(p.value("cat/external"), False))
        self.hamlib_host.setText(str(p.value("cat/host", "127.0.0.1")))
        self.hamlib_port.setValue(int(p.value("cat/port", 4_532)))
        self.ptt_arm.setChecked(self._stored_bool(p.value("cat/ptt_control"), True))
        self.input_device.setCurrentText(str(p.value("audio/input", self.input_device.currentText())))
        self.output_device.setCurrentText(str(p.value("audio/output", self.output_device.currentText())))
        self._apply_theme(str(p.value("appearance/theme", "Dark")))
        geometry = p.value("window/geometry")
        dock_state = p.value("window/dock_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if dock_state is not None:
            self.restoreState(dock_state)

    def _save_preferences(self) -> None:
        """Persist all operator-adjustable settings and window layout."""
        p = self.preferences
        values = {
            "station/callsign": self.callsign.text().strip().upper(),
            "station/grid": self.grid.text().strip().upper(),
            "signal/audio_frequency_hz": self.frequency.value(),
            "signal/bandwidth": self.bandwidth.currentText(),
            "radio/frequency_hz": self.radio_frequency.value(),
            "radio/mode": self.radio_mode.currentText(),
            "cat/model_id": self.hamlib_model.currentData(),
            "cat/device": self.cat_device.currentText(),
            "cat/baud": self.cat_baud.currentText(),
            "cat/external": self.external_hamlib.isChecked(),
            "cat/host": self.hamlib_host.text().strip(),
            "cat/port": self.hamlib_port.value(),
            "cat/ptt_control": self.ptt_arm.isChecked(),
            "audio/input": self.input_device.currentText(),
            "audio/output": self.output_device.currentText(),
            "window/geometry": self.saveGeometry(),
            "window/dock_state": self.saveState(),
        }
        for key, value in values.items():
            p.setValue(key, value)
        p.sync()

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
        self._set_diagnostic("SNR", f"Input {peak:.3f}")

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
        previous_input = self.input_device.currentText()
        previous_output = self.output_device.currentText()
        try:
            inputs = list_audio_devices("input")
            outputs = list_audio_devices("output")
        except Exception as error:
            self._append(f"[AUDIO ERROR] {error}")
            return
        self._input_devices = {f"{item.index}: {item.name}": item for item in inputs}
        self.input_device.clear()
        self.input_device.addItems(self._input_devices)
        if previous_input in self._input_devices:
            self.input_device.setCurrentText(previous_input)
        selected_input = next(iter(self._input_devices.values()), None)
        compatible = () if selected_input is None else compatible_outputs(selected_input, outputs)
        self._output_devices = {f"{item.index}: {item.name}": item for item in compatible}
        self.output_device.clear()
        self.output_device.addItems(self._output_devices)
        if previous_output in self._output_devices:
            self.output_device.setCurrentText(previous_output)

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
            self._set_diagnostic("Sync", "LOCKED")
            self._set_diagnostic("Offset", f"{event.frequency_offset_hz:+.2f} Hz")
            self._set_diagnostic("CRC", "PASS")
            self._set_diagnostic("FEC", "CORRECTED")
        self._poll_cat_events()

    def _toggle_cat(self) -> None:
        if self._hamlib is not None:
            self._disconnect_cat()
            return
        self.cat_button.setEnabled(False)
        external = self.external_hamlib.isChecked()
        host = self.hamlib_host.text() if external else "127.0.0.1"
        port = self.hamlib_port.value()
        model = int(self.hamlib_model.currentData())
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
        self._set_diagnostic("Sync", f"CAT {state}")
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
                    f"[CAT] {source.title()} Hamlib connected; PTT control "
                    f"{'enabled' if self.ptt_arm.isChecked() else 'disabled'}."
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
        self._save_preferences()
        self._display_timer.stop()
        self._event_timer.stop()
        self._cat_timer.stop()
        if self._stream is not None:
            self._stop_receiver()
        if self._hamlib is not None:
            self._disconnect_cat()
        self.session_log.close()
        event.accept()


def _stylesheet(theme_name: str = "Dark") -> str:
    background, field, border, foreground, muted, accent, blue = THEMES[theme_name]
    return f"""
        QWidget {{ background: {background}; color: {foreground}; font-size: 12px; }}
        QFrame#panel {{ background: {field}; border: 1px solid {border}; border-radius: 6px; }}
        QLabel#title {{ font-size: 25px; font-weight: 700; }}
        QLabel#badge {{ background: {field}; color: {blue}; padding: 7px 11px; border-radius: 4px; }}
        QLabel#value {{ color: {accent}; font-family: monospace; font-weight: 600; }}
        QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget {{ background: {field}; border: 1px solid {border}; padding: 5px; }}
        QPushButton {{ background: {field}; border: 1px solid {border}; padding: 7px; border-radius: 4px; }}
        QPushButton:hover {{ border-color: {accent}; }}
        QPushButton#primary {{ background: {border}; border-color: {accent}; font-weight: 700; }}
        QTabBar::tab {{ background: {field}; padding: 7px 12px; }}
        QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
    """


def run(settings: AppSettings = SETTINGS) -> None:
    """Start the responsive Qt Aurora interface."""
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Aurora")
    application.setOrganizationName("N4EAC")
    application.setStyle("Fusion")
    application.setStyleSheet(_stylesheet())
    window = AuroraQtWindow(settings)
    window.show()
    application.exec()
