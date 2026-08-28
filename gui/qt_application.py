"""Responsive PySide6 operator interface for Aurora."""

from __future__ import annotations

import sys
import queue
import secrets
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QImage,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QTextCharFormat,
    QTextCursor,
)
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
    QSlider,
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
from audio.adaptive_receiver import AdaptiveBandwidthAudioReceiver
from audio.device import compatible_outputs, list_audio_devices
from audio.multichannel_receiver import mode_at_frequency
from audio.playback import condition_playback, play_audio, stop_playback
from audio.streaming import AudioInputStream, AudioStreamStatus
from dsp.spectrum import SpectrumFrame, compute_spectrum
from dsp.transmit_quality import TransmitQualityReport, validate_transmit_audio
from dsp.ofdm import config_for_mode
from dsp.waveform import modulate_audio
from modem.bandwidth_adaptation import fixed_bandwidth
from modem.chat_transport import encode_chat_air_transmission
from modem.message_templates import CANNED_MESSAGES, prepare_message_template
from modem.contact_session import (
    DEFAULT_REPLY_WINDOW_SECONDS,
    ContactManager,
    TurnState,
)
from modem.station_data import StationData, encode_station_air_transmission
from radio.hamlib_control import DEFAULT_RADIO_PASSBAND_HZ, HamlibController
from radio.bundled_hamlib import BundledHamlibConfig, BundledHamlibService
from radio.hamlib_models import list_radio_models
from radio.audio_tuning import MODEM_AUDIO_CENTER_HZ, dial_frequency_for_audio_center
from radio.device import list_serial_ports
from radio.split_control import FakeSplitController
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
MAX_TX_AUDIO_GAIN = 0.55
TX_DRIVE_SCALE_VERSION = 2

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


