"""Tests for Aurora symbol timing recovery."""

import unittest

import numpy as np

from dsp.timing_recovery import gardner_timing_recovery


class TimingRecoveryTests(unittest.TestCase):
    def test_fractionally_shifted_symbols_are_recovered(self) -> None:
        symbols = np.asarray(([1.0, -1.0, 1.0, 1.0, -1.0] * 12), dtype=float)
        oversampled = np.repeat(symbols, 4)
        positions = np.arange(len(oversampled), dtype=float) - 0.35
        shifted = np.interp(
            positions,
            np.arange(len(oversampled), dtype=float),
            oversampled,
            left=oversampled[0],
            right=oversampled[-1],
        ).astype(np.complex128)
        result = gardner_timing_recovery(shifted, 4.0, loop_gain=0.02)
        decisions = np.where(result.symbols.real >= 0.0, 1.0, -1.0)
        np.testing.assert_array_equal(decisions[: len(symbols)], symbols)
        self.assertTrue(np.isfinite(result.mean_error))

    def test_undersampled_input_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "two samples"):
            gardner_timing_recovery(np.ones(20), 1.5)


if __name__ == "__main__":
    unittest.main()
