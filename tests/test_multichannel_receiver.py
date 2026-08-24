"""Tests for parallel frequency-tagged Aurora chat reception."""

import unittest

import numpy as np

from audio.buffer import AudioBuffer
from audio.multichannel_receiver import MultichannelAudioReceiver, mode_at_frequency
from dsp.waveform import modulate_audio
from modem.chat_transport import encode_chat_transmission
from modem.mode_definition import AURORA_500_MODE


class MultichannelReceiverTests(unittest.TestCase):
    def test_frequency_range_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "100 and 3000"):
            mode_at_frequency(AURORA_500_MODE, 99)

    def test_two_simultaneous_frequencies_are_decoded(self) -> None:
        signals = []
        for frequency, callsign, text in (
            (900, "N4EAC", "selected"),
            (2_100, "W1AW", "other signal"),
        ):
            mode = mode_at_frequency(AURORA_500_MODE, frequency)
            transmission = encode_chat_transmission(callsign, text, mode=mode)
            signals.append(
                modulate_audio(
                    transmission.symbols,
                    mode,
                    leading_silence_samples=731,
                ).samples
            )
        length = max(len(signal) for signal in signals)
        mixed = np.zeros(length, dtype=np.float32)
        for signal in signals:
            mixed[: len(signal)] += signal * 0.45
        receiver = MultichannelAudioReceiver((900, 2_100), AURORA_500_MODE)
        events = receiver.feed(AudioBuffer(mixed, 12_000))
        self.assertEqual(
            {
                (event.frequency_hz, event.message.callsign, event.message.text)
                for event in events
            },
            {
                (900, "N4EAC", "selected"),
                (2_100, "W1AW", "other signal"),
            },
        )

    def test_noise_does_not_activate_every_channel_decoder(self) -> None:
        receiver = MultichannelAudioReceiver(
            tuple(range(100, 3_001, 100)), AURORA_500_MODE
        )
        noise = np.random.default_rng(824).normal(0.0, 0.01, 100_000)
        receiver._samples = noise.astype(np.float32)
        self.assertEqual(receiver._spectral_candidates(), ())


if __name__ == "__main__":
    unittest.main()
