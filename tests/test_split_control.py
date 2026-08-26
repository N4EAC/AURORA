"""Tests for failure-safe fake-split Hamlib sequencing."""

import unittest
from unittest.mock import MagicMock

from radio.split_control import FakeSplitController


class SplitControlTests(unittest.TestCase):
    def test_transmit_and_receive_tunes_require_ptt_off_and_readback(self) -> None:
        hamlib = MagicMock()
        hamlib.get_frequency.side_effect = [7_107_000, 7_117_000]
        split = FakeSplitController(hamlib, settle_seconds=0, sleep=MagicMock())
        split.prepare_transmit(7_107_000)
        split.finish_transmit(7_117_000)
        self.assertEqual(
            hamlib.set_frequency.call_args_list[0].args[0], 7_107_000
        )
        self.assertEqual(
            hamlib.set_frequency.call_args_list[1].args[0], 7_117_000
        )
        self.assertGreaterEqual(hamlib.set_ptt.call_count, 2)

    def test_mismatched_readback_blocks_operation(self) -> None:
        hamlib = MagicMock()
        hamlib.get_frequency.return_value = 7_100_000
        split = FakeSplitController(hamlib, settle_seconds=0)
        with self.assertRaisesRegex(RuntimeError, "readback"):
            split.prepare_transmit(7_107_000)


if __name__ == "__main__":
    unittest.main()
