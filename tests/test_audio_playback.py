"""Tests for Aurora buffered playback."""

import unittest
from unittest.mock import patch

import numpy as np

from audio.buffer import AudioBuffer
from audio.playback import play_audio, stop_playback


class AudioPlaybackTests(unittest.TestCase):
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
