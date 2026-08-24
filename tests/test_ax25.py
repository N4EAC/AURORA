"""Tests for Aurora's parallel AX.25 UI-frame transport."""

import unittest

from dsp.core import decode_soft_symbols, decode_transmission
from dsp.waveform import demodulate_audio, modulate_audio
from modem import AURORA_2300_MODE
from modem.ax25 import (
    AX25_NO_LAYER3_PID,
    Ax25Address,
    Ax25Error,
    Ax25UiFrame,
    crc16_x25,
    decode_ui_frame,
    encode_ui_frame,
)
from modem.station_data import (
    AURORA_FLAG_AX25,
    StationData,
    build_station_ax25,
    decode_station_transport,
    encode_station_transmission,
    parse_station_ax25,
)


class Ax25Tests(unittest.TestCase):
    def test_x25_crc_standard_check_value(self) -> None:
        self.assertEqual(crc16_x25(b"123456789"), 0x906E)

    def test_callsign_and_ssid_normalization(self) -> None:
        self.assertEqual(str(Ax25Address.parse("n4eac-7")), "N4EAC-7")
        with self.assertRaises(Ax25Error):
            Ax25Address.parse("TOOLONG")

    def test_ui_frame_round_trip_and_fcs_rejection(self) -> None:
        frame = Ax25UiFrame(
            Ax25Address("AURORA"),
            Ax25Address("N4EAC", 2),
            b"station payload",
        )
        encoded = encode_ui_frame(frame)
        decoded = decode_ui_frame(encoded)
        self.assertEqual(decoded, frame)
        self.assertEqual(decoded.pid, AX25_NO_LAYER3_PID)
        corrupted = bytearray(encoded)
        corrupted[-3] ^= 0x01
        with self.assertRaisesRegex(Ax25Error, "FCS"):
            decode_ui_frame(corrupted)

    def test_station_data_round_trip(self) -> None:
        original = StationData(
            "N4EAC-1",
            grid="FM18LW",
            latitude=38.8977,
            longitude=-77.0365,
            altitude_m=18.25,
            comment="Aurora test station",
        )
        decoded = parse_station_ax25(build_station_ax25(original))
        self.assertEqual(str(decoded.destination), "AURORA")
        self.assertEqual(decoded.data.callsign, original.callsign)
        self.assertEqual(decoded.data.grid, original.grid)
        self.assertAlmostEqual(decoded.data.latitude, original.latitude, places=6)
        self.assertAlmostEqual(decoded.data.longitude, original.longitude, places=6)
        self.assertEqual(decoded.data.altitude_m, original.altitude_m)
        self.assertEqual(decoded.data.comment, original.comment)

    def test_ax25_transport_coexists_with_native_aurora_frames(self) -> None:
        transmission = encode_station_transmission(
            StationData("N4EAC", grid="FM18")
        )
        aurora_frame = decode_transmission(transmission)
        self.assertEqual(aurora_frame.flags, AURORA_FLAG_AX25)
        decoded = decode_station_transport(aurora_frame)
        self.assertEqual(decoded.data.callsign, "N4EAC")
        self.assertEqual(decoded.data.grid, "FM18")

    def test_station_transport_round_trips_through_ofdm_audio(self) -> None:
        mode = AURORA_2300_MODE
        transmission = encode_station_transmission(
            StationData("N4EAC", grid="FM18LW", latitude=38.8977, longitude=-77.0365),
            mode=mode,
        )
        audio = modulate_audio(transmission.symbols, mode)
        recovered = demodulate_audio(audio, len(transmission.symbols), mode)
        aurora_frame = decode_soft_symbols(
            tuple(recovered.symbols),
            mode.modulation,
            interleaver_columns=mode.interleaver_columns,
        )
        decoded = decode_station_transport(aurora_frame)
        self.assertEqual(decoded.data.callsign, "N4EAC")
        self.assertEqual(decoded.data.grid, "FM18LW")

    def test_station_location_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "together"):
            StationData("N4EAC", latitude=38.0)
        with self.assertRaisesRegex(ValueError, "Grid"):
            StationData("N4EAC", grid="INVALID")


if __name__ == "__main__":
    unittest.main()
