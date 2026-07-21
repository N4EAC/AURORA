"""Tests for Aurora real-time audio stream wrappers."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from audio.buffer import AudioBuffer
from audio.streaming import AudioDuplexStream, AudioInputStream, AudioOutputStream


class AudioStreamingTests(unittest.TestCase):
    @patch("audio.streaming.sd.InputStream")
    def test_input_stream_delivers_copied_audio(self, stream_type) -> None:
        backend = MagicMock(active=False)
        stream_type.return_value = backend
        received: list[AudioBuffer] = []
        stream = AudioInputStream(received.append)

        callback = stream_type.call_args.kwargs["callback"]
        source = np.full((4, 1), 0.25, dtype=np.float32)
        callback(source, 4, None, None)
        source.fill(0.0)

        self.assertEqual(received[0].sample_rate, 12_000)
        self.assertAlmostEqual(float(received[0].samples[0, 0]), 0.25)
        stream.start()
        stream.stop()
        stream.close()
        backend.start.assert_called_once_with()
        backend.stop.assert_called_once_with()
        backend.close.assert_called_once_with()

    @patch("audio.streaming.sd.OutputStream")
    def test_output_stream_zero_pads_short_blocks(self, stream_type) -> None:
        stream_type.return_value = MagicMock(active=False)
        AudioOutputStream(lambda frames: np.array([0.5, -0.5], dtype=np.float32))
        callback = stream_type.call_args.kwargs["callback"]
        output = np.empty((4, 1), dtype=np.float32)
        callback(output, 4, None, None)
        np.testing.assert_array_equal(output[:, 0], [0.5, -0.5, 0.0, 0.0])

    @patch("audio.streaming.sd.Stream")
    def test_duplex_stream_processes_input(self, stream_type) -> None:
        stream_type.return_value = MagicMock(active=False)
        AudioDuplexStream(lambda audio: -audio.samples)
        callback = stream_type.call_args.kwargs["callback"]
        input_data = np.array([[0.25], [-0.5]], dtype=np.float32)
        output = np.empty_like(input_data)
        callback(input_data, output, 2, None, None)
        np.testing.assert_array_equal(output, -input_data)


if __name__ == "__main__":
    unittest.main()
