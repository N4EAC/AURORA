"""Tests for deterministic offline real-audio channel impairments."""

import unittest

import numpy as np

from audio.buffer import AudioBuffer
from dsp.audio_channel import (
    AudioChannelConfig,
    apply_audio_channel,
    reference_noise_variance,
)


class AudioChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        time = np.arange(12_000, dtype=np.float64) / 12_000.0
        self.audio = AudioBuffer(
            (0.25 * np.sin(2.0 * np.pi * 1_500.0 * time)).astype(np.float32),
            12_000,
        )

    def test_seeded_channel_is_reproducible(self) -> None:
        config = AudioChannelConfig(snr_db=5.0, impulse_probability=0.001, impulse_scale=2.0)
        first = apply_audio_channel(self.audio, config, np.random.default_rng(42))
        second = apply_audio_channel(self.audio, config, np.random.default_rng(42))
        self.assertTrue(np.array_equal(first.samples, second.samples))

    def test_reference_bandwidth_noise_calibration(self) -> None:
        variance = reference_noise_variance(1.0, 0.0, 12_000, 2_500.0)
        self.assertAlmostEqual(variance, 2.4)

    def test_each_non_noise_impairment_changes_audio(self) -> None:
        cases = (
            AudioChannelConfig(amplitude_scale=0.5),
            AudioChannelConfig(timing_offset_samples=0.4),
            AudioChannelConfig(clock_error_ppm=100.0),
            AudioChannelConfig(multipath_delay_ms=1.0, multipath_gain=0.3),
            AudioChannelConfig(fading_depth=0.4, fading_cycles_per_frame=1.0),
            AudioChannelConfig(impulse_probability=0.01, impulse_scale=2.0),
        )
        for config in cases:
            with self.subTest(config=config):
                impaired = apply_audio_channel(
                    self.audio, config, np.random.default_rng(2026)
                )
                self.assertFalse(np.array_equal(impaired.samples, self.audio.samples))
                self.assertTrue(np.isfinite(impaired.samples).all())

    def test_reference_bandwidth_cannot_exceed_nyquist(self) -> None:
        with self.assertRaisesRegex(ValueError, "Nyquist"):
            apply_audio_channel(
                self.audio,
                AudioChannelConfig(reference_bandwidth_hz=7_000.0),
                np.random.default_rng(1),
            )


if __name__ == "__main__":
    unittest.main()
