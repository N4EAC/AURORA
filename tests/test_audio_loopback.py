"""Tests for the audio-only Aurora loopback transaction."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from audio.loopback import (
    _playrec_with_timeout,
    run_audio_loopback,
    run_deep_audio_loopback,
)


class AudioLoopbackTests(unittest.TestCase):
    def test_stalled_audio_backend_is_stopped_at_timeout(self) -> None:
        samples = np.zeros(12, dtype=np.float32)
        stream = Mock(active=True)
        with (
            patch("audio.loopback.sd.playrec", return_value=samples),
            patch("audio.loopback.sd.get_stream", return_value=stream),
            patch("audio.loopback.sd.stop") as stop,
            patch("audio.loopback.time.monotonic", side_effect=(0.0, 1.0)),
        ):
            with self.assertRaisesRegex(TimeoutError, "timeout"):
                _playrec_with_timeout(
                    samples,
                    sample_rate=12_000,
                    input_device=1,
                    output_device=2,
                    timeout_margin_seconds=0.1,
                )
        stop.assert_called_once_with()

    def test_deep_payload_length_is_validated_before_audio_access(self) -> None:
        with patch("audio.loopback.sd.playrec") as playrec:
            with self.assertRaisesRegex(ValueError, "exactly 20"):
                run_deep_audio_loopback(
                    b"short",
                    input_device=1,
                    output_device=2,
                    capture_path="unused.wav",
                )
        playrec.assert_not_called()

    def test_empty_message_is_rejected_before_audio_access(self) -> None:
        with patch("audio.loopback.sd.playrec") as playrec:
            with self.assertRaisesRegex(ValueError, "message"):
                run_audio_loopback(
                    " ",
                    input_device=1,
                    output_device=2,
                    capture_path="unused.wav",
                )
        playrec.assert_not_called()

    def test_output_gain_is_validated_before_audio_access(self) -> None:
        with patch("audio.loopback.sd.playrec") as playrec:
            with self.assertRaisesRegex(ValueError, "output gain"):
                run_audio_loopback(
                    "Aurora",
                    input_device=1,
                    output_device=2,
                    capture_path="unused.wav",
                    output_gain=1.1,
                )
        playrec.assert_not_called()

    def test_full_duplex_capture_decodes_and_writes_wav(self) -> None:
        def loopback(samples, **options):
            self.assertEqual(options["input_device"], 1)
            self.assertEqual(options["output_device"], 2)
            return samples.copy()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.wav"
            with patch("audio.loopback._playrec_with_timeout", side_effect=loopback):
                result = run_audio_loopback(
                    "Aurora audio",
                    input_device=1,
                    output_device=2,
                    capture_path=path,
                )
            self.assertEqual(result.received_text, "Aurora audio")
            self.assertTrue(path.exists())
            self.assertTrue(result.diagnostics.synchronized)
            self.assertFalse(result.clipped)

    def test_output_gain_scales_played_samples(self) -> None:
        observed_peak = 0.0

        def loopback(samples, **options):
            nonlocal observed_peak
            observed_peak = float(np.max(np.abs(samples)))
            return samples.copy()

        with tempfile.TemporaryDirectory() as directory:
            with patch("audio.loopback._playrec_with_timeout", side_effect=loopback):
                run_audio_loopback(
                    "gain",
                    input_device=1,
                    output_device=2,
                    capture_path=Path(directory) / "capture.wav",
                    output_gain=0.5,
                )
        self.assertLess(observed_peak, 0.5)

    def test_deep_full_duplex_capture_decodes_and_writes_wav(self) -> None:
        def loopback(samples, **options):
            self.assertEqual(options["input_device"], 1)
            self.assertEqual(options["output_device"], 2)
            return samples.copy()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep_capture.wav"
            with patch("audio.loopback._playrec_with_timeout", side_effect=loopback):
                result = run_deep_audio_loopback(
                    b"Aurora Deep message!",
                    input_device=1,
                    output_device=2,
                    capture_path=path,
                )
            self.assertEqual(result.received_payload, b"Aurora Deep message!")
            self.assertTrue(path.exists())
            self.assertFalse(result.clipped)


if __name__ == "__main__":
    unittest.main()
