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
CHAT_VERSION = 3
CHAT_TEXT_BYTES = 512
CHAT_FLAG_REPLY_TO = 0x01
CHAT_FLAG_BTY = 0x02
CHAT_FLAG_EOC = 0x04
_V2_HEADER_FORMAT = ">2sBIBBH"
_V2_HEADER_SIZE = struct.calcsize(_V2_HEADER_FORMAT)
_HEADER_FORMAT = ">2sBIBBBHBIIH"
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One decoded native Aurora message."""

    callsign: str
    text: str
    destination: str = "AURORA"
    frame_id: int = 0
    sender_name: str = ""
    contact_id: int = 0
    reply_frequency_hz: int | None = None
    reply_window_seconds: int = 0
    back_to_you: bool = False
    end_of_call: bool = False


def build_native_chat(
    callsign: str,
    text: str,
    *,
    destination: str = "AURORA",
    frame_id: int = 0,
    sender_name: str = "",
    contact_id: int = 0,
    reply_frequency_hz: int | None = None,
    reply_window_seconds: int = 0,
    back_to_you: bool = False,
    end_of_call: bool = False,
) -> bytes:
    """Serialize native chat without AX.25 headers or fixed-size padding."""
    source = str(Ax25Address.parse(callsign)).encode("ascii")
    target = str(Ax25Address.parse(destination)).encode("ascii")
    message = text.strip().encode("utf-8")
    name = sender_name.strip().encode("utf-8")
    if len(message) > CHAT_TEXT_BYTES:
        raise ValueError(f"Chat message must not exceed {CHAT_TEXT_BYTES} UTF-8 bytes")
    if not 0 <= frame_id <= 0xFFFFFFFF:
        raise ValueError("Chat frame ID is invalid")
    if len(name) > 80:
        raise ValueError("Operator name must not exceed 80 UTF-8 bytes")
    if not 0 <= contact_id <= 0xFFFFFFFF:
        raise ValueError("Contact ID is invalid")
    if reply_frequency_hz is not None and reply_frequency_hz <= 0:
        raise ValueError("Reply frequency must be positive")
    if not 0 <= reply_window_seconds <= 0xFFFF:
        raise ValueError("Reply window is invalid")
    flags = 0
    if reply_frequency_hz is not None:
        flags |= CHAT_FLAG_REPLY_TO
    if back_to_you:
        flags |= CHAT_FLAG_BTY
    if end_of_call:
        flags |= CHAT_FLAG_EOC
    if not message and not end_of_call:
        raise ValueError("Enter a chat message")
    if flags and contact_id == 0:
        raise ValueError("Contact metadata requires a contact ID")
    return (
        struct.pack(
            _HEADER_FORMAT,
            CHAT_MAGIC,
            CHAT_VERSION,
            frame_id,
            len(source),
            len(target),
            len(name),
            len(message),
            flags,
            contact_id,
            reply_frequency_hz or 0,
            reply_window_seconds,
        )
        + source
        + target
        + name
        + message
    )


def parse_native_chat(encoded: bytes) -> ChatMessage:
    """Validate and decode one variable-length native chat payload."""
    payload = bytes(encoded)
    if len(payload) < _V2_HEADER_SIZE:
        raise ValueError("Native Aurora chat is too short")
    magic, version = struct.unpack(">2sB", payload[:3])
    if magic != CHAT_MAGIC or version not in {2, CHAT_VERSION}:
        raise ValueError("Native Aurora chat identity is invalid")
    if version == 2:
        _, _, frame_id, source_size, target_size, text_size = struct.unpack(
            _V2_HEADER_FORMAT, payload[:_V2_HEADER_SIZE]
        )
        name_size = flags = contact_id = reply_frequency_hz = reply_window = 0
        offset = _V2_HEADER_SIZE
    else:
        (
            _, _, frame_id, source_size, target_size, name_size, text_size,
            flags, contact_id, reply_frequency_hz, reply_window,
        ) = struct.unpack(_HEADER_FORMAT, payload[:_HEADER_SIZE])
        if flags & ~(CHAT_FLAG_REPLY_TO | CHAT_FLAG_BTY | CHAT_FLAG_EOC):
            raise ValueError("Native Aurora chat control flags are invalid")
        if name_size > 80 or (flags and contact_id == 0):
            raise ValueError("Native Aurora chat contact metadata is invalid")
        if bool(flags & CHAT_FLAG_REPLY_TO) != bool(reply_frequency_hz):
            raise ValueError("Native Aurora chat Reply-To metadata is invalid")
        offset = _HEADER_SIZE
    expected = offset + source_size + target_size + name_size + text_size
    if len(payload) != expected or text_size > CHAT_TEXT_BYTES:
        raise ValueError("Native Aurora chat length is invalid")
    try:
        source = payload[offset : offset + source_size].decode("ascii")
        offset += source_size
        target = payload[offset : offset + target_size].decode("ascii")
        offset += target_size
        name = payload[offset : offset + name_size].decode("utf-8")
        offset += name_size
        text = payload[offset:].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Native Aurora chat encoding is invalid") from error
    source = str(Ax25Address.parse(source))
    target = str(Ax25Address.parse(target))
    if not text and not flags & CHAT_FLAG_EOC:
        raise ValueError("Native Aurora chat message is empty")
    reply = reply_frequency_hz if flags & CHAT_FLAG_REPLY_TO else None
    return ChatMessage(
        source, text, target, frame_id, name, contact_id, reply, reply_window,
        bool(flags & CHAT_FLAG_BTY), bool(flags & CHAT_FLAG_EOC),
    )


def encode_chat_transmission(
    callsign: str,
    text: str,
    *,
    destination: str = "AURORA",
    frame_id: int = 0,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
    **contact_metadata,
) -> EncodedTransmission:
    """Protect native variable-length chat with Aurora framing and FEC."""
    payload = build_native_chat(
        callsign, text, destination=destination, frame_id=frame_id,
        **contact_metadata,
    )
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
    **contact_metadata,
) -> AirTransmission:
    """Build native chat plus its protected variable-length bootstrap."""
    identifier = secrets.randbits(32) if frame_id is None else frame_id
    native = build_native_chat(
        callsign, text, destination=destination, frame_id=identifier,
        **contact_metadata,
    )
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
