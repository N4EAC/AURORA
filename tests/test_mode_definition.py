"""Tests for the centralized Aurora robust simulation-mode definition."""

import unittest

from dsp.fec import CONSTRAINT_LENGTH, GENERATOR_POLYNOMIALS
from gui.testing_controller import SweepConfig
from modem import AURORA_BANDWIDTH_MODES, AURORA_ROBUST_MODE


class ModeDefinitionTests(unittest.TestCase):
    def test_robust_mode_selects_documented_parameters(self) -> None:
        mode = AURORA_ROBUST_MODE
        self.assertEqual(mode.modulation, "bpsk")
        self.assertEqual(mode.symbol_rate, 300.0)
        self.assertEqual((mode.fec_rate_numerator, mode.fec_rate_denominator), (1, 2))
        self.assertTrue(mode.fec_terminated)
        self.assertEqual(mode.interleaver_columns, 8)
        self.assertFalse(mode.interleaver_geometry_signaled)
        self.assertEqual(mode.audio_sample_rate, 12_000)
        self.assertEqual(mode.audio_carrier_hz, 1_500.0)
        self.assertEqual(mode.pulse_shape, "ofdm")
        self.assertEqual(mode.waveform, "ofdm")

    def test_mode_fec_selection_matches_dsp_implementation(self) -> None:
        self.assertEqual(AURORA_ROBUST_MODE.fec_constraint_length, CONSTRAINT_LENGTH)
        self.assertEqual(
            AURORA_ROBUST_MODE.fec_generator_polynomials,
            GENERATOR_POLYNOMIALS,
        )

    def test_adaptive_profiles_match_documented_geometry(self) -> None:
        expected = {
            500: (300.0, 8, 4),
            2_300: (1_575.0, 42, 21),
            2_800: (1_950.0, 52, 26),
        }
        self.assertEqual(set(AURORA_BANDWIDTH_MODES), set(expected))
        for bandwidth, (rate, columns, edge) in expected.items():
            mode = AURORA_BANDWIDTH_MODES[bandwidth]
            self.assertEqual(mode.occupied_bandwidth_hz, bandwidth)
            self.assertEqual(mode.symbol_rate, rate)
            self.assertEqual(mode.interleaver_columns, columns)
            self.assertEqual(mode.ofdm_edge_subcarrier, edge)

    def test_sweep_defaults_to_robust_mode_geometry(self) -> None:
        config = SweepConfig()
        self.assertEqual(config.symbol_rate, AURORA_ROBUST_MODE.symbol_rate)
        self.assertEqual(
            config.interleaver_columns,
            AURORA_ROBUST_MODE.interleaver_columns,
        )


if __name__ == "__main__":
    unittest.main()
