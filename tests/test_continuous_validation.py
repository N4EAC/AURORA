"""Tests for reproducible Aurora continuous-receiver validation."""

import unittest

from modem.continuous_validation import (
    ContinuousNoiseValidationConfig,
    run_continuous_noise_validation,
)


class ContinuousNoiseValidationTests(unittest.TestCase):
    def test_small_campaign_is_deterministic_and_reports_domain(self) -> None:
        config = ContinuousNoiseValidationConfig(trials=2)

        first = run_continuous_noise_validation(config)
        second = run_continuous_noise_validation(config)

        self.assertEqual(first.false_decodes, second.false_decodes)
        self.assertEqual(first.noise_trials, 2)
        self.assertEqual(first.next_trial, 2)
        self.assertEqual(first.measurement_domain, "continuous_receiver_noise")
        self.assertFalse(first.over_the_air_protocol)

    def test_batch_range_is_resumable(self) -> None:
        result = run_continuous_noise_validation(
            ContinuousNoiseValidationConfig(
                trials=10,
                start_trial=25,
                batch_size=1,
            )
        )

        self.assertEqual(result.noise_trials, 1)
        self.assertEqual(result.start_trial, 25)
        self.assertEqual(result.next_trial, 26)

    def test_invalid_worker_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Worker"):
            ContinuousNoiseValidationConfig(workers=0)


if __name__ == "__main__":
    unittest.main()
