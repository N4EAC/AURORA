"""Tests for deterministic bootstrap characterization."""

import unittest

from modem.bootstrap_validation import run_bootstrap_characterization


class BootstrapValidationTests(unittest.TestCase):
    def test_clean_margin_decodes_and_noise_does_not(self) -> None:
        result = run_bootstrap_characterization(
            snr_db=15.0,
            signal_trials=3,
            noise_trials=5,
            seed=25,
        )
        self.assertEqual(result.decoded_signals, 3)
        self.assertEqual(result.false_decodes, 0)
        self.assertGreater(result.mean_sync_metric, 0.45)


if __name__ == "__main__":
    unittest.main()
