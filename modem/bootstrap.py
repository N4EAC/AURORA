"""Protected geometry header preceding variable-length Aurora payloads."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from dsp.core import EncodedTransmission, encode_payload
from dsp.framing import Frame
from modem.mode_definition import ModeDefinition


BOOTSTRAP_MAGIC = b"AB"
BOOTSTRAP_VERSION = 1
AURORA_FLAG_BOOTSTRAP = 0x80
FRAME_TYPE_CHAT = 1
FRAME_TYPE_AX25_STATION = 2
FRAME_TYPE_RECEPTION_REPORT = 3
_FORMAT = ">2sBBBBBBHHI"
BOOTSTRAP_SIZE = struct.calcsize(_FORMAT)
_BANDWIDTH_CODES = {500: 1, 2_300: 2, 2_800: 3}
_CODE_BANDWIDTHS = {value: key for key, value in _BANDWIDTH_CODES.items()}
_MODULATION_BPSK = 1
_FEC_CONVOLUTIONAL_RATE_HALF = 1


@dataclass(frozen=True, slots=True)
class BootstrapHeader:
    """Geometry required to decode the following protected payload."""

    frame_type: int
    bandwidth_hz: int
    interleaver_columns: int
    payload_symbol_count: int
    payload_size: int
    frame_id: int


@dataclass(frozen=True, slots=True)
class AirTransmission:
    """Bootstrap and variable-length payload symbols sent as one OFDM frame."""

    symbols: tuple[complex, ...]
    modulation: str
    bootstrap_symbol_count: int
    payload_symbol_count: int
    frame_id: int
    frame_type: int


def build_bootstrap(header: BootstrapHeader) -> bytes:
    """Serialize and validate one fixed-size bootstrap header."""
    if header.frame_type not in {
        FRAME_TYPE_CHAT,
        FRAME_TYPE_AX25_STATION,
        FRAME_TYPE_RECEPTION_REPORT,
    }:
        raise ValueError("Unknown Aurora bootstrap frame type")
    if header.bandwidth_hz not in _BANDWIDTH_CODES:
        raise ValueError("Bootstrap bandwidth must be 500, 2300, or 2800 Hz")
    if not 1 <= header.interleaver_columns <= 255:
        raise ValueError("Bootstrap interleaver geometry is invalid")
    if not 1 <= header.payload_symbol_count <= 65_535:
        raise ValueError("Bootstrap payload symbol count is invalid")
    if not 1 <= header.payload_size <= 65_535:
        raise ValueError("Bootstrap payload size is invalid")
    if not 0 <= header.frame_id <= 0xFFFFFFFF:
        raise ValueError("Bootstrap frame ID is invalid")
    return struct.pack(
        _FORMAT,
        BOOTSTRAP_MAGIC,
        BOOTSTRAP_VERSION,
        header.frame_type,
        _BANDWIDTH_CODES[header.bandwidth_hz],
        _MODULATION_BPSK,
        _FEC_CONVOLUTIONAL_RATE_HALF,
        header.interleaver_columns,
        header.payload_symbol_count,
        header.payload_size,
        header.frame_id,
    )


def parse_bootstrap(encoded: bytes) -> BootstrapHeader:
    """Decode one bootstrap header after Aurora CRC validation."""
    if len(encoded) != BOOTSTRAP_SIZE:
        raise ValueError("Aurora bootstrap length is invalid")
    (
        magic,
        version,
        frame_type,
        bandwidth_code,
        modulation_code,
        fec_code,
        columns,
        symbols,
        size,
        frame_id,
    ) = struct.unpack(_FORMAT, encoded)
    if magic != BOOTSTRAP_MAGIC or version != BOOTSTRAP_VERSION:
        raise ValueError("Aurora bootstrap identity is invalid")
    if modulation_code != _MODULATION_BPSK:
        raise ValueError("Aurora bootstrap modulation is unsupported")
    if fec_code != _FEC_CONVOLUTIONAL_RATE_HALF:
        raise ValueError("Aurora bootstrap FEC profile is unsupported")
    try:
        bandwidth = _CODE_BANDWIDTHS[bandwidth_code]
    except KeyError as error:
        raise ValueError("Aurora bootstrap bandwidth code is invalid") from error
    header = BootstrapHeader(frame_type, bandwidth, columns, symbols, size, frame_id)
    build_bootstrap(header)
    return header


def encode_bootstrap(header: BootstrapHeader, mode: ModeDefinition) -> EncodedTransmission:
    """Protect a bootstrap using the candidate payload mode geometry."""
    return encode_payload(
        build_bootstrap(header),
        flags=AURORA_FLAG_BOOTSTRAP,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )


def decode_bootstrap_frame(frame: Frame) -> BootstrapHeader:
    """Validate the Aurora frame type and parse bootstrap metadata."""
    if frame.flags != AURORA_FLAG_BOOTSTRAP:
        raise ValueError("Aurora frame is not a bootstrap")
    return parse_bootstrap(frame.payload)


def bootstrap_symbol_count(mode: ModeDefinition) -> int:
    """Return the fixed protected bootstrap symbol count for a mode."""
    header = BootstrapHeader(
        FRAME_TYPE_CHAT,
        mode.occupied_bandwidth_hz,
        mode.interleaver_columns,
        1,
        1,
        0,
    )
    return len(encode_bootstrap(header, mode).symbols)


def build_air_transmission(
    payload: EncodedTransmission,
    *,
    payload_size: int,
    frame_type: int,
    frame_id: int,
    mode: ModeDefinition,
) -> AirTransmission:
    """Prefix a protected payload with its protected decode geometry."""
    header = BootstrapHeader(
        frame_type,
        mode.occupied_bandwidth_hz,
        mode.interleaver_columns,
        len(payload.symbols),
        payload_size,
        frame_id,
    )
    bootstrap = encode_bootstrap(header, mode)
    return AirTransmission(
        bootstrap.symbols + payload.symbols,
        mode.modulation,
        len(bootstrap.symbols),
        len(payload.symbols),
        frame_id,
        frame_type,
    )
