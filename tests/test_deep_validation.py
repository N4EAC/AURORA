"""Tests for batched Aurora Deep validation campaigns."""

import unittest

from dsp.deep_codec import DeepCodecConfig, K10_RATE_QUARTER_GENERATORS
from modem.deep_validation import DeepValidationConfig, run_deep_validation


class DeepValidationTests(unittest.TestCase):
    def test_small_clean_batch_decodes_and_reports_resources(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                measure_memory=True,
            )
        )
        self.assertEqual(result.signal_trials, 1)
        self.assertEqual(result.decoded, 1)
        self.assertEqual(result.next_trial, 1)
        self.assertGreater(result.elapsed_seconds, 0.0)
        self.assertGreater(result.peak_memory_bytes, 0)
        self.assertEqual(result.fading_equalized_trials, 0)
        self.assertFalse(result.over_the_air_protocol)

    def test_batch_range_is_resumable(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=5,
                noise_trials=0,
                start_trial=2,
                batch_size=1,
                snr_db=20.0,
            )
        )
        self.assertEqual(result.start_trial, 2)
        self.assertEqual(result.next_trial, 3)
        self.assertEqual(result.signal_trials, 1)

    def test_cancellation_stops_before_first_trial(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(signal_trials=2, noise_trials=0),
            should_continue=lambda: False,
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.signal_trials, 0)

    def test_fading_activation_ratio_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "activation gain ratio"):
            DeepValidationConfig(fading_activation_gain_ratio=-0.1)

    def test_fading_confidence_threshold_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence threshold"):
            DeepValidationConfig(fading_confidence_threshold=0.0)

    def test_acquisition_diversity_threshold_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "diversity score threshold"):
            DeepValidationConfig(acquisition_diversity_score_threshold=1.1)

    def test_acquisition_diversity_coherent_threshold_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "coherent threshold"):
            DeepValidationConfig(acquisition_diversity_coherent_threshold=0.0)

    def test_equalized_fallback_preserves_clean_decode(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                fading_equalization=True,
            )
        )
        self.assertEqual(result.decoded, 1)
        self.assertEqual(result.fading_equalized_trials, 0)

    def test_alternate_interleaver_geometry_preserves_clean_decode(self) -> None:
        codec = DeepCodecConfig(
            1,
            64,
            "native_rate_quarter",
            10,
            K10_RATE_QUARTER_GENERATORS,
        )
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                codec=codec,
            )
        )
        self.assertEqual(result.decoded, 1)


if __name__ == "__main__":
    unittest.main()
