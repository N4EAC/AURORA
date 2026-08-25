"""Headless tests for Aurora's live Qt radio-audio display path."""

import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDockWidget

from audio.buffer import AudioBuffer
from gui.qt_application import AuroraQtWindow


class QtLiveDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.preferences = QSettings(
            str(Path(self.directory.name) / "aurora.ini"), QSettings.IniFormat
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_portaudio_shaped_mono_block_updates_spectrum(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        samples = np.sin(np.arange(1_024, dtype=np.float32) * 0.2)[:, np.newaxis]
        window._receive_audio(AudioBuffer(samples, 12_000))
        window._update_live_display()
        self.assertIsNotNone(window.spectrum._frame)
        window.close()

    def test_operator_layout_and_defaults(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(window.transmit_button.text(), "SEND")
        self.assertEqual(window.ptt_arm.text(), "PTT Control")
        self.assertTrue(window.ptt_arm.isChecked())
        self.assertNotIn("#", window.hamlib_model.currentText())
        self.assertIsInstance(window.messages_dock, QDockWidget)
        self.assertIsInstance(window.other_signals_dock, QDockWidget)
        self.assertLessEqual(window.waterfall.maximumHeight(), 72)
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["File", "Setup", "Theme", "About"],
        )
        window.close()

    def test_operator_preferences_round_trip(self) -> None:
        first = AuroraQtWindow(preferences=self.preferences)
        first.operator_name.setText("Eduardo")
        first.callsign.setText("K1ABC")
        first.grid.setText("FN31")
        first.latitude.setText("41.1")
        first.longitude.setText("-72.2")
        first.bandwidth.setCurrentText("2.3 kHz")
        first.frequency.setValue(1_700)
        first._apply_theme("Amber")
        first.close()

        second = AuroraQtWindow(preferences=self.preferences)
        self.assertEqual(second.operator_name.text(), "Eduardo")
        self.assertEqual(second.callsign.text(), "K1ABC")
        self.assertEqual(second.grid.text(), "FN31")
        self.assertEqual(second.latitude.text(), "41.1")
        self.assertEqual(second.longitude.text(), "-72.2")
        self.assertEqual(second.bandwidth.currentText(), "2.3 kHz")
        self.assertEqual(second.frequency.value(), 1_700)
        self.assertEqual(second.preferences.value("appearance/theme"), "Amber")
        second.close()

    def test_other_signal_can_tune_and_prepare_contact(self) -> None:
        window = AuroraQtWindow(preferences=self.preferences)
        window.add_other_signal(1_700, "W1AW", "CQ")
        window._tune_to_other_signal(0, prepare_contact=True)
        self.assertEqual(window.frequency.value(), 1_700)
        self.assertEqual(window.message.text(), "W1AW de <CALL>")
        self.assertIn("reply prepared for W1AW", window.history.toPlainText())
        window.close()


if __name__ == "__main__":
    unittest.main()
