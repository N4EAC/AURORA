"""Tests for moving decoded audio signals to Aurora's fixed modem center."""

import unittest

from radio.audio_tuning import dial_frequency_for_audio_center


class AudioTuningTests(unittest.TestCase):
    def test_usb_moves_detected_signal_to_1500_hz(self) -> None:
        self.assertEqual(
            dial_frequency_for_audio_center(14_074_000, 1_900, "USB-D"),
            14_074_400,
        )
        self.assertEqual(
            dial_frequency_for_audio_center(14_074_000, 1_100, "USB"),
            14_073_600,
        )

    def test_lsb_reverses_dial_adjustment(self) -> None:
        self.assertEqual(
            dial_frequency_for_audio_center(7_074_000, 1_900, "LSB-D"),
            7_073_600,
        )

    def test_non_sideband_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "USB or LSB"):
            dial_frequency_for_audio_center(7_074_000, 1_900, "CW")


if __name__ == "__main__":
    unittest.main()
