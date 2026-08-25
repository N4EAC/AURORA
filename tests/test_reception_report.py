"""Tests for compact native Aurora reception reports."""

import unittest

from dsp.core import decode_transmission
from modem.reception_report import (
    ReceptionReport,
    decode_reception_report,
    encode_reception_report,
)


class ReceptionReportTests(unittest.TestCase):
    def test_fixed_point_report_round_trip(self) -> None:
        original = ReceptionReport("N4EAC", 12345, -12.4, 1.7, -2.0, 8)
        decoded = decode_reception_report(
            decode_transmission(encode_reception_report(original))
        )
        self.assertEqual(decoded, original)


if __name__ == "__main__":
    unittest.main()
