"""Minimal AX.25 version 2.2 UI-frame transport for Aurora."""

from __future__ import annotations

from dataclasses import dataclass
import re


AX25_UI_CONTROL = 0x03
AX25_NO_LAYER3_PID = 0xF0
AX25_MAX_INFORMATION = 256
_CALLSIGN_PATTERN = re.compile(r"^[A-Z0-9]{1,6}$")


class Ax25Error(ValueError):
    """Raised when an AX.25 frame or address is invalid."""


@dataclass(frozen=True, slots=True)
class Ax25Address:
    """One AX.25 callsign and secondary-station identifier."""

    callsign: str
    ssid: int = 0

    def __post_init__(self) -> None:
        normalized = self.callsign.strip().upper()
        if not _CALLSIGN_PATTERN.fullmatch(normalized):
            raise Ax25Error("AX.25 callsign must contain 1-6 ASCII letters or digits")
        if not 0 <= self.ssid <= 15:
            raise Ax25Error("AX.25 SSID must be between 0 and 15")
        object.__setattr__(self, "callsign", normalized)

    @classmethod
    def parse(cls, value: str) -> Ax25Address:
        """Parse `CALL` or `CALL-SSID` operator notation."""
        text = value.strip().upper()
        if "-" not in text:
            return cls(text)
        callsign, ssid_text = text.rsplit("-", 1)
        try:
            ssid = int(ssid_text)
        except ValueError as error:
            raise Ax25Error("AX.25 SSID must be numeric") from error
        return cls(callsign, ssid)

    def __str__(self) -> str:
        return self.callsign if self.ssid == 0 else f"{self.callsign}-{self.ssid}"


@dataclass(frozen=True, slots=True)
class Ax25UiFrame:
    """An unnumbered-information AX.25 frame without HDLC flags."""

    destination: Ax25Address
    source: Ax25Address
    information: bytes
    repeaters: tuple[Ax25Address, ...] = ()
    pid: int = AX25_NO_LAYER3_PID

    def __post_init__(self) -> None:
        information = bytes(self.information)
        if len(information) > AX25_MAX_INFORMATION:
            raise Ax25Error("AX.25 information exceeds 256 bytes")
        if len(self.repeaters) > 8:
            raise Ax25Error("AX.25 supports at most eight repeater addresses")
        if not 0 <= self.pid <= 0xFF:
            raise Ax25Error("AX.25 PID must fit in one byte")
        object.__setattr__(self, "information", information)
        object.__setattr__(self, "repeaters", tuple(self.repeaters))


def crc16_x25(data: bytes) -> int:
    """Return the reflected CRC-16/X-25 used for the AX.25 FCS."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc ^ 0xFFFF


def _encode_address(address: Ax25Address, *, final: bool) -> bytes:
    callsign = address.callsign.ljust(6)
    encoded = bytearray(ord(character) << 1 for character in callsign)
    encoded.append(0x60 | (address.ssid << 1) | int(final))
    return bytes(encoded)


def _decode_address(encoded: bytes) -> tuple[Ax25Address, bool]:
    if len(encoded) != 7 or any(byte & 1 for byte in encoded[:6]):
        raise Ax25Error("AX.25 address field is malformed")
    callsign = "".join(chr(byte >> 1) for byte in encoded[:6]).rstrip()
    ssid = (encoded[6] >> 1) & 0x0F
    return Ax25Address(callsign, ssid), bool(encoded[6] & 0x01)


def encode_ui_frame(frame: Ax25UiFrame) -> bytes:
    """Serialize one AX.25 UI frame including its little-endian FCS."""
    addresses = (frame.destination, frame.source, *frame.repeaters)
    body = bytearray()
    for index, address in enumerate(addresses):
        body.extend(_encode_address(address, final=index == len(addresses) - 1))
    body.extend((AX25_UI_CONTROL, frame.pid))
    body.extend(frame.information)
    fcs = crc16_x25(body)
    body.extend((fcs & 0xFF, fcs >> 8))
    return bytes(body)


def decode_ui_frame(encoded: bytes) -> Ax25UiFrame:
    """Validate and parse one AX.25 UI frame including its FCS."""
    data = bytes(encoded)
    if len(data) < 18:
        raise Ax25Error("AX.25 UI frame is too short")
    received_fcs = data[-2] | (data[-1] << 8)
    body = data[:-2]
    if crc16_x25(body) != received_fcs:
        raise Ax25Error("AX.25 FCS validation failed")

    addresses: list[Ax25Address] = []
    offset = 0
    while True:
        if offset + 7 > len(body):
            raise Ax25Error("AX.25 address list is incomplete")
        address, final = _decode_address(body[offset : offset + 7])
        addresses.append(address)
        offset += 7
        if final:
            break
        if len(addresses) > 10:
            raise Ax25Error("AX.25 address list is too long")
    if len(addresses) < 2:
        raise Ax25Error("AX.25 frame requires destination and source addresses")
    if offset + 2 > len(body):
        raise Ax25Error("AX.25 control or PID field is missing")
    if body[offset] != AX25_UI_CONTROL:
        raise Ax25Error("Aurora AX.25 transport accepts UI frames only")
    pid = body[offset + 1]
    return Ax25UiFrame(
        addresses[0],
        addresses[1],
        body[offset + 2 :],
        tuple(addresses[2:]),
        pid,
    )
