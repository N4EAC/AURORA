"""Tests for Aurora PCM WAV handling."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from audio.buffer import AudioBuffer
from audio.wav import read_wav, write_wav


class AudioWavTests(unittest.TestCase):
    def test_mono_wav_round_trip(self) -> None:
        samples = np.array([-1.0, -0.5, 0.0, 0.5, 1.0], dtype=np.float32)
        source = AudioBuffer(samples, 12_000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio.wav"
            write_wav(path, source)
            decoded = read_wav(path)

        self.assertEqual(decoded.sample_rate, 12_000)
        self.assertEqual(decoded.channel_count, 1)
        np.testing.assert_allclose(decoded.samples, samples, atol=1.0 / 32_767.0)

    def test_stereo_wav_round_trip(self) -> None:
        samples = np.array([[0.25, -0.25], [0.5, -0.5]], dtype=np.float32)
        source = AudioBuffer(samples, 48_000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stereo.wav"
            write_wav(path, source)
            decoded = read_wav(path)

        self.assertEqual(decoded.channel_count, 2)
        np.testing.assert_allclose(decoded.samples, samples, atol=1.0 / 32_767.0)


if __name__ == "__main__":
    unittest.main()
