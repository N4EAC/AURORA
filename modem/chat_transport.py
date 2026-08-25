"""Fixed-geometry AX.25 chat messages carried by Aurora frames."""

from __future__ import annotations

from dataclasses import dataclass

from dsp.core import EncodedTransmission, encode_payload
from dsp.framing import Frame
from modem.ax25 import Ax25Address, Ax25Error, Ax25UiFrame, decode_ui_frame, encode_ui_frame
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


AURORA_FLAG_CHAT = 0x02
CHAT_MAGIC = b"AC"
CHAT_VERSION = 1
CHAT_TEXT_BYTES = 120


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One decoded chat message with AX.25 station identity."""

    callsign: str
    text: str


def build_chat_ax25(callsign: str, text: str, destination: str = "AURORA") -> bytes:
    """Build a fixed-size AX.25 UI frame for spectrum-wide decoding."""
    message = text.strip()
    encoded = message.encode("utf-8")
    if not encoded:
        raise ValueError("Enter a chat message")
    if len(encoded) > CHAT_TEXT_BYTES:
        raise ValueError(f"Chat message must not exceed {CHAT_TEXT_BYTES} UTF-8 bytes")
    information = (
        CHAT_MAGIC
        + bytes((CHAT_VERSION, len(encoded)))
        + encoded.ljust(CHAT_TEXT_BYTES, b"\x00")
    )
    return encode_ui_frame(
        Ax25UiFrame(
            Ax25Address.parse(destination),
            Ax25Address.parse(callsign),
            information,
        )
    )


def parse_chat_ax25(encoded: bytes) -> ChatMessage:
    """Validate and decode one fixed-geometry AX.25 chat frame."""
    frame = decode_ui_frame(encoded)
    information = frame.information
    expected = 4 + CHAT_TEXT_BYTES
    if len(information) != expected or information[:2] != CHAT_MAGIC:
        raise Ax25Error("AX.25 payload is not an Aurora chat message")
    if information[2] != CHAT_VERSION:
        raise Ax25Error(f"Unsupported Aurora chat version: {information[2]}")
    length = information[3]
    if length > CHAT_TEXT_BYTES or any(information[4 + length :]):
        raise Ax25Error("Aurora chat padding is invalid")
    try:
        text = information[4 : 4 + length].decode("utf-8")
    except UnicodeDecodeError as error:
        raise Ax25Error("Aurora chat text is not valid UTF-8") from error
    return ChatMessage(str(frame.source), text)


def encode_chat_transmission(
    callsign: str,
    text: str,
    *,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> EncodedTransmission:
    """Protect a fixed-geometry AX.25 chat frame with the selected mode."""
    return encode_payload(
        build_chat_ax25(callsign, text),
        flags=AURORA_FLAG_CHAT,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )


def decode_chat_transport(frame: Frame) -> ChatMessage:
    """Decode an Aurora frame only when it contains AX.25 chat traffic."""
    if frame.flags != AURORA_FLAG_CHAT:
        raise Ax25Error("Aurora frame does not contain AX.25 chat traffic")
    return parse_chat_ax25(frame.payload)
