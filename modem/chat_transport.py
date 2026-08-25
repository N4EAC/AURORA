"""Variable-length native Aurora chat transport."""

from __future__ import annotations

from dataclasses import dataclass
import secrets
import struct

from dsp.core import EncodedTransmission, encode_payload
from dsp.framing import Frame, build_frame
from modem.ax25 import Ax25Address
from modem.bootstrap import AirTransmission, FRAME_TYPE_CHAT, build_air_transmission
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


AURORA_FLAG_CHAT = 0x02
CHAT_MAGIC = b"AC"
CHAT_VERSION = 2
CHAT_TEXT_BYTES = 512
_HEADER_FORMAT = ">2sBIBBH"
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One decoded native Aurora message."""

    callsign: str
    text: str
    destination: str = "AURORA"
    frame_id: int = 0


def build_native_chat(
    callsign: str,
    text: str,
    *,
    destination: str = "AURORA",
    frame_id: int = 0,
) -> bytes:
    """Serialize native chat without AX.25 headers or fixed-size padding."""
    source = str(Ax25Address.parse(callsign)).encode("ascii")
    target = str(Ax25Address.parse(destination)).encode("ascii")
    message = text.strip().encode("utf-8")
    if not message:
        raise ValueError("Enter a chat message")
    if len(message) > CHAT_TEXT_BYTES:
        raise ValueError(f"Chat message must not exceed {CHAT_TEXT_BYTES} UTF-8 bytes")
    if not 0 <= frame_id <= 0xFFFFFFFF:
        raise ValueError("Chat frame ID is invalid")
    return (
        struct.pack(
            _HEADER_FORMAT,
            CHAT_MAGIC,
            CHAT_VERSION,
            frame_id,
            len(source),
            len(target),
            len(message),
        )
        + source
        + target
        + message
    )


def parse_native_chat(encoded: bytes) -> ChatMessage:
    """Validate and decode one variable-length native chat payload."""
    payload = bytes(encoded)
    if len(payload) < _HEADER_SIZE:
        raise ValueError("Native Aurora chat is too short")
    magic, version, frame_id, source_size, target_size, text_size = struct.unpack(
        _HEADER_FORMAT, payload[:_HEADER_SIZE]
    )
    if magic != CHAT_MAGIC or version != CHAT_VERSION:
        raise ValueError("Native Aurora chat identity is invalid")
    expected = _HEADER_SIZE + source_size + target_size + text_size
    if len(payload) != expected or text_size > CHAT_TEXT_BYTES:
        raise ValueError("Native Aurora chat length is invalid")
    offset = _HEADER_SIZE
    try:
        source = payload[offset : offset + source_size].decode("ascii")
        offset += source_size
        target = payload[offset : offset + target_size].decode("ascii")
        offset += target_size
        text = payload[offset:].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Native Aurora chat encoding is invalid") from error
    source = str(Ax25Address.parse(source))
    target = str(Ax25Address.parse(target))
    if not text:
        raise ValueError("Native Aurora chat message is empty")
    return ChatMessage(source, text, target, frame_id)


def encode_chat_transmission(
    callsign: str,
    text: str,
    *,
    destination: str = "AURORA",
    frame_id: int = 0,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> EncodedTransmission:
    """Protect native variable-length chat with Aurora framing and FEC."""
    payload = build_native_chat(callsign, text, destination=destination, frame_id=frame_id)
    return encode_payload(
        payload,
        flags=AURORA_FLAG_CHAT,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )


def encode_chat_air_transmission(
    callsign: str,
    text: str,
    *,
    destination: str = "AURORA",
    frame_id: int | None = None,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> AirTransmission:
    """Build native chat plus its protected variable-length bootstrap."""
    identifier = secrets.randbits(32) if frame_id is None else frame_id
    native = build_native_chat(callsign, text, destination=destination, frame_id=identifier)
    payload = encode_payload(
        native,
        flags=AURORA_FLAG_CHAT,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )
    return build_air_transmission(
        payload,
        payload_size=len(build_frame(native, AURORA_FLAG_CHAT)),
        frame_type=FRAME_TYPE_CHAT,
        frame_id=identifier,
        mode=mode,
    )


def decode_chat_transport(frame: Frame) -> ChatMessage:
    """Decode native chat from a CRC-valid Aurora frame."""
    if frame.flags != AURORA_FLAG_CHAT:
        raise ValueError("Aurora frame does not contain native chat")
    return parse_native_chat(frame.payload)
