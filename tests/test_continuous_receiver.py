"""Tests for bounded continuous Aurora audio reception."""

import unittest
from pathlib import Path

import numpy as np

from audio.buffer import AudioBuffer
from audio.wav import read_wav
from audio.continuous_receiver import (
    ContinuousAudioReceiver,
    ContinuousReceiverConfig,
)
from dsp.core import encode_payload
from dsp.waveform import modulate_audio
from modem.mode_definition import AURORA_ROBUST_MODE


def _test_waveform(message: bytes, leading: int = 731) -> tuple[AudioBuffer, int]:
    transmission = encode_payload(
        message,
        modulation=AURORA_ROBUST_MODE.modulation,
        interleaver_columns=AURORA_ROBUST_MODE.interleaver_columns,
    )
    return (
        modulate_audio(
            transmission.symbols,
            leading_silence_samples=leading,
        ),
        len(transmission.symbols),
    )


def _disrupt_waveform(
    waveform: AudioBuffer,
    *,
    sample: int,
    sample_count: int,
    duplicate: bool,
) -> AudioBuffer:
    if duplicate:
        samples = np.concatenate(
            (
                waveform.samples[:sample],
                waveform.samples[sample - sample_count : sample],
                waveform.samples[sample:],
            )
        )
    else:
        samples = np.concatenate(
            (
                waveform.samples[:sample],
                waveform.samples[sample + sample_count :],
                np.zeros(sample_count, dtype=np.float32),
            )
        )
    return AudioBuffer(samples, waveform.sample_rate)


class ContinuousAudioReceiverTests(unittest.TestCase):
    def test_arbitrary_blocks_recover_one_crc_confirmed_frame(self) -> None:
        waveform, symbol_count = _test_waveform(b"stream")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        events = []
        for offset in range(0, waveform.frame_count, 777):
            events.extend(
                receiver.feed(
                    AudioBuffer(
                        waveform.samples[offset : offset + 777],
                        waveform.sample_rate,
                    )
                )
            )
        self.assertEqual([event.payload for event in events], [b"stream"])
        self.assertEqual(receiver.diagnostics.decoded_frames, 1)
        self.assertLess(receiver.diagnostics.buffered_samples, 777)

    def test_discontinuity_discards_partial_frame_and_recovers_next(self) -> None:
        waveform, symbol_count = _test_waveform(b"recover")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        midpoint = waveform.frame_count // 2
        self.assertEqual(
            receiver.feed(
                AudioBuffer(waveform.samples[:midpoint], waveform.sample_rate)
            ),
            (),
        )
        events = receiver.feed(waveform, discontinuity=True)
        self.assertEqual([event.payload for event in events], [b"recover"])
        self.assertEqual(receiver.diagnostics.discontinuities, 1)
        self.assertGreater(receiver.diagnostics.dropped_samples, 0)

    def test_two_frames_in_one_block_are_both_recovered(self) -> None:
        waveform, symbol_count = _test_waveform(b"double")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        combined = AudioBuffer(
            np.concatenate((waveform.samples, waveform.samples)),
            waveform.sample_rate,
        )

        events = receiver.feed(combined)

        self.assertEqual(
            [event.payload for event in events],
            [b"double", b"double"],
        )
        self.assertEqual(receiver.diagnostics.decoded_frames, 2)
        self.assertEqual(receiver.diagnostics.buffered_samples, 0)

    def test_recorded_phase_discontinuity_is_crc_repaired(self) -> None:
        _, symbol_count = _test_waveform(b"A085")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        capture = read_wav(
            Path("tests/fixtures/audio/a085_transient_failure.wav")
        )

        events = receiver.feed(capture)

        self.assertEqual([event.payload for event in events], [b"A085"])
        self.assertEqual(events[0].recovery, "phase_inversion")
        self.assertIsNotNone(events[0].repair_symbol)
        self.assertEqual(receiver.diagnostics.phase_repairs, 1)

    def test_mid_frame_sample_loss_is_crc_repaired(self) -> None:
        waveform, symbol_count = _test_waveform(b"sample loss")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        disrupted = _disrupt_waveform(
            waveform,
            sample=waveform.frame_count // 2,
            sample_count=108,
            duplicate=False,
        )

        events = receiver.feed(disrupted)

        self.assertEqual([event.payload for event in events], [b"sample loss"])
        self.assertEqual(events[0].recovery, "phase_inversion")

    def test_mid_frame_sample_duplication_is_crc_repaired(self) -> None:
        waveform, symbol_count = _test_waveform(b"sample duplicate")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        disrupted = _disrupt_waveform(
            waveform,
            sample=waveform.frame_count // 2,
            sample_count=108,
            duplicate=True,
        )

        events = receiver.feed(disrupted)

        self.assertEqual(
            [event.payload for event in events],
            [b"sample duplicate"],
        )
        self.assertEqual(events[0].recovery, "phase_inversion")

    def test_noise_buffer_remains_bounded(self) -> None:
        _, symbol_count = _test_waveform(b"bounded")
        config = ContinuousReceiverConfig(
            symbol_count,
            search_margin_seconds=0.1,
            retry_step_samples=512,
        )
        receiver = ContinuousAudioReceiver(config)
        noise = np.random.default_rng(2026).normal(
            0.0,
            0.01,
            config.maximum_buffer_samples + 2_048,
        )
        receiver.feed(AudioBuffer(noise.astype(np.float32), 12_000))
        self.assertLess(
            receiver.diagnostics.buffered_samples,
            len(noise),
        )
        self.assertGreaterEqual(receiver.diagnostics.failed_windows, 1)

    def test_corrupted_frame_is_skipped_before_valid_frame(self) -> None:
        waveform, symbol_count = _test_waveform(b"recover")
        corrupted = np.asarray(waveform.samples).copy()
        corrupted.fill(0.0)
        combined = np.concatenate(
            (
                corrupted,
                np.zeros(2_048, dtype=np.float32),
                waveform.samples,
            )
        )
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(
                symbol_count,
                search_margin_seconds=1.0,
                retry_step_samples=1_024,
            )
        )
        events = receiver.feed(AudioBuffer(combined, waveform.sample_rate))
        self.assertEqual([event.payload for event in events], [b"recover"])
        self.assertEqual(receiver.diagnostics.decoded_frames, 1)

    def test_wrong_sample_rate_is_rejected(self) -> None:
        _, symbol_count = _test_waveform(b"rate")
        receiver = ContinuousAudioReceiver(
            ContinuousReceiverConfig(symbol_count)
        )
        with self.assertRaisesRegex(ValueError, "sample rate"):
            receiver.feed(AudioBuffer(np.zeros(10, dtype=np.float32), 8_000))


if __name__ == "__main__":
    unittest.main()
