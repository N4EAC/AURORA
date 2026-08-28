"""Tests for simultaneous Aurora occupied-bandwidth reception."""

import unittest
from unittest.mock import MagicMock

import numpy as np

from audio.adaptive_receiver import AdaptiveBandwidthAudioReceiver
from audio.buffer import AudioBuffer


class AdaptiveBandwidthAudioReceiverTests(unittest.TestCase):
    def test_every_bandwidth_receiver_receives_the_same_audio(self) -> None:
        receivers = []

        def factory(frequencies, mode):
            receiver = MagicMock()
            receiver.feed.return_value = ()
            receiver.mode = mode
            receiver.frequencies = frequencies
            receivers.append(receiver)
            return receiver

        adaptive = AdaptiveBandwidthAudioReceiver((500, 1_500, 2_500), receiver_factory=factory)
        audio = AudioBuffer(np.zeros(128, dtype=np.float32), 12_000)
        self.assertEqual(len(receivers), 3)
        adaptive.feed(audio, discontinuity=True)
        self.assertEqual(
            {receiver.mode.occupied_bandwidth_hz for receiver in receivers},
            {500, 2_300, 2_800},
        )
        for receiver in receivers:
            receiver.feed.assert_called_once_with(audio, discontinuity=True)


if __name__ == "__main__":
    unittest.main()
