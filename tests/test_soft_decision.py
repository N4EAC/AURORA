"""Tests for Aurora soft-decision demapping and FEC."""

import unittest

import numpy as np

from dsp import decode_soft_symbols, encode_payload
from dsp.fec import convolutional_encode, viterbi_decode_soft
from dsp.soft_decision import soft_demapping


class SoftDecisionTests(unittest.TestCase):
    def test_qpsk_likelihood_signs_match_bits(self) -> None:
        symbols = np.array([complex(0.6, -0.4), complex(-0.3, 0.8)])
        likelihoods = soft_demapping(symbols, "qpsk", noise_variance=0.5)
        self.assertEqual((likelihoods > 0.0).tolist(), [True, False, False, True])

    def test_soft_viterbi_recovers_noisy_codeword(self) -> None:
        random = np.random.default_rng(2026)
        source = [1, 0, 1, 1, 0, 0, 1, 0] * 8
        encoded = np.asarray(convolutional_encode(source))
        received = 1.0 - 2.0 * encoded + random.normal(0.0, 0.55, len(encoded))
        self.assertEqual(viterbi_decode_soft(received), source)

    def test_soft_payload_round_trip(self) -> None:
        transmission = encode_payload(b"soft Aurora")
        decoded = decode_soft_symbols(
            transmission.symbols, transmission.modulation, noise_variance=0.1
        )
        self.assertEqual(decoded.payload, b"soft Aurora")


if __name__ == "__main__":
    unittest.main()
