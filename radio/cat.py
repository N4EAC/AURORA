"""CAT command control for Aurora radios."""

from typing import Protocol


class CommandTransport(Protocol):
    """Transport operations required by the CAT controller."""

    def send(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...


MODE_TO_CODE = {
    "LSB": "1",
    "USB": "2",
    "CW": "3",
    "FM": "4",
    "AM": "5",
    "FSK": "6",
    "CW-R": "7",
    "FSK-R": "9",
}
CODE_TO_MODE = {code: mode for mode, code in MODE_TO_CODE.items()}


class CatProtocolError(RuntimeError):
    """Raised when a CAT response is malformed or unsupported."""


class CatController:
    """Kenwood-style ASCII CAT controller."""

    def __init__(self, transport: CommandTransport) -> None:
        self._transport = transport

    def set_frequency(self, frequency_hz: int) -> None:
        """Set VFO A frequency in hertz."""
        if not 0 < frequency_hz <= 99_999_999_999:
            raise ValueError("CAT frequency is outside the supported range")
        self._transport.send(f"FA{frequency_hz:011d};")

    def get_frequency(self) -> int:
        """Read VFO A frequency in hertz."""
        response = self._transport.query("FA;")
        if not response.startswith("FA") or not response.endswith(";"):
            raise CatProtocolError("Invalid CAT frequency response")
        value = response[2:-1]
        if not value.isdigit():
            raise CatProtocolError("CAT frequency response is not numeric")
        return int(value)

    def set_mode(self, mode: str) -> None:
        """Set the operating mode."""
        normalized = mode.upper()
        try:
            code = MODE_TO_CODE[normalized]
        except KeyError as error:
            raise ValueError(f"Unsupported CAT mode: {mode}") from error
        self._transport.send(f"MD{code};")

    def get_mode(self) -> str:
        """Read the operating mode."""
        response = self._transport.query("MD;")
        if len(response) != 4 or not response.startswith("MD") or response[-1] != ";":
            raise CatProtocolError("Invalid CAT mode response")
        try:
            return CODE_TO_MODE[response[2]]
        except KeyError as error:
            raise CatProtocolError("Radio returned an unsupported CAT mode") from error

    def set_ptt(self, active: bool) -> None:
        """Enable or disable transmitter PTT through CAT."""
        self._transport.send("TX;" if active else "RX;")
