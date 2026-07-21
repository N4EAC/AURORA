"""Synthetic baseband tests for the Aurora receiver front end."""

import math
import unittest

import numpy as np

from dsp.preamble import acquisition_preamble
from dsp.receiver import AuroraReceiver, ReceiverConfig


class ReceiverTests(unittest.TestCase):
    def test_receiver_acquires_and_reports_impairments(self) -> None:
        sample_rate = 12_000.0
        samples_per_symbol = 4
        preamble = acquisition_preamble(samples_per_symbol)
        payload_symbols = np.asarray([1.0, -1.0, 1.0, 1.0, -1.0] * 8)
        payload = np.repeat(payload_symbols, samples_per_symbol)
        prefix = np.zeros(29, dtype=np.complex128)
        clean = np.concatenate((prefix, preamble, payload))

        expected_offset = 18.0
        indices = np.arange(len(clean))
        impaired = clean * np.exp(
            2j * math.pi * expected_offset * indices / sample_rate
        )
        receiver = AuroraReceiver(
            ReceiverConfig(preamble=preamble, sync_threshold=0.7)
        )
        result = receiver.process(impaired)

        self.assertTrue(result.diagnostics.synchronized)
        self.assertGreater(result.diagnostics.sync_metric, 0.9)
        self.assertAlmostEqual(
            result.diagnostics.frequency_offset_hz, expected_offset, places=5
        )
        self.assertGreaterEqual(len(result.symbols), len(payload_symbols) - 1)
        self.assertTrue(np.isfinite(result.diagnostics.timing_error))


if __name__ == "__main__":
    unittest.main()
