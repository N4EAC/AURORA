"""Tests for the centralized Aurora robust simulation-mode definition."""

import unittest

from dsp.fec import CONSTRAINT_LENGTH, GENERATOR_POLYNOMIALS
from gui.testing_controller import SweepConfig
from modem import AURORA_ROBUST_MODE


class ModeDefinitionTests(unittest.TestCase):
    def test_robust_mode_selects_documented_parameters(self) -> None:
        mode = AURORA_ROBUST_MODE
        self.assertEqual(mode.modulation, "bpsk")
        self.assertEqual(mode.symbol_rate, 31.25)
        self.assertEqual((mode.fec_rate_numerator, mode.fec_rate_denominator), (1, 2))
        self.assertTrue(mode.fec_terminated)
        self.assertEqual(mode.interleaver_columns, 16)
        self.assertFalse(mode.interleaver_geometry_signaled)
        self.assertEqual(mode.audio_sample_rate, 12_000)
        self.assertEqual(mode.audio_carrier_hz, 1_500.0)
        self.assertEqual(mode.pulse_shape, "root_raised_cosine")
        self.assertEqual(mode.pulse_rolloff, 0.35)
        self.assertEqual(mode.pulse_span_symbols, 8)

    def test_mode_fec_selection_matches_dsp_implementation(self) -> None:
        self.assertEqual(AURORA_ROBUST_MODE.fec_constraint_length, CONSTRAINT_LENGTH)
        self.assertEqual(
            AURORA_ROBUST_MODE.fec_generator_polynomials,
            GENERATOR_POLYNOMIALS,
        )

    def test_sweep_defaults_to_robust_mode_geometry(self) -> None:
        config = SweepConfig()
        self.assertEqual(config.symbol_rate, AURORA_ROBUST_MODE.symbol_rate)
        self.assertEqual(
            config.interleaver_columns,
            AURORA_ROBUST_MODE.interleaver_columns,
        )


if __name__ == "__main__":
    unittest.main()
