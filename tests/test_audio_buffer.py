"""Tests for Aurora audio buffers."""

import unittest

import numpy as np

from audio.buffer import AudioBuffer


class AudioBufferTests(unittest.TestCase):
    def test_mono_properties(self) -> None:
        audio = AudioBuffer(np.zeros(6_000, dtype=np.float32), 12_000)
        self.assertEqual(audio.frame_count, 6_000)
        self.assertEqual(audio.channel_count, 1)
        self.assertEqual(audio.duration_seconds, 0.5)

    def test_source_is_copied_and_buffer_is_read_only(self) -> None:
        source = np.array([0.25, -0.25], dtype=np.float32)
        audio = AudioBuffer(source, 12_000)
        source[0] = 1.0
        self.assertAlmostEqual(float(audio.samples[0]), 0.25)
        with self.assertRaises(ValueError):
            audio.samples[0] = 0.0

    def test_non_finite_samples_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            AudioBuffer(np.array([np.nan], dtype=np.float32), 12_000)


if __name__ == "__main__":
    unittest.main()
