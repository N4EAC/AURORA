"""Tests for Aurora symbol mapping."""

import unittest

from dsp.symbol_mapper import demap_symbols, map_bits


class SymbolMapperTests(unittest.TestCase):
    def test_bpsk_round_trip(self) -> None:
        bits = [0, 1, 1, 0]
        self.assertEqual(demap_symbols(map_bits(bits, "bpsk"), "bpsk"), bits)

    def test_qpsk_round_trip(self) -> None:
        bits = [0, 0, 0, 1, 1, 1, 1, 0]
        self.assertEqual(demap_symbols(map_bits(bits, "qpsk"), "qpsk"), bits)

    def test_hard_decisions_tolerate_small_offsets(self) -> None:
        symbols = [complex(0.2, -0.3), complex(-0.4, 0.1)]
        self.assertEqual(demap_symbols(symbols, "qpsk"), [0, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()