class ConstellationWidget(QWidget):
    """Read-only equalized-symbol constellation for decoded Aurora frames."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(150)
        self._symbols: tuple[complex, ...] = ()

    def set_symbols(self, symbols: tuple[complex, ...]) -> None:
        self._symbols = symbols[-500:]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), FIELD)
        center_x, center_y = self.width() / 2.0, self.height() / 2.0
        painter.setPen(QPen(BORDER, 1))
        painter.drawLine(0, int(center_y), self.width(), int(center_y))
        painter.drawLine(int(center_x), 0, int(center_x), self.height())
        if not self._symbols:
            painter.setPen(MUTED)
            painter.drawText(self.rect(), Qt.AlignCenter, "Awaiting decoded OFDM symbols")
            return
        scale = max(min(self.width(), self.height()) * 0.34, 1.0)
        painter.setPen(QPen(ACCENT, 3))
        for symbol in self._symbols:
            x = center_x + max(-1.4, min(1.4, symbol.real)) * scale / 1.4
            y = center_y - max(-1.4, min(1.4, symbol.imag)) * scale / 1.4
            painter.drawPoint(QPointF(x, y))


class SubcarrierQualityWidget(QWidget):
    """Read-only relative quality bars for the last decoded OFDM frame."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(120)
        self._quality: tuple[float, ...] = ()

    def set_quality(self, quality: tuple[float, ...]) -> None:
        self._quality = quality
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), FIELD)
        if not self._quality:
            painter.setPen(MUTED)
            painter.drawText(self.rect(), Qt.AlignCenter, "Awaiting decoded OFDM frame")
            return
        width = self.width() / len(self._quality)
        for index, value in enumerate(self._quality):
            height = max(1.0, min(1.0, value) * (self.height() - 8))
            painter.fillRect(
                int(index * width) + 1,
                int(self.height() - height),
                max(1, int(width) - 2),
                int(height),
                ACCENT,
            )


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
        self._receiver: AdaptiveBandwidthAudioReceiver | None = None
        self._stream: AudioInputStream | None = None
        self._hamlib: HamlibController | None = None
        self._hamlib_service: BundledHamlibService | None = None
        self._last_cat_status: tuple[int, str, int, bool] | None = None
        self._contacts = ContactManager()
        self._target_callsign = ""
        self._target_name = ""
        self._cat_request_pending = False
        self._operator_tune_pending = False
        self._auto_cat_connect_pending = False
        self._startup_radio_settings: tuple[int, str] | None = None
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
        if self._should_restore_cat_automatically():
            self._startup_radio_settings = (
                self.radio_frequency.value(),
                self.radio_mode.currentText(),
            )
            QTimer.singleShot(250, self._restore_cat_automatically)
        if self.preferences.contains("audio/input"):
            QTimer.singleShot(400, self._restore_audio_automatically)

    def _build_ui(self) -> None:
        self._build_setup_dialog()
        self._build_diagnostics_window()
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
            "Type a frequency and press Enter, or click a digit and use the mouse wheel or "
            "Up/Down; Left/Right selects a digit. Short entries are kHz: 7117 becomes "
            "7,117,000 Hz and 7117.5 becomes 7,117,500 Hz"
        )
        self.radio_frequency.operatorFrequencyChanged.connect(
            self._operator_radio_frequency_changed
        )
        self.radio_frequency.lineEdit().textEdited.connect(
            self._preview_reply_frequency
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
            ("TX bandwidth", self.bandwidth),
        ):
            operating_row.addWidget(QLabel(label))
            operating_row.addWidget(widget)
        operating_row.addStretch()
        summary_layout.addLayout(operating_row)
        outer.addWidget(summary)

        outer.addWidget(self._build_workspace())
        self._bandwidth_changed(self.bandwidth.currentText())

        composer = QHBoxLayout()
        self.canned_message = QComboBox()
        self.canned_message.addItems(CANNED_MESSAGES)
        self.canned_message.currentTextChanged.connect(self._select_canned_message)
        composer.addWidget(self.canned_message)
        self.after_send = QComboBox()
        self.after_send.addItems(("Continue", "Back to You", "End Contact"))
        self.after_send.setToolTip("One-shot action applied to this transmission")
        composer.addWidget(self.after_send)
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
        rx_level_row = QHBoxLayout()
        self.rx_audio_level = QSlider(Qt.Horizontal)
        self.rx_audio_level.setRange(10, 200)
        self.rx_audio_level.setValue(100)
        self.rx_audio_level.setToolTip(
            "Software gain applied after audio capture; this does not change the "
            "radio or operating-system input control."
        )
        self.rx_audio_level_value = QLabel("100%")
        self.rx_audio_level.valueChanged.connect(
            lambda value: self.rx_audio_level_value.setText(f"{value}%")
        )
        rx_level_row.addWidget(self.rx_audio_level, 1)
        rx_level_row.addWidget(self.rx_audio_level_value)
        audio_form.addRow("RX audio level", rx_level_row)
        tx_level_row = QHBoxLayout()
        self.tx_audio_level = QSlider(Qt.Horizontal)
        self.tx_audio_level.setRange(10, 100)
        self.tx_audio_level.setValue(100)
        self.tx_audio_level.setToolTip(
            "Generated Aurora audio amplitude; this does not change RF power."
        )
        self.tx_audio_level_value = QLabel("100%")
        self.tx_audio_level.valueChanged.connect(
            lambda value: self.tx_audio_level_value.setText(f"{value}%")
        )
        tx_level_row.addWidget(self.tx_audio_level, 1)
        tx_level_row.addWidget(self.tx_audio_level_value)
        audio_form.addRow("TX audio drive", tx_level_row)
        audio_layout.addLayout(audio_form)
        self.tx_test_button = QPushButton("TUNE / TEST TX")
        self.tx_test_button.setEnabled(False)
        self.tx_test_button.clicked.connect(self._test_tx_audio)
        audio_layout.addWidget(self.tx_test_button)
        refresh = QPushButton("REFRESH AUDIO DEVICES")
        refresh.clicked.connect(self._refresh_audio)
        audio_layout.addWidget(refresh)
        self.rx_button = QPushButton("START AUDIO RX")
        self.rx_button.clicked.connect(self._toggle_receiver)
        audio_layout.addWidget(self.rx_button)
        audio_layout.addStretch()
        tabs.addTab(audio_tab, "Audio")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.setup_dialog.accept)
        dialog_layout.addWidget(buttons)

    def _build_diagnostics_window(self) -> None:
        """Create the optional, read-only signal diagnostics window."""
        self.diagnostics_window = QDialog(self)
        self.diagnostics_window.setWindowTitle("Aurora Signal Diagnostics")
        self.diagnostics_window.resize(680, 560)
        layout = QVBoxLayout(self.diagnostics_window)
        form = QFormLayout()
        self.diagnostics: dict[str, QLabel] = {}
        for name, initial in (
            ("Sync", "SEARCHING"), ("SNR", "-- dB"), ("Frequency offset", "-- Hz"),
            ("Timing offset", "--"), ("CRC", "WAITING"),
            ("FEC corrections", "not available"),
        ):
            value = QLabel(initial)
            value.setObjectName("value")
            self.diagnostics[name] = value
            form.addRow(name, value)
        layout.addLayout(form)
        layout.addWidget(QLabel("GENERATED TX AUDIO"))
        tx_form = QFormLayout()
        self.tx_diagnostics: dict[str, QLabel] = {}
        for name, initial in (
            ("State", "IDLE"), ("Audio drive", "100%"), ("Peak", "--"),
            ("RMS", "--"), ("Crest factor", "--"), ("Clipping", "--"),
            ("Linearity", "NOT TESTED"), ("Profile", "--"),
            ("Constellation", "ideal BPSK: −1 / +1"),
        ):
            value = QLabel(initial)
            value.setObjectName("value")
            self.tx_diagnostics[name] = value
            tx_form.addRow(name, value)
        layout.addLayout(tx_form)
        layout.addWidget(QLabel("EQUALIZED BPSK CONSTELLATION"))
        self.constellation = ConstellationWidget()
        layout.addWidget(self.constellation, 1)
        layout.addWidget(QLabel("PER-SUBCARRIER RELATIVE QUALITY"))
        self.subcarrier_quality = SubcarrierQualityWidget()
        layout.addWidget(self.subcarrier_quality, 1)

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

        view_menu = self.menuBar().addMenu("View")
        self.diagnostics_action = QAction("Signal Diagnostics", self)
        self.diagnostics_action.setCheckable(True)
        self.diagnostics_action.toggled.connect(self.diagnostics_window.setVisible)
        self.diagnostics_window.finished.connect(
            lambda result: self.diagnostics_action.setChecked(False)
        )
        view_menu.addAction(self.diagnostics_action)

        theme_menu = self.menuBar().addMenu("Theme")
        for theme_name in THEMES:
            action = QAction(theme_name, self)
            action.triggered.connect(
                lambda checked=False, name=theme_name: self._apply_theme(name)
            )
            theme_menu.addAction(action)

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
        layout.addWidget(QLabel("AUDIO ACTIVITY • 100–3000 Hz • DISPLAY ONLY"))
        self.waterfall = WaterfallWidget()
        layout.addWidget(self.waterfall)
        reply_row = QHBoxLayout()
        self.reply_channel_enabled = QPushButton("REPLY CHANNEL: OFF")
        self.reply_channel_enabled.setCheckable(True)
        self.reply_channel_enabled.setToolTip(
            "Arm this before SEND to advertise and listen on the Reply frequency"
        )
        self.reply_channel_enabled.toggled.connect(self._reply_offer_toggled)
        reply_row.addWidget(self.reply_channel_enabled)
        self.reply_frequency = DigitFrequencySpinBox()
        self.reply_frequency.setValue(14_074_000)
        self.reply_frequency.setToolTip(
            "Dial frequency where you will listen for replies; short entries are kHz"
        )
        reply_row.addWidget(self.reply_frequency)
        self.reply_window = QSpinBox()
        self.reply_window.setRange(30, 600)
        self.reply_window.setValue(DEFAULT_REPLY_WINDOW_SECONDS)
        self.reply_window.setSuffix(" s")
        reply_row.addWidget(self.reply_window)
        self.return_normal_button = QPushButton("RETURN TO NORMAL")
        self.return_normal_button.setEnabled(False)
        self.return_normal_button.clicked.connect(self._return_to_normal_operation)
        reply_row.addWidget(self.return_normal_button)
        self.contact_status = QLabel("SIMPLEX")
        self.contact_status.setObjectName("value")
        reply_row.addWidget(self.contact_status)
        layout.addLayout(reply_row)
        return workspace

    def _bandwidth_changed(self, selection: str) -> None:
        """Describe the occupied region for the fixed-center profile."""
        del selection
        half_width = self._selected_mode().occupied_bandwidth_hz // 2
        self.waterfall.setToolTip(
            f"Selected profile occupies approximately "
            f"{MODEM_AUDIO_CENTER_HZ - half_width}–{MODEM_AUDIO_CENTER_HZ + half_width} Hz"
        )

    def _reply_offer_toggled(self, enabled: bool) -> None:
        """Arm a Reply offer or cancel its active split when switched off."""
        self.reply_channel_enabled.setText(
            "REPLY CHANNEL: ARMED" if enabled else "REPLY CHANNEL: OFF"
        )
        if enabled and self.reply_frequency.value() == self.radio_frequency.value():
            self.reply_channel_enabled.setChecked(False)
            self.contact_status.setText("REPLY FREQUENCY MUST DIFFER")
            self._append(
                "[REPLY CHANNEL BLOCKED] Reply frequency cannot equal the main "
                "frequency. Leave Reply Channel off for simplex operation."
            )
            return
        if not enabled and self._contacts.active is not None:
            self._return_to_normal_operation()
            return
        if self._contacts.active is None:
            self.contact_status.setText("REPLY OFFER ARMED" if enabled else "SIMPLEX")

    def _station_identity_changed(self, callsign: str) -> None:
        self.callsign_display.setText(callsign.strip().upper() or "NOT SET")

    def _select_canned_message(self, selection: str) -> None:
        template = CANNED_MESSAGES.get(selection, "")
        if template:
            self.message.setText(template)
            self.message.setFocus()

    def _prepared_message(self):
        active = self._contacts.active
        split_frequency = None
        if active is not None:
            split_frequency = self.reply_frequency.value()
        elif self.reply_channel_enabled.isChecked():
            split_frequency = self.reply_frequency.value()
        return prepare_message_template(
            self.message.text(),
            name=self.operator_name.text(),
            callsign=self.callsign.text(),
            target_callsign=self._target_callsign,
            target_name=self._target_name,
            split_frequency_hz=split_frequency,
        )

    def _set_diagnostic(self, name: str, value: str) -> None:
        self.diagnostics[name].setText(value)

    def _apply_theme(self, name: str) -> None:
        """Apply and remember one of Aurora's operator display themes."""
        global BACKGROUND, FIELD, BORDER, FOREGROUND, MUTED, ACCENT, BLUE
        selected = name if name in THEMES else "Dark"
        colors = THEMES[selected]
        BACKGROUND, FIELD, BORDER, FOREGROUND, MUTED, ACCENT, BLUE = map(QColor, colors)
        QApplication.instance().setStyleSheet(_stylesheet(selected))
        self.preferences.setValue("appearance/theme", selected)
        self.waterfall.update()
        self.constellation.update()
        self.subcarrier_quality.update()

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

    def _should_restore_cat_automatically(self) -> bool:
        """Recognize successful CAT state and migrate complete legacy settings."""
        success = self.preferences.value("cat/last_success")
        if success is not None:
            return self._stored_bool(success, False)

        # Builds predating automatic CAT startup saved the working connection
        # fields but had no success marker. Treat an explicitly saved, complete
        # configuration as the migration signal; a successful connection will
        # then persist cat/last_success for subsequent launches.
        required = ("cat/model_id", "cat/baud", "cat/external")
        if not all(self.preferences.contains(key) for key in required):
            return False
        if self._stored_bool(self.preferences.value("cat/external"), False):
            return bool(str(self.preferences.value("cat/host", "")).strip())
        return bool(str(self.preferences.value("cat/device", "")).strip())

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
        # A Reply-To candidate is transient contact state. Never resurrect it
        # without an active contact after an application restart.
        self.reply_frequency.set_synchronized_value(self.radio_frequency.value())
        p.remove("contact/reply_frequency_hz")
        saved_reply_window = int(
            p.value("contact/reply_window_seconds", DEFAULT_REPLY_WINDOW_SECONDS)
        )
        # Migrate the former default while preserving other operator choices.
        if saved_reply_window == 120:
            saved_reply_window = DEFAULT_REPLY_WINDOW_SECONDS
        self.reply_window.setValue(saved_reply_window)
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
        self.rx_audio_level.setValue(int(p.value("audio/rx_level_percent", 100)))
        saved_tx_drive = int(p.value("audio/tx_drive_percent", 100))
        scale_version = int(p.value("audio/tx_drive_scale_version", 1))
        if scale_version < TX_DRIVE_SCALE_VERSION:
            # Preserve the actual gain from the former 10–55 raw-gain display.
            saved_tx_drive = round(saved_tx_drive / 55 * 100)
        self.tx_audio_level.setValue(saved_tx_drive)
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
            "contact/reply_window_seconds": self.reply_window.value(),
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
            "audio/rx_level_percent": self.rx_audio_level.value(),
            "audio/tx_drive_percent": self.tx_audio_level.value(),
            "audio/tx_drive_scale_version": TX_DRIVE_SCALE_VERSION,
            "window/geometry": self.saveGeometry(),
            "window/dock_state": self.saveState(),
        }
        for key, value in values.items():
            p.setValue(key, value)
        p.sync()

    def _append(self, text: str, *, chat: bool = False) -> None:
        """Append chat in normal text and system events in theme-safe color."""
        cursor = self.history.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.history.document().isEmpty():
            cursor.insertBlock()
        text_format = QTextCharFormat()
        text_format.setForeground(FOREGROUND if chat else BLUE)
        cursor.insertText(text, text_format)
        self.history.setTextCursor(cursor)
        self.history.ensureCursorVisible()

    def add_other_signal(
        self,
        frequency_hz: int,
        callsign: str,
        message: str,
        *,
        sender_name: str = "",
        contact_id: int = 0,
        reply_frequency_hz: int | None = None,
        reply_window_seconds: int = 0,
    ) -> None:
        """Insert an off-frequency CRC-valid decode into the activity list."""
        self.other_signals.insertRow(0)
        for column, value in enumerate((f"{frequency_hz} Hz", callsign, message)):
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, int(frequency_hz))
            item.setData(Qt.UserRole + 1, callsign)
            item.setData(Qt.UserRole + 2, reply_frequency_hz)
            item.setData(Qt.UserRole + 3, contact_id)
            item.setData(Qt.UserRole + 4, reply_window_seconds)
            item.setData(Qt.UserRole + 5, sender_name)
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
        reply_frequency = self.other_signals.item(row, 0).data(Qt.UserRole + 2)
        reply_action = None
        if reply_frequency:
            reply_action = menu.addAction(f"Reply to {callsign} on {reply_frequency} Hz")
        selected = menu.exec(self.other_signals.viewport().mapToGlobal(position))
        if selected == tune:
            self._tune_to_other_signal(row, prepare_contact=False)
        elif selected == prepare:
            self._tune_to_other_signal(row, prepare_contact=True)
        elif reply_action is not None and selected == reply_action:
            self._accept_reply_channel(row)

    def _accept_reply_channel(self, row: int) -> None:
        """Accept a decoded Reply-To offer only after explicit operator action."""
        item = self.other_signals.item(row, 0)
        callsign_item = self.other_signals.item(row, 1)
        if item is None or callsign_item is None or self._hamlib is None:
            self._append("[REPLY CHANNEL BLOCKED] Connect Hamlib and select a valid offer.")
            return
        audio_frequency = int(item.data(Qt.UserRole))
        reply_frequency = item.data(Qt.UserRole + 2)
        try:
            calling_frequency = dial_frequency_for_audio_center(
                self.radio_frequency.value(), audio_frequency, self.radio_mode.currentText()
            )
            session = self._contacts.accept(
                peer_callsign=callsign_item.text().strip().upper(),
                peer_name=str(item.data(Qt.UserRole + 5) or ""),
                contact_id=int(item.data(Qt.UserRole + 3) or 0),
                received_frequency_hz=calling_frequency,
                reply_frequency_hz=int(reply_frequency),
                normal_frequency_hz=self.radio_frequency.value(),
                mode=self.radio_mode.currentText(),
                window_seconds=int(item.data(Qt.UserRole + 4) or 120),
            )
        except (TypeError, ValueError) as error:
            self._append(f"[REPLY CHANNEL BLOCKED] {error}")
            return
        self._target_callsign = session.peer_callsign
        self._target_name = session.peer_name
        self.reply_frequency.set_synchronized_value(session.transmit_frequency_hz)
        self.radio_frequency.setValue(session.receive_frequency_hz)
        self._operator_tune_pending = True
        self._request_radio_frequency(session.receive_frequency_hz, "Reply Channel RX")
        self.return_normal_button.setEnabled(True)
        self.contact_status.setText(
            f"SPLIT RX {session.receive_frequency_hz} / TX {session.transmit_frequency_hz}"
        )
        self._refresh_radio_route_badge()
        self._append(
            f"[REPLY CHANNEL] {session.peer_callsign}: RX {session.receive_frequency_hz} Hz, "
            f"TX {session.transmit_frequency_hz} Hz."
        )

    def _tune_to_other_signal(self, row: int, *, prepare_contact: bool) -> None:
        """Retune the radio to center a decoded station and prepare a reply."""
        frequency_item = self.other_signals.item(row, 0)
        callsign_item = self.other_signals.item(row, 1)
        if frequency_item is None or callsign_item is None:
            return
        frequency = int(frequency_item.data(Qt.UserRole))
        callsign = callsign_item.text().strip().upper()
        self._target_callsign = callsign
        self._target_name = str(frequency_item.data(Qt.UserRole + 5) or "")
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
        gain = self.rx_audio_level.value() / 100.0
        adjusted = AudioBuffer(audio.samples * gain, audio.sample_rate)
        self._audio_blocks.put(adjusted)
        try:
            self._display_blocks.put_nowait(adjusted)
        except queue.Full:
            try:
                self._display_blocks.get_nowait()
            except queue.Empty:
                pass
            self._display_blocks.put_nowait(adjusted)

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
        self.waterfall.add_frame(frame)

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
            self._receiver = AdaptiveBandwidthAudioReceiver(
                tuple(range(100, 3_001, 100))
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
            self._append(f"[AUDIO RX ERROR] {error}")
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
        self.rx_button.setText("STOP AUDIO RX")
        self._append(
            f"[RX] Live radio audio: {device.name}; scanning 100–3000 Hz "
            "for all Aurora bandwidths."
        )

    def _restore_audio_automatically(self) -> None:
        """Start receive monitoring from the saved radio input at launch."""
        if self._stream is not None:
            return
        selected = self.input_device.currentText()
        if self.preferences.contains("audio/input"):
            selected = str(self.preferences.value("audio/input", "")).strip()
        if selected not in self._input_devices:
            self._append(
                "[AUDIO RX] Saved radio input is unavailable; select an input in Setup."
            )
            return
        self.input_device.setCurrentText(selected)
        self._append("[AUDIO RX] Starting the saved radio input automatically.")
        self._toggle_receiver()

    def _stop_receiver(self) -> None:
        self._receiver_stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        self._stream = None
        self._receiver = None
        stop_playback()
        self.rx_button.setText("START AUDIO RX")

    def _poll_decode_events(self) -> None:
        while True:
            try:
                event = self._decode_events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, Exception):
                self._append(f"[AUDIO RX ERROR] {event}")
                self._stop_receiver()
                return
            if event.message is not None:
                self._handle_contact_control(event.message)
            if event.message is not None and event.frequency_hz == MODEM_AUDIO_CENTER_HZ:
                self._append(
                    f"[RX {event.frequency_hz} Hz/{event.message.callsign}] "
                    f"{event.message.text}",
                    chat=True,
                )
                if event.message.reply_frequency_hz is not None:
                    self.add_other_signal(
                        event.frequency_hz,
                        event.message.callsign,
                        event.message.text,
                        sender_name=event.message.sender_name,
                        contact_id=event.message.contact_id,
                        reply_frequency_hz=event.message.reply_frequency_hz,
                        reply_window_seconds=event.message.reply_window_seconds,
                    )
            elif event.message is not None:
                self.add_other_signal(
                    event.frequency_hz,
                    event.message.callsign,
                    event.message.text,
                    sender_name=event.message.sender_name,
                    contact_id=event.message.contact_id,
                    reply_frequency_hz=event.message.reply_frequency_hz,
                    reply_window_seconds=event.message.reply_window_seconds,
                )
            elif event.station is not None:
                station = event.station.data
                location = station.grid or "station update"
                if station.latitude is not None:
                    location = f"GPS {station.latitude:+.5f}, {station.longitude:+.5f}"
                self.add_other_signal(
                    event.frequency_hz,
                    station.callsign,
                    location,
                    sender_name=station.operator_name or "",
                )
            elif event.report is not None:
                report = event.report
                self.add_other_signal(
                    event.frequency_hz,
                    report.reporter,
                    f"Report #{report.referenced_frame_id}: {report.snr_db:+.1f} dB SNR",
                )
            self._set_diagnostic("Sync", "LOCKED")
            self._set_diagnostic("SNR", f"{event.snr_db:+.1f} dB")
            self._set_diagnostic(
                "Frequency offset", f"{event.frequency_offset_hz:+.2f} Hz"
            )
            self._set_diagnostic(
                "Timing offset", f"{event.timing_offset_samples:.2f} samples"
            )
            self._set_diagnostic("CRC", "PASS")
            self._set_diagnostic("FEC corrections", "decoded; count unavailable")
            self.constellation.set_symbols(event.equalized_symbols)
            self.subcarrier_quality.set_quality(event.subcarrier_quality)
        self._poll_cat_events()

    def _handle_contact_control(self, message) -> None:
        """Apply only controls that match the active peer and contact ID."""
        active = self._contacts.active
        if active is None:
            return
        if message.destination not in {
            "AURORA",
            self.callsign.text().strip().upper(),
        }:
            return
        if message.contact_id != active.contact_id:
            return
        if active.peer_callsign == "AURORA":
            active = self._contacts.bind_peer(message.callsign, message.sender_name)
            self._target_callsign = message.callsign
            self._target_name = message.sender_name
        if active is None or message.callsign != active.peer_callsign:
            return
        self._contacts.refresh(message.reply_window_seconds or self.reply_window.value())
        if message.end_of_call:
            self._append(f"[EOC] {message.callsign} ended the contact.")
            self._return_to_normal_operation()
        elif message.back_to_you:
            self._contacts.update_turn(TurnState.PEER_PASSED_TURN)
            self.contact_status.setText(f"YOUR TURN • {message.callsign}")
            self._append(f"[BTY] {message.callsign} passed the turn to you.")

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
                status = self._initialize_radio_status(controller)
                self._cat_events.put(("connected", controller, service, status))
            except Exception as error:
                if service is not None:
                    service.stop()
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraHamlibConnect", daemon=True).start()

    @staticmethod
    def _initialize_radio_status(
        controller: HamlibController,
    ) -> tuple[int, str, int, bool]:
        """Set the one-time 3 kHz startup filter and return CAT readback."""
        frequency = controller.get_frequency()
        mode, _ = controller.get_mode()
        controller.set_mode(mode, DEFAULT_RADIO_PASSBAND_HZ)
        mode, passband = controller.get_mode()
        return frequency, mode, passband, controller.get_ptt()

    def _restore_cat_automatically(self) -> None:
        """Reconnect a previously successful CAT setup without opening Setup."""
        if self._hamlib is not None:
            return
        self._auto_cat_connect_pending = True
        self._append("[CAT] Restoring the last successful CAT configuration.")
        self._toggle_cat()

    def _disconnect_cat(self) -> None:
        controller = self._hamlib
        service = self._hamlib_service
        active = self._contacts.return_to_normal()
        self._hamlib = None
        self._hamlib_service = None
        if controller is not None:
            try:
                controller.set_ptt(False)
                if active is not None:
                    FakeSplitController(controller).restore(active.normal_frequency_hz)
            except Exception:
                pass
            controller.close()
        if service is not None:
            service.stop()
        self.cat_button.setText("CONNECT HAMLIB")
        self.cat_button.setEnabled(True)
        self.apply_radio_button.setEnabled(False)
        self.station_data_button.setEnabled(False)
        self.tx_test_button.setEnabled(False)
        self.radio_badge.setText("RADIO DISCONNECTED")
        self._last_cat_status = None
        self.return_normal_button.setEnabled(False)
        self.contact_status.setText("SIMPLEX")

    def _request_cat_status(self) -> None:
        active = self._contacts.active
        if active is not None and active.expired():
            self._append("[REPLY CHANNEL] Offer expired; returning to normal operation.")
            self._return_to_normal_operation()
            return
        if active is not None:
            self._update_contact_countdown()
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

    def _update_contact_countdown(self) -> None:
        """Show the remaining Reply Channel time without changing its routing."""
        active = self._contacts.active
        if active is None:
            return
        remaining = active.remaining_seconds()
        countdown = f"{remaining // 60:02d}:{remaining % 60:02d}"
        if active.turn_state == TurnState.WAITING_FOR_REPLY:
            status = "WAITING FOR REPLY"
        elif active.turn_state == TurnState.PEER_PASSED_TURN:
            status = f"YOUR TURN • {active.peer_callsign}"
        else:
            status = (
                f"SPLIT RX {active.receive_frequency_hz} / "
                f"TX {active.transmit_frequency_hz}"
            )
        self.contact_status.setText(f"{status} • {countdown}")

    def _apply_radio_settings(self) -> None:
        if self._hamlib is None:
            return
        controller = self._hamlib
        frequency = self.radio_frequency.value()
        mode = self.radio_mode.currentText()
        passband = DEFAULT_RADIO_PASSBAND_HZ
        if self._last_cat_status is not None and self._last_cat_status[2] > 0:
            passband = self._last_cat_status[2]

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
        self._operator_tune_pending = True
        self._radio_tune_timer.start()

    def _operator_radio_frequency_changed(self, frequency_hz: int) -> None:
        """Tune the radio and initialize Reply Channel from the operator entry."""
        self.reply_frequency.set_synchronized_value(frequency_hz)
        self._schedule_radio_frequency(frequency_hz)

    def _preview_reply_frequency(self, text: str) -> None:
        """Mirror a valid typed frequency before Enter commands the radio."""
        frequency_hz = self.radio_frequency.valueFromText(text)
        if self.radio_frequency.minimum() <= frequency_hz <= self.radio_frequency.maximum():
            self.reply_frequency.set_synchronized_value(frequency_hz)

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

    def _return_to_normal_operation(self) -> None:
        """End local split state immediately without requiring an RF EOC."""
        session = self._contacts.return_to_normal()
        self._target_callsign = ""
        self._target_name = ""
        self.reply_channel_enabled.setChecked(False)
        self.after_send.setCurrentText("Continue")
        self.return_normal_button.setEnabled(False)
        self.contact_status.setText("RETURNING" if session is not None else "SIMPLEX")
        if session is None:
            self._append("[CONTACT] Already in normal operation.")
            return
        controller = self._hamlib
        if controller is None:
            self.contact_status.setText("SIMPLEX")
            self._append("[CONTACT] Split state cleared locally; Hamlib is disconnected.")
            return
        def worker() -> None:
            try:
                FakeSplitController(controller).restore(session.normal_frequency_hz)
                self._cat_events.put(("normal_restored", session.normal_frequency_hz))
            except Exception as error:
                self._cat_events.put(("cat_error", error))

        threading.Thread(target=worker, name="AuroraReturnNormal", daemon=True).start()

    def _ptt_arm_changed(self, armed: bool) -> None:
        self.transmit_button.setEnabled(armed and self._hamlib is not None)
        self.station_data_button.setEnabled(armed and self._hamlib is not None)
        self.tx_test_button.setEnabled(armed and self._hamlib is not None)

    def _show_cat_status(self, status: tuple[int, str, int, bool]) -> None:
        frequency, mode, passband, ptt = status
        active = self._contacts.active
        if (
            active is not None
            and not ptt
            and not self._operator_tune_pending
            and frequency != active.receive_frequency_hz
        ):
            self._clear_split_after_manual_radio_tune(frequency)
        self._last_cat_status = status
        if not (
            self.radio_frequency.operator_text_editing()
            or self._operator_tune_pending
        ):
            self.radio_frequency.setValue(frequency)
        if self.radio_mode.findText(mode) < 0:
            self.radio_mode.addItem(mode)
        self.radio_mode.setCurrentText(mode)
        state = "TX" if ptt else "RX"
        self._refresh_radio_route_badge()
        self._set_diagnostic("Sync", f"CAT {state}")
        self.session_log.record(
            "HAMLIB_STATUS",
            frequency_hz=frequency,
            mode=mode,
            passband_hz=passband,
            ptt=ptt,
        )

    def _clear_split_after_manual_radio_tune(self, frequency_hz: int) -> None:
        """Adopt an external dial change as simplex instead of hiding stale split."""
        previous = self._contacts.return_to_normal()
        if previous is None:
            return
        self._target_callsign = ""
        self._target_name = ""
        self.reply_channel_enabled.setChecked(False)
        self.return_normal_button.setEnabled(False)
        self.radio_frequency.set_synchronized_value(frequency_hz)
        self.reply_frequency.set_synchronized_value(frequency_hz)
        self.contact_status.setText("SIMPLEX • MANUAL RADIO TUNE")
        self._append(
            "[REPLY CHANNEL CANCELLED] The radio was tuned manually during split. "
            f"Aurora adopted {frequency_hz} Hz as the new simplex frequency."
        )

    def _refresh_radio_route_badge(self) -> None:
        """Show explicit RX/TX dial routing for simplex or Reply Channel."""
        if self._hamlib is None:
            self.radio_badge.setText("RADIO DISCONNECTED")
            return
        status = self._last_cat_status
        actual_hz = status[0] if status is not None else self.radio_frequency.value()
        ptt = status[3] if status is not None else False
        session = self._contacts.active
        if session is None:
            receive_hz = transmit_hz = actual_hz
            route = "SIMPLEX"
        else:
            receive_hz = session.receive_frequency_hz
            transmit_hz = session.transmit_frequency_hz
            route = "SPLIT" if session.split else "SIMPLEX"
        state = "TX" if ptt else "RX"
        self.radio_badge.setText(
            f"HAMLIB {state} • {route}\n"
            f"RX: {receive_hz / 1_000_000:.6f}  TX: {transmit_hz / 1_000_000:.6f} MHz"
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
                self.preferences.setValue("cat/last_success", True)
                self._save_preferences()
                self.cat_button.setText("DISCONNECT HAMLIB")
                self.cat_button.setEnabled(True)
                self.apply_radio_button.setEnabled(True)
                self._ptt_arm_changed(self.ptt_arm.isChecked())
                self._show_cat_status(values[2])
                source = "external" if self._hamlib_service is None else "bundled"
                self._append(
                    f"[CAT] {source.title()} Hamlib connected; PTT control "
                    f"{'enabled' if self.ptt_arm.isChecked() else 'disabled'}."
                )
                if (
                    self._auto_cat_connect_pending
                    and self._startup_radio_settings is not None
                ):
                    frequency, mode = self._startup_radio_settings
                    self.radio_frequency.set_synchronized_value(frequency)
                    self.reply_frequency.set_synchronized_value(frequency)
                    self.radio_mode.setCurrentText(mode)
                    self._append(
                        f"[CAT] Applying saved frequency {frequency} Hz and mode {mode}."
                    )
                    self._apply_radio_settings()
                self._auto_cat_connect_pending = False
                self._startup_radio_settings = None
            elif kind == "status":
                self._show_cat_status(values[0])
            elif kind == "settings_applied":
                self._append("[CAT] Radio frequency and mode applied.")
            elif kind == "frequency_applied":
                self._operator_tune_pending = False
                self.radio_frequency.setValue(values[0])
                if self._last_cat_status is not None:
                    _, mode, passband, ptt = self._last_cat_status
                    self._last_cat_status = (values[0], mode, passband, ptt)
                self._refresh_radio_route_badge()
                self._append(f"[CAT] Tuned to {values[0]} Hz ({values[1]}).")
            elif kind == "normal_restored":
                self.radio_frequency.setValue(values[0])
                self.contact_status.setText("SIMPLEX")
                if self._last_cat_status is not None:
                    _, mode, passband, ptt = self._last_cat_status
                    self._last_cat_status = (values[0], mode, passband, ptt)
                self._refresh_radio_route_badge()
                self._append(f"[CONTACT] Returned to normal operation on {values[0]} Hz.")
            elif kind == "tx_complete":
                self._operator_tune_pending = False
                self.transmit_button.setEnabled(self.ptt_arm.isChecked())
                self.station_data_button.setEnabled(self.ptt_arm.isChecked())
                self.tx_test_button.setEnabled(self.ptt_arm.isChecked())
                error, back_to_you, end_of_call, return_frequency = values
                self.tx_diagnostics["State"].setText(
                    "ERROR" if error is not None else "IDLE"
                )
                if return_frequency is not None:
                    self.radio_frequency.setValue(return_frequency)
                if back_to_you and error is None:
                    self._contacts.update_turn(TurnState.WAITING_FOR_REPLY)
                    self.contact_status.setText("WAITING FOR REPLY")
                if end_of_call:
                    ended = self._contacts.return_to_normal()
                    self._target_callsign = ""
                    self._target_name = ""
                    self.reply_channel_enabled.setChecked(False)
                    self.return_normal_button.setEnabled(False)
                    self.contact_status.setText("SIMPLEX")
                    if ended is not None:
                        self._append("[EOC] Contact ended; returned to normal operation.")
                self._refresh_radio_route_badge()
                if error is not None:
                    self._append(f"[TX ERROR] {error}")
            elif kind == "cat_error":
                self._operator_tune_pending = False
                self._auto_cat_connect_pending = False
                self._startup_radio_settings = None
                self.cat_button.setEnabled(True)
                self._append(f"[CAT ERROR] {values[0]}")

    def _build_transmit_audio(
        self,
        message_text: str,
        *,
        back_to_you: bool = False,
        end_of_call: bool = False,
    ) -> AudioBuffer:
        """Build conditioned radio audio for the current operator message."""
        mode = mode_at_frequency(self._selected_mode(), MODEM_AUDIO_CENTER_HZ)
        session = self._contacts.active
        transmission = encode_chat_air_transmission(
            self.callsign.text(),
            message_text,
            destination=self._target_callsign or "AURORA",
            mode=mode,
            sender_name=self.operator_name.text(),
            contact_id=session.contact_id if session is not None else 0,
            reply_frequency_hz=(
                session.receive_frequency_hz if session is not None else None
            ),
            reply_window_seconds=(
                self.reply_window.value() if session is not None else 0
            ),
            back_to_you=back_to_you,
            end_of_call=end_of_call,
        )
        waveform = modulate_audio(
            transmission.symbols,
            mode,
            leading_silence_samples=self.settings.audio_sample_rate // 5,
        )
        conditioned = condition_playback(
            waveform,
            gain=self._tx_audio_gain(),
            fade_seconds=0.02,
            trailing_silence_seconds=0.10,
        )
        report = validate_transmit_audio(conditioned)
        self._update_generated_tx_diagnostics(mode, report)
        return conditioned

    def _update_generated_tx_diagnostics(
        self, mode, report: TransmitQualityReport
    ) -> None:
        """Publish local waveform measurements without implying an RF ALC reading."""
        carrier_count = len(config_for_mode(mode).data_subcarriers)
        values = {
            "Audio drive": f"{self.tx_audio_level.value()}%",
            "Peak": f"{report.peak:.3f}",
            "RMS": f"{report.active_rms:.3f}",
            "Crest factor": f"{report.crest_factor:.2f}:1",
            "Clipping": str(report.clipped_samples),
            "Linearity": "PASS" if report.compliant else "BLOCKED",
            "Profile": f"{mode.occupied_bandwidth_hz} Hz • {carrier_count} carriers",
        }
        for name, value in values.items():
            self.tx_diagnostics[name].setText(value)

    def _tx_audio_gain(self) -> float:
        """Map the operator's 100% display to Aurora's validated gain ceiling."""
        return MAX_TX_AUDIO_GAIN * self.tx_audio_level.value() / 100.0

    def _test_tx_audio(self) -> None:
        """Transmit a representative identified OFDM frame for radio ALC setup."""
        if self._hamlib is None or not self.ptt_arm.isChecked():
            self._append("[TX TEST BLOCKED] Connect Hamlib and enable PTT Control.")
            return
        if self._contacts.active is not None:
            self._append("[TX TEST BLOCKED] Return to normal operation before testing.")
            return
        try:
            output = self._output_devices[self.output_device.currentText()]
            callsign = self.callsign.text().strip().upper() or "AURORA"
            audio = self._build_transmit_audio(f"TX LEVEL TEST DE {callsign}")
        except Exception as error:
            self._append(f"[TX TEST ERROR] {error}")
            return
        self._start_radio_playback(audio, output.index)
        self._append(
            f"[TX TEST] Aurora OFDM level test at {self.tx_audio_level.value()}%; "
            "observe the radio ALC meter."
        )

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
                operator_name=self.operator_name.text().strip() or None,
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
                gain=self._tx_audio_gain(),
                fade_seconds=0.02,
                trailing_silence_seconds=0.10,
            )
            report = validate_transmit_audio(audio)
            self._update_generated_tx_diagnostics(mode, report)
            output = self._output_devices[self.output_device.currentText()]
        except Exception as error:
            self._append(f"[STATION DATA ERROR] {error}")
            return
        self._start_radio_playback(audio, output.index)
        location = station.grid or "location omitted"
        if station.latitude is not None:
            location = "GPS included"
        self._append(f"[TX AX.25/{station.callsign}] {location}")

    def _start_radio_playback(
        self,
        audio: AudioBuffer,
        output_index: int,
        *,
        back_to_you: bool = False,
        end_of_call: bool = False,
    ) -> None:
        """Key PTT and play one already-conditioned Aurora transmission."""
        self.transmit_button.setEnabled(False)
        self.station_data_button.setEnabled(False)
        self.tx_test_button.setEnabled(False)
        self.tx_diagnostics["State"].setText("TX ACTIVE")
        session = self._contacts.active
        if session is not None and session.split:
            self._operator_tune_pending = True

        def worker() -> None:
            error = None
            return_frequency = None
            try:
                if session is not None and session.split:
                    FakeSplitController(self._hamlib).prepare_transmit(
                        session.transmit_frequency_hz
                    )
                self._hamlib.set_ptt(True)
                play_audio(audio, blocking=True, device=output_index)
            except Exception as caught:
                error = caught
            finally:
                try:
                    self._hamlib.set_ptt(False)
                    if session is not None and session.split:
                        return_frequency = (
                            session.normal_frequency_hz
                            if end_of_call
                            else session.receive_frequency_hz
                        )
                        FakeSplitController(self._hamlib).finish_transmit(return_frequency)
                except Exception as restore_error:
                    error = error or restore_error
                self._cat_events.put(
                    ("tx_complete", error, back_to_you, end_of_call, return_frequency)
                )

        threading.Thread(target=worker, name="AuroraRadioTransmit", daemon=True).start()

    def _transmit(self) -> None:
        if self._hamlib is None or not self.ptt_arm.isChecked():
            self._append("[TX BLOCKED] Connect Hamlib and explicitly arm PTT.")
            return
        try:
            output = self._output_devices[self.output_device.currentText()]
            prepared = self._prepared_message()
            selection = self.after_send.currentText()
            back_to_you = prepared.back_to_you or selection == "Back to You"
            end_of_call = prepared.end_of_call or selection == "End Contact"
            if back_to_you and end_of_call:
                raise ValueError("BTY and EOC cannot be sent together")
            if self.reply_channel_enabled.isChecked() and self._contacts.active is None:
                session = self._contacts.offer(
                    local_callsign=self.callsign.text(),
                    normal_frequency_hz=self.radio_frequency.value(),
                    reply_frequency_hz=self.reply_frequency.value(),
                    mode=self.radio_mode.currentText(),
                    window_seconds=self.reply_window.value(),
                )
                self.return_normal_button.setEnabled(True)
                self.contact_status.setText(
                    f"SPLIT RX {session.receive_frequency_hz} / TX {session.transmit_frequency_hz}"
                )
                self._refresh_radio_route_badge()
            if (back_to_you or end_of_call) and self._contacts.active is None:
                raise ValueError("BTY and EOC require an active Reply Channel contact")
            if self._contacts.active is not None:
                self._contacts.refresh(self.reply_window.value())
            audio = self._build_transmit_audio(
                prepared.text,
                back_to_you=back_to_you,
                end_of_call=end_of_call,
            )
        except Exception as error:
            self._append(f"[AUDIO TX ERROR] {error}")
            return
        self.after_send.setCurrentText("Continue")
        self._start_radio_playback(
            audio,
            output.index,
            back_to_you=back_to_you,
            end_of_call=end_of_call,
        )
        self.message.clear()
        self._append(
            f"[TX {MODEM_AUDIO_CENTER_HZ} Hz/{self.callsign.text()}] "
            f"{prepared.text}",
            chat=True,
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
        QPushButton:checked {{ background: {accent}; color: {background}; border-color: {accent}; font-weight: 700; }}
        QPushButton#primary {{ background: {border}; border-color: {accent}; font-weight: 700; }}
        QTabBar::tab {{ background: {field}; padding: 7px 12px; }}
        QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
    """


def run(settings: AppSettings = SETTINGS) -> None:
    """Start the responsive Qt Aurora interface."""
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Aurora")
    application.setOrganizationName("N4EAC")
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    icon_path = resource_root / "assets" / "aurora-icon.png"
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    application.setStyle("Fusion")
    application.setStyleSheet(_stylesheet())
    window = AuroraQtWindow(settings)
    window.show()
    application.exec()
