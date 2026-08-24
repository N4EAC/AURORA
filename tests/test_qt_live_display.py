"""Headless tests for Aurora's live Qt radio-audio display path."""

import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from audio.buffer import AudioBuffer
from gui.qt_application import AuroraQtWindow


class QtLiveDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_portaudio_shaped_mono_block_updates_spectrum(self) -> None:
        window = AuroraQtWindow()
        samples = np.sin(np.arange(1_024, dtype=np.float32) * 0.2)[:, np.newaxis]
        window._receive_audio(AudioBuffer(samples, 12_000))
        window._update_live_display()
        self.assertIsNotNone(window.spectrum._frame)
        window.close()


if __name__ == "__main__":
    unittest.main()
