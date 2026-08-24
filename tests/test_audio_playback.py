"""Tests for Aurora buffered playback."""

import unittest
from unittest.mock import patch

import numpy as np

from audio.buffer import AudioBuffer
from audio.playback import condition_playback, play_audio, stop_playback


class AudioPlaybackTests(unittest.TestCase):
    def test_conditioning_adds_headroom_fades_and_silent_guard(self) -> None:
        audio = AudioBuffer(np.ones(1_200, dtype=np.float32), 12_000)
        conditioned = condition_playback(
            audio,
            gain=0.5,
            fade_seconds=0.01,
            trailing_silence_seconds=0.1,
        )
        self.assertEqual(conditioned.frame_count, 2_400)
        self.assertEqual(float(conditioned.samples[0]), 0.0)
        self.assertEqual(float(conditioned.samples[-1]), 0.0)
        self.assertLessEqual(float(np.max(np.abs(conditioned.samples))), 0.5)

    @patch("audio.playback.sd.play")
    def test_playback_passes_buffer_properties(self, play) -> None:
        audio = AudioBuffer(np.zeros(16, dtype=np.float32), 12_000)
        play_audio(audio, blocking=True, device=2)
        play.assert_called_once_with(
            audio.samples,
            samplerate=12_000,
            device=2,
            blocking=True,
        )

    @patch("audio.playback.sd.stop")
    def test_stop_delegates_to_backend(self, stop) -> None:
        stop_playback()
        stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
