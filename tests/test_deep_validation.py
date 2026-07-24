"""Tests for batched Aurora Deep validation campaigns."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from dsp.deep_codec import DeepCodecConfig, K10_RATE_QUARTER_GENERATORS
from modem.deep_validation import DeepValidationConfig, run_deep_validation
from modem.mode_definition import AURORA_ROBUST_MODE


class DeepValidationTests(unittest.TestCase):
    def test_noise_uses_configured_soft_observation_count(self) -> None:
        decoded = (False, False, False, 0.0, 0.0, False, 0.0, 0.0)
        with (
            patch(
                "modem.deep_validation._noise_audio",
                wraps=__import__(
                    "modem.deep_validation", fromlist=["_noise_audio"]
                )._noise_audio,
            ) as noise_audio,
            patch(
                "modem.deep_validation._decode_soft_observations",
                return_value=decoded,
            ) as decode_observations,
        ):
            result = run_deep_validation(
                DeepValidationConfig(
                    signal_trials=0,
                    noise_trials=1,
                    soft_observation_count=2,
                )
            )
        self.assertEqual(result.noise_trials, 1)
        self.assertEqual(noise_audio.call_count, 2)
        self.assertEqual(len(decode_observations.call_args.args[0]), 2)

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

    def test_alternate_pilot_geometry_preserves_clean_decode(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                pilot_interval=64,
                pilot_symbol_count=8,
            )
        )
        self.assertEqual(result.decoded, 1)

    def test_alternate_symbol_rate_preserves_clean_decode(self) -> None:
        mode = replace(
            AURORA_ROBUST_MODE,
            name="Aurora 62.5 symbol research",
            symbol_rate=62.5,
        )
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                mode=mode,
            )
        )
        self.assertEqual(result.decoded, 1)

    def test_two_soft_observations_preserve_clean_decode(self) -> None:
        result = run_deep_validation(
            DeepValidationConfig(
                signal_trials=1,
                noise_trials=0,
                snr_db=20.0,
                soft_observation_count=2,
            )
        )
        self.assertEqual(result.decoded, 1)

    def test_soft_observation_count_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "observation count"):
            DeepValidationConfig(soft_observation_count=0)


if __name__ == "__main__":
    unittest.main()
