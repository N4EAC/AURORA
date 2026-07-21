"""Binary framing for Aurora payloads."""

from dataclasses import dataclass
import struct

from dsp.crc import crc16_ccitt, verify_crc16


SYNC_WORD = b"\xA7\x4D\x92\x6B"
PROTOCOL_VERSION = 1
MAX_PAYLOAD_SIZE = 65_535
HEADER_FORMAT = ">4sBBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
CRC_SIZE = 2


class FrameError(ValueError):
    """Raised when an Aurora frame is malformed or fails validation."""


@dataclass(frozen=True, slots=True)
class Frame:
    """Decoded Aurora frame fields."""

    payload: bytes
    flags: int
    version: int


def build_frame(payload: bytes, flags: int = 0) -> bytes:
    """Build an Aurora frame containing *payload*."""
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("Payload exceeds the Aurora frame size limit")
    if not 0 <= flags <= 0xFF:
        raise ValueError("Flags must fit in one byte")

    body = struct.pack(">BBH", PROTOCOL_VERSION, flags, len(payload)) + payload
    return SYNC_WORD + body + struct.pack(">H", crc16_ccitt(body))


def parse_frame(encoded: bytes) -> Frame:
    """Parse and validate an encoded Aurora frame."""
    encoded = bytes(encoded)
    minimum_size = HEADER_SIZE + CRC_SIZE
    if len(encoded) < minimum_size:
        raise FrameError("Frame is too short")

    sync_word, version, flags, payload_size = struct.unpack(
        HEADER_FORMAT, encoded[:HEADER_SIZE]
    )
    if sync_word != SYNC_WORD:
        raise FrameError("Frame sync word is invalid")
    if version != PROTOCOL_VERSION:
        raise FrameError(f"Unsupported frame version: {version}")

    expected_size = HEADER_SIZE + payload_size + CRC_SIZE
    if len(encoded) != expected_size:
        raise FrameError("Frame length does not match its header")

    body = encoded[len(SYNC_WORD) : -CRC_SIZE]
    received_crc = struct.unpack(">H", encoded[-CRC_SIZE:])[0]
    if not verify_crc16(body, received_crc):
        raise FrameError("Frame CRC validation failed")

    return Frame(encoded[HEADER_SIZE:-CRC_SIZE], flags, version)
