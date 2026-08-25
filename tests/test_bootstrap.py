"""Tests for Aurora variable-length bootstrap metadata."""

import unittest

from dsp.core import decode_transmission, encode_payload
from dsp.framing import build_frame
from modem.bootstrap import (
    BootstrapHeader,
    FRAME_TYPE_CHAT,
    build_air_transmission,
    decode_bootstrap_frame,
    encode_bootstrap,
    parse_bootstrap,
    build_bootstrap,
)
from modem.mode_definition import AURORA_2300_MODE


class BootstrapTests(unittest.TestCase):
    def test_header_round_trip(self) -> None:
        original = BootstrapHeader(FRAME_TYPE_CHAT, 2_300, 42, 812, 50, 1234)
        self.assertEqual(parse_bootstrap(build_bootstrap(original)), original)

    def test_protected_bootstrap_round_trip(self) -> None:
        header = BootstrapHeader(FRAME_TYPE_CHAT, 2_300, 42, 812, 50, 1234)
        decoded = decode_bootstrap_frame(
            decode_transmission(encode_bootstrap(header, AURORA_2300_MODE))
        )
        self.assertEqual(decoded, header)

    def test_air_geometry_matches_payload(self) -> None:
        payload_bytes = b"short native payload"
        payload = encode_payload(
            payload_bytes,
            flags=2,
            interleaver_columns=AURORA_2300_MODE.interleaver_columns,
        )
        air = build_air_transmission(
            payload,
            payload_size=len(build_frame(payload_bytes, 2)),
            frame_type=FRAME_TYPE_CHAT,
            frame_id=44,
            mode=AURORA_2300_MODE,
        )
        self.assertEqual(air.payload_symbol_count, len(payload.symbols))


if __name__ == "__main__":
    unittest.main()
