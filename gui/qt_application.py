"""Responsive PySide6 operator interface for Aurora."""

from __future__ import annotations

import sys
import queue
import secrets
import threading

import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt, QTimer
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
    QMenu,
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
from audio.multichannel_receiver import (
    MultichannelAudioReceiver,
    mode_at_frequency,
)
from audio.playback import condition_playback, play_audio, stop_playback
from audio.streaming import AudioInputStream, AudioStreamStatus
from dsp.spectrum import SpectrumFrame, compute_spectrum
from dsp.transmit_quality import validate_transmit_audio
from dsp.waveform import modulate_audio
from modem.bandwidth_adaptation import fixed_bandwidth
from modem.chat_transport import encode_chat_air_transmission
from modem.message_templates import CANNED_MESSAGES, expand_message_template
from modem.station_data import StationData, encode_station_air_transmission
from radio.hamlib_control import HamlibController
from radio.bundled_hamlib import BundledHamlibConfig, BundledHamlibService
from radio.hamlib_models import list_radio_models
from radio.audio_tuning import MODEM_AUDIO_CENTER_HZ, dial_frequency_for_audio_center
from radio.device import list_serial_ports
from gui.frequency_control import DigitFrequencySpinBox
from util.session_debug_log import SessionDebugLog
from util.application_version import APPLICATION_VERSION


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
    """Efficient receive spectrum with Aurora's fixed modem-center marker."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(110)
        self._frame: SpectrumFrame | None = None
        self._selected_hz = MODEM_AUDIO_CENTER_HZ

    def set_frame(self, frame: SpectrumFrame) -> None:
        """Replace the spectrum data and schedule a repaint."""
        self._frame = frame
        self.update()

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
        painter.drawText(int(marker_x) + 5, 14, f"MODEM CENTER {self._selected_hz} Hz")
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
        self._radio_tune_timer = QTimer(self)
        self._radio_tune_timer.setSingleShot(True)
        self._radio_tune_timer.setInterval(180)
        self._radio_tune_timer.timeout.connect(self._apply_tuned_radio_frequency)
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
        self.radio_frequency = DigitFrequencySpinBox()
        self.radio_frequency.setToolTip(
            "Click a digit, use the mouse wheel or Up/Down to tune; Left/Right selects a digit"
        )
        self.radio_frequency.operatorFrequencyChanged.connect(
            self._schedule_radio_frequency
        )
        self.radio_mode = QComboBox()
        self.radio_mode.addItems(("USB-D", "USB", "LSB-D", "LSB", "CW", "CW-R"))
        self.callsign_display = QLabel("N4EAC")
        self.callsign_display.setObjectName("value")
        self.bandwidth = QComboBox()
        self.bandwidth.addItems(("AUTO", "500 Hz", "2.3 kHz", "2.8 kHz"))
        self.bandwidth.currentTextChanged.connect(self._bandwidth_changed)
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
        self._bandwidth_changed(self.bandwidth.currentText())

        composer = QHBoxLayout()
        self.canned_message = QComboBox()
        self.canned_message.addItems(CANNED_MESSAGES)
        self.canned_message.currentTextChanged.connect(self._select_canned_message)
        composer.addWidget(self.canned_message)
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
        self.operator_name = QLineEdit()
        self.callsign = QLineEdit("N4EAC")
        self.callsign.textChanged.connect(self._station_identity_changed)
        self.grid = QLineEdit()
        self.latitude = QLineEdit()
        self.longitude = QLineEdit()
        self.altitude = QLineEdit()
        station_form.addRow("Name", self.operator_name)
        station_form.addRow("Callsign", self.callsign)
        station_form.addRow("Grid", self.grid)
        station_form.addRow("Latitude (optional)", self.latitude)
        station_form.addRow("Longitude (optional)", self.longitude)
        station_form.addRow("Altitude m (optional)", self.altitude)
        self.station_data_button = QPushButton("SEND STATION DATA")
        self.station_data_button.setEnabled(False)
        self.station_data_button.clicked.connect(self._send_station_data)
        station_form.addRow(self.station_data_button)
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
        self.other_signals.setSelectionBehavior(QTableWidget.SelectRows)
        self.other_signals.setContextMenuPolicy(Qt.CustomContextMenu)
        self.other_signals.customContextMenuRequested.connect(
            self._show_other_signal_menu
        )
        self.other_signals.cellDoubleClicked.connect(
            lambda row, column: self._tune_to_other_signal(row, prepare_contact=True)
        )
        self.other_signals.setToolTip(
            "Right-click a station for tuning options; double-click to prepare contact"
        )
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
        tuning.addWidget(QLabel("Aurora modem center"))
        center = QLabel(f"{MODEM_AUDIO_CENTER_HZ} Hz • fixed")
        center.setObjectName("value")
        tuning.addWidget(center)
        tuning.addStretch()
        layout.addLayout(tuning)
        layout.addWidget(QLabel("RECEIVE SPECTRUM • monitoring 100–3000 Hz"))
        self.spectrum = SpectrumWidget()
        layout.addWidget(self.spectrum, 1)
        layout.addWidget(QLabel("WATERFALL"))
        self.waterfall = WaterfallWidget()
        layout.addWidget(self.waterfall)
        return workspace

    def _bandwidth_changed(self, selection: str) -> None:
        """Describe the occupied region for the fixed-center profile."""
        del selection
        half_width = self._selected_mode().occupied_bandwidth_hz // 2
        self.spectrum.setToolTip(
            f"Selected profile occupies approximately "
            f"{MODEM_AUDIO_CENTER_HZ - half_width}–{MODEM_AUDIO_CENTER_HZ + half_width} Hz"
        )

    def _station_identity_changed(self, callsign: str) -> None:
        self.callsign_display.setText(callsign.strip().upper() or "NOT SET")

    def _select_canned_message(self, selection: str) -> None:
        template = CANNED_MESSAGES.get(selection, "")
        if template:
            self.message.setText(template)
            self.message.setFocus()

    def _expanded_message(self) -> str:
        return expand_message_template(
            self.message.text(),
            name=self.operator_name.text(),
            callsign=self.callsign.text(),
        )

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
        self.operator_name.setText(str(p.value("station/name", "")))
        self.callsign.setText(str(p.value("station/callsign", "N4EAC")))
        self.grid.setText(str(p.value("station/grid", "")))
        self.latitude.setText(str(p.value("station/latitude", "")))
        self.longitude.setText(str(p.value("station/longitude", "")))
        self.altitude.setText(str(p.value("station/altitude", "")))
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
            "station/name": self.operator_name.text().strip(),
            "station/callsign": self.callsign.text().strip().upper(),
            "station/grid": self.grid.text().strip().upper(),
            "station/latitude": self.latitude.text().strip(),
            "station/longitude": self.longitude.text().strip(),
            "station/altitude": self.altitude.text().strip(),
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
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, int(frequency_hz))
            item.setData(Qt.UserRole + 1, callsign)
            self.other_signals.setItem(0, column, item)

    def _show_other_signal_menu(self, position) -> None:
        """Offer safe operator actions for one decoded off-frequency station."""
        item = self.other_signals.itemAt(position)
        if item is None:
            return
        row = item.row()
        callsign = self.other_signals.item(row, 1).text()
        menu = QMenu(self.other_signals)
        tune = menu.addAction(f"Tune to {callsign}")
        prepare = menu.addAction(f"Tune and Prepare Contact with {callsign}")
        selected = menu.exec(self.other_signals.viewport().mapToGlobal(position))
        if selected == tune:
            self._tune_to_other_signal(row, prepare_contact=False)
        elif selected == prepare:
            self._tune_to_other_signal(row, prepare_contact=True)

    def _tune_to_other_signal(self, row: int, *, prepare_contact: bool) -> None:
        """Retune the radio to center a decoded station and prepare a reply."""
        frequency_item = self.other_signals.item(row, 0)
        callsign_item = self.other_signals.item(row, 1)
        if frequency_item is None or callsign_item is None:
            return
        frequency = int(frequency_item.data(Qt.UserRole))
        callsign = callsign_item.text().strip().upper()
        if self._hamlib is None:
            self._append(f"[TUNE BLOCKED] Connect Hamlib to tune to {callsign}.")
            return
        try:
            dial_frequency = dial_frequency_for_audio_center(
                self.radio_frequency.value(), frequency, self.radio_mode.currentText()
            )
        except ValueError as error:
            self._append(f"[TUNE BLOCKED] {error}")
            return
        self.radio_frequency.setValue(dial_frequency)
        self._request_radio_frequency(
            dial_frequency,
            f"{callsign} from {frequency} Hz to {MODEM_AUDIO_CENTER_HZ} Hz",
        )
        self.messages_dock.raise_()
        if prepare_contact:
            self.canned_message.setCurrentText("Custom")
            self.message.setText(f"{callsign} de <CALL>")
            self.message.setFocus()
            self._append(
                f"[CONTACT] Centering {callsign} from {frequency} Hz; reply prepared."
            )
        else:
            self._append(
                f"[TUNE] Centering {callsign} from {frequency} Hz at "
                f"{dial_frequency} Hz dial."
            )

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
            if event.message is not None and event.frequency_hz == MODEM_AUDIO_CENTER_HZ:
                self._append(
                    f"[RX {event.frequency_hz} Hz/{event.message.callsign}] "
                    f"{event.message.text}"
                )
            elif event.message is not None:
                self.add_other_signal(
                    event.frequency_hz, event.message.callsign, event.message.text
                )
            elif event.station is not None:
                station = event.station.data
                location = station.grid or "station update"
                if station.latitude is not None:
                    location = f"GPS {station.latitude:+.5f}, {station.longitude:+.5f}"
                self.add_other_signal(event.frequency_hz, station.callsign, location)
            elif event.report is not None:
                report = event.report
                self.add_other_signal(
                    event.frequency_hz,
                    report.reporter,
                    f"Report #{report.referenced_frame_id}: {report.snr_db:+.1f} dB SNR",
                )
            self._set_diagnostic("Sync", "LOCKED")
            self._set_diagnostic("Offset", f"{event.frequency_offset_hz:+.2f} Hz")
            self._set_diagnostic("Timing", f"{event.timing_offset_samples:.2f} samples")
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
        self.station_data_button.setEnabled(False)
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

    def _schedule_radio_frequency(self, frequency_hz: int) -> None:
        """Debounce operator wheel/key tuning before issuing a Hamlib command."""
        del frequency_hz
        self._radio_tune_timer.start()

    def _apply_tuned_radio_frequency(self) -> None:
        """Apply the operator-selected dial frequency through Hamlib."""
        if self._hamlib is None:
            self._append("[TUNE BLOCKED] Connect Hamlib to tune the radio.")
            return
        self._request_radio_frequency(self.radio_frequency.value(), "operator tuning")

    def _request_radio_frequency(self, frequency_hz: int, reason: str) -> None:
        """Set only the radio dial frequency without changing mode or passband."""
        controller = self._hamlib
        if controller is None:
            return

        def worker() -> None:
            try:
                controller.set_frequency(frequency_hz)
                self._cat_events.put(("frequency_applied", frequency_hz, reason))
            except Exception as error:
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraHamlibTune", daemon=True).start()

    def _ptt_arm_changed(self, armed: bool) -> None:
        self.transmit_button.setEnabled(armed and self._hamlib is not None)
        self.station_data_button.setEnabled(armed and self._hamlib is not None)

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
                self.station_data_button.setEnabled(self.ptt_arm.isChecked())
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
            elif kind == "frequency_applied":
                self._append(f"[CAT] Tuned to {values[0]} Hz ({values[1]}).")
            elif kind == "tx_complete":
                self.transmit_button.setEnabled(self.ptt_arm.isChecked())
                self.station_data_button.setEnabled(self.ptt_arm.isChecked())
                if values[0] is not None:
                    self._append(f"[TX ERROR] {values[0]}")
            elif kind == "cat_error":
                self.cat_button.setEnabled(True)
                self._append(f"[CAT ERROR] {values[0]}")

    def _build_transmit_audio(self, message_text: str | None = None) -> AudioBuffer:
        """Build conditioned radio audio for the current operator message."""
        mode = mode_at_frequency(self._selected_mode(), MODEM_AUDIO_CENTER_HZ)
        transmission = encode_chat_air_transmission(
            self.callsign.text(), message_text or self._expanded_message(), mode=mode
        )
        waveform = modulate_audio(
            transmission.symbols,
            mode,
            leading_silence_samples=self.settings.audio_sample_rate // 5,
        )
        conditioned = condition_playback(
            waveform,
            gain=0.55,
            fade_seconds=0.02,
            trailing_silence_seconds=0.10,
        )
        validate_transmit_audio(conditioned)
        return conditioned

    def _send_station_data(self) -> None:
        """Send optional location as a separate AX.25 station-data frame."""
        if self._hamlib is None or not self.ptt_arm.isChecked():
            self._append("[TX BLOCKED] Connect Hamlib and enable PTT Control.")
            return
        try:
            latitude_text = self.latitude.text().strip()
            longitude_text = self.longitude.text().strip()
            altitude_text = self.altitude.text().strip()
            station = StationData(
                self.callsign.text(),
                grid=self.grid.text().strip() or None,
                latitude=float(latitude_text) if latitude_text else None,
                longitude=float(longitude_text) if longitude_text else None,
                altitude_m=float(altitude_text) if altitude_text else None,
            )
            mode = mode_at_frequency(self._selected_mode(), MODEM_AUDIO_CENTER_HZ)
            transmission = encode_station_air_transmission(
                station,
                frame_id=secrets.randbits(32),
                mode=mode,
            )
            waveform = modulate_audio(
                transmission.symbols,
                mode,
                leading_silence_samples=self.settings.audio_sample_rate // 5,
            )
            audio = condition_playback(
                waveform,
                gain=0.55,
                fade_seconds=0.02,
                trailing_silence_seconds=0.10,
            )
            validate_transmit_audio(audio)
            output = self._output_devices[self.output_device.currentText()]
        except Exception as error:
            self._append(f"[STATION DATA ERROR] {error}")
            return
        self._start_radio_playback(audio, output.index)
        location = station.grid or "location omitted"
        if station.latitude is not None:
            location = "GPS included"
        self._append(f"[TX AX.25/{station.callsign}] {location}")

    def _start_radio_playback(self, audio: AudioBuffer, output_index: int) -> None:
        """Key PTT and play one already-conditioned Aurora transmission."""
        self.transmit_button.setEnabled(False)
        self.station_data_button.setEnabled(False)

        def worker() -> None:
            try:
                self._hamlib.set_ptt(True)
                play_audio(audio, blocking=True, device=output_index)
                self._cat_events.put(("tx_complete", None))
            except Exception as error:
                self._cat_events.put(("tx_complete", error))
            finally:
                try:
                    self._hamlib.set_ptt(False)
                except Exception as error:
                    self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraRadioTransmit", daemon=True).start()

    def _transmit(self) -> None:
        if self._hamlib is None or not self.ptt_arm.isChecked():
            self._append("[TX BLOCKED] Connect Hamlib and explicitly arm PTT.")
            return
        try:
            output = self._output_devices[self.output_device.currentText()]
            expanded_message = self._expanded_message()
            audio = self._build_transmit_audio(expanded_message)
        except Exception as error:
            self._append(f"[AUDIO TX ERROR] {error}")
            return
        self._start_radio_playback(audio, output.index)
        self._append(
            f"[TX {MODEM_AUDIO_CENTER_HZ} Hz/{self.callsign.text()}] "
            f"{expanded_message}"
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
