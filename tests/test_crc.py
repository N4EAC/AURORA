"""Tests for Aurora CRC calculation."""

import unittest

from dsp.crc import crc16_ccitt, verify_crc16


class CrcTests(unittest.TestCase):
    def test_standard_check_value(self) -> None:
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_verification_rejects_changed_data(self) -> None:
        checksum = crc16_ccitt(b"Aurora")
        self.assertTrue(verify_crc16(b"Aurora", checksum))
        self.assertFalse(verify_crc16(b"aurora", checksum))


if __name__ == "__main__":
    unittest.main()
