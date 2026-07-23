"""Tests for Aurora extreme research acquisition waveforms."""

import unittest

import numpy as np

from dsp.audio_channel import AudioChannelConfig, apply_audio_channel
from dsp.extreme_waveforms import (
    EXTREME_SAMPLE_RATE,
    EXTREME_SAMPLES_PER_SYMBOL,
    acquisition_baseband,
    extreme_4gfsk_preamble,
    extreme_bpsk_preamble,
    generate_acquisition_audio,
    search_acquisition,
)


class ExtremeWaveformTests(unittest.TestCase):
    def test_preambles_are_deterministic_and_have_equal_symbol_count(self) -> None:
        self.assertEqual(len(extreme_bpsk_preamble()), 127)
        self.assertEqual(len(extreme_4gfsk_preamble()), 127)
        self.assertTrue(np.all(np.isin(extreme_4gfsk_preamble(), (0, 1, 2, 3))))

    def test_candidate_baseband_durations_match(self) -> None:
        bpsk = acquisition_baseband("bpsk")
        gfsk = acquisition_baseband("4gfsk")
        self.assertEqual(len(bpsk), len(gfsk))
        self.assertGreater(len(bpsk), 127 * EXTREME_SAMPLES_PER_SYMBOL)
        self.assertIs(bpsk, acquisition_baseband("bpsk"))
        self.assertIs(gfsk, acquisition_baseband("4gfsk"))
        self.assertFalse(bpsk.flags.writeable)
        self.assertFalse(gfsk.flags.writeable)

    def test_audio_is_finite_mono_and_bounded(self) -> None:
        for modulation in ("bpsk", "4gfsk"):
            with self.subTest(modulation=modulation):
                audio = generate_acquisition_audio(modulation)
                self.assertEqual(audio.sample_rate, EXTREME_SAMPLE_RATE)
                self.assertEqual(audio.channel_count, 1)
                self.assertTrue(np.isfinite(audio.samples).all())
                self.assertLessEqual(float(np.max(np.abs(audio.samples))), 0.95)

    def test_clean_acquisition_finds_unknown_start_and_frequency(self) -> None:
        leading = 389
        for modulation in ("bpsk", "4gfsk"):
            with self.subTest(modulation=modulation):
                audio = generate_acquisition_audio(
                    modulation,
                    leading_silence_samples=leading,
                    frequency_offset_hz=0.5,
                )
                result = search_acquisition(
                    audio,
                    modulation,
                    frequency_search_hz=(0.0, 0.5, 1.0),
                )
                self.assertEqual(result.sample_index, leading)
                self.assertAlmostEqual(result.refined_sample_index, leading, delta=0.1)
                self.assertEqual(result.frequency_offset_hz, 0.5)
                self.assertGreater(result.peak_to_median, 5.0)
                self.assertGreater(result.peak_curvature, 0.0)

    def test_clock_hypothesis_recovers_resampled_acquisition(self) -> None:
        clean = generate_acquisition_audio("4gfsk", leading_silence_samples=389)
        impaired = apply_audio_channel(
            clean,
            AudioChannelConfig(clock_error_ppm=75.0),
            np.random.default_rng(8),
        )
        result = search_acquisition(
            impaired,
            "4gfsk",
            frequency_search_hz=(0.0,),
            clock_search_ppm=(0.0, 50.0, 75.0, 100.0),
        )
        self.assertEqual(result.clock_error_ppm, 75.0)
        self.assertGreater(result.clock_metric_margin, 0.0)


if __name__ == "__main__":
    unittest.main()
