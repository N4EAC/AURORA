"""Tests for enforceable Aurora transmitter-audio limits."""

import unittest

import numpy as np

from audio.buffer import AudioBuffer
from audio.playback import condition_playback
from dsp.transmit_quality import analyze_transmit_audio, validate_transmit_audio
from dsp.waveform import modulate_audio
from modem.chat_transport import encode_chat_air_transmission
from modem.mode_definition import AURORA_BANDWIDTH_MODES


class TransmitQualityTests(unittest.TestCase):
    def test_conditioned_ofdm_meets_linearity_limits(self) -> None:
        for bandwidth, mode in AURORA_BANDWIDTH_MODES.items():
            with self.subTest(bandwidth=bandwidth):
                transmission = encode_chat_air_transmission(
                    "N4EAC", "Aurora quality check", frame_id=5, mode=mode
                )
                audio = condition_playback(
                    modulate_audio(transmission.symbols, mode)
                )
                report = validate_transmit_audio(audio)
                self.assertTrue(report.compliant)
                self.assertLessEqual(report.peak, 0.50)
                self.assertEqual(report.clipped_samples, 0)

    def test_clipped_audio_is_rejected(self) -> None:
        samples = np.tile(np.asarray((1.0, -1.0), dtype=np.float32), 100)
        report = analyze_transmit_audio(AudioBuffer(samples, 12_000))
        self.assertFalse(report.compliant)
        with self.assertRaisesRegex(ValueError, "peak"):
            validate_transmit_audio(AudioBuffer(samples, 12_000))


if __name__ == "__main__":
    unittest.main()
