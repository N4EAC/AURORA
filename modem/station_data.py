"""Compact structured station data carried in AX.25 UI frames."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import struct

from dsp.core import EncodedTransmission, encode_payload
from dsp.framing import Frame, build_frame
from modem.ax25 import Ax25Address, Ax25Error, Ax25UiFrame, decode_ui_frame, encode_ui_frame
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition
from modem.bootstrap import (
    AirTransmission,
    FRAME_TYPE_AX25_STATION,
    build_air_transmission,
)


AURORA_FLAG_AX25 = 0x01
STATION_DATA_MAGIC = b"AU"
STATION_DATA_VERSION = 1
_GRID_PATTERN = re.compile(
    r"^[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StationData:
    """Identity and optional location data for one amateur station."""

    callsign: str
    grid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    comment: str | None = None
    operator_name: str | None = None

    def __post_init__(self) -> None:
        address = Ax25Address.parse(self.callsign)
        object.__setattr__(self, "callsign", str(address))
        if self.grid is not None:
            grid = self.grid.strip().upper()
            if not _GRID_PATTERN.fullmatch(grid):
                raise ValueError("Grid must be a valid 4, 6, or 8 character locator")
            object.__setattr__(self, "grid", grid)
        position_values = (self.latitude, self.longitude)
        if (position_values[0] is None) != (position_values[1] is None):
            raise ValueError("Latitude and longitude must be supplied together")
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        if self.altitude_m is not None and not math.isfinite(self.altitude_m):
            raise ValueError("Altitude must be finite")
        if self.comment is not None:
            comment = self.comment.strip()
            if len(comment.encode("utf-8")) > 80:
                raise ValueError("Station comment must not exceed 80 UTF-8 bytes")
            object.__setattr__(self, "comment", comment or None)
        if self.operator_name is not None:
            name = self.operator_name.strip()
            if len(name.encode("utf-8")) > 80:
                raise ValueError("Operator name must not exceed 80 UTF-8 bytes")
            object.__setattr__(self, "operator_name", name or None)


@dataclass(frozen=True, slots=True)
class StationDataFrame:
    """Decoded station record and its AX.25 destination."""

    destination: Ax25Address
    data: StationData


def _field(field_type: int, value: bytes) -> bytes:
    if len(value) > 255:
        raise ValueError("Station-data field exceeds 255 bytes")
    return bytes((field_type, len(value))) + value


def encode_station_information(data: StationData) -> bytes:
    """Encode optional station properties as a versioned compact TLV payload."""
    encoded = bytearray(STATION_DATA_MAGIC + bytes((STATION_DATA_VERSION,)))
    if data.grid is not None:
        encoded.extend(_field(1, data.grid.encode("ascii")))
    if data.latitude is not None and data.longitude is not None:
        encoded.extend(
            _field(
                2,
                struct.pack(">ii", round(data.latitude * 1_000_000), round(data.longitude * 1_000_000)),
            )
        )
    if data.altitude_m is not None:
        encoded.extend(_field(3, struct.pack(">i", round(data.altitude_m * 100))))
    if data.comment is not None:
        encoded.extend(_field(4, data.comment.encode("utf-8")))
    if data.operator_name is not None:
        encoded.extend(_field(5, data.operator_name.encode("utf-8")))
    return bytes(encoded)


def decode_station_information(callsign: str, encoded: bytes) -> StationData:
    """Decode a compact station-data information field."""
    payload = bytes(encoded)
    if len(payload) < 3 or payload[:2] != STATION_DATA_MAGIC:
        raise Ax25Error("Station-data magic is invalid")
    if payload[2] != STATION_DATA_VERSION:
        raise Ax25Error(f"Unsupported station-data version: {payload[2]}")
    values: dict[int, bytes] = {}
    offset = 3
    while offset < len(payload):
        if offset + 2 > len(payload):
            raise Ax25Error("Station-data TLV header is incomplete")
        field_type, length = payload[offset], payload[offset + 1]
        offset += 2
        if offset + length > len(payload):
            raise Ax25Error("Station-data TLV value is incomplete")
        if field_type in values:
            raise Ax25Error("Station-data field is duplicated")
        values[field_type] = payload[offset : offset + length]
        offset += length
    try:
        grid = values[1].decode("ascii") if 1 in values else None
        latitude = longitude = None
        if 2 in values:
            if len(values[2]) != 8:
                raise Ax25Error("Station GPS field has invalid length")
            latitude_raw, longitude_raw = struct.unpack(">ii", values[2])
            latitude = latitude_raw / 1_000_000.0
            longitude = longitude_raw / 1_000_000.0
        altitude = None
        if 3 in values:
            if len(values[3]) != 4:
                raise Ax25Error("Station altitude field has invalid length")
            altitude = struct.unpack(">i", values[3])[0] / 100.0
        comment = values[4].decode("utf-8") if 4 in values else None
        operator_name = values[5].decode("utf-8") if 5 in values else None
    except (UnicodeDecodeError, struct.error) as error:
        raise Ax25Error("Station-data field encoding is invalid") from error
    return StationData(
        callsign, grid, latitude, longitude, altitude, comment, operator_name
    )


def build_station_ax25(
    data: StationData,
    destination: str = "AURORA",
) -> bytes:
    """Build an AX.25 UI frame carrying one Aurora station record."""
    return encode_ui_frame(
        Ax25UiFrame(
            Ax25Address.parse(destination),
            Ax25Address.parse(data.callsign),
            encode_station_information(data),
        )
    )


def parse_station_ax25(encoded: bytes) -> StationDataFrame:
    """Validate an AX.25 UI frame and decode its Aurora station record."""
    frame = decode_ui_frame(encoded)
    data = decode_station_information(str(frame.source), frame.information)
    return StationDataFrame(frame.destination, data)


def encode_station_transmission(
    data: StationData,
    *,
    destination: str = "AURORA",
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> EncodedTransmission:
    """Protect one AX.25 station frame with Aurora framing, FEC, and mapping."""
    return encode_payload(
        build_station_ax25(data, destination),
        flags=AURORA_FLAG_AX25,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )


def encode_station_air_transmission(
    data: StationData,
    *,
    destination: str = "AURORA",
    frame_id: int,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> AirTransmission:
    """Build bootstrapped AX.25 station data without chat text."""
    native = build_station_ax25(data, destination)
    payload = encode_payload(
        native,
        flags=AURORA_FLAG_AX25,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )
    return build_air_transmission(
        payload,
        payload_size=len(build_frame(native, AURORA_FLAG_AX25)),
        frame_type=FRAME_TYPE_AX25_STATION,
        frame_id=frame_id,
        mode=mode,
    )


def decode_station_transport(frame: Frame) -> StationDataFrame:
    """Decode AX.25 station data from a CRC-valid Aurora frame."""
    if not frame.flags & AURORA_FLAG_AX25:
        raise Ax25Error("Aurora frame does not contain AX.25 transport data")
    return parse_station_ax25(frame.payload)
