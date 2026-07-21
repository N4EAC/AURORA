"""Thread-safe serial transport for Aurora radio control."""

import threading
from typing import Any, Callable

import serial


SerialFactory = Callable[..., Any]


class RadioConnectionError(RuntimeError):
    """Raised when a radio transport operation cannot be completed."""


class SerialTransport:
    """ASCII command transport over a serial radio connection."""

    def __init__(
        self,
        port: str,
        *,
        baud_rate: int = 9_600,
        timeout: float = 0.5,
        serial_factory: SerialFactory = serial.Serial,
    ) -> None:
        if not port:
            raise ValueError("A serial port is required")
        self._lock = threading.Lock()
        self._serial = serial_factory(
            port=port,
            baudrate=baud_rate,
            timeout=timeout,
            write_timeout=timeout,
        )

    @property
    def is_open(self) -> bool:
        """Return whether the serial connection is open."""
        return bool(self._serial.is_open)

    def send(self, command: str) -> None:
        """Send a CAT command without waiting for a response."""
        with self._lock:
            self._write(command)

    def query(self, command: str) -> str:
        """Send a CAT command and return its semicolon-terminated response."""
        with self._lock:
            self._write(command)
            response = self._serial.read_until(b";")
        if not response.endswith(b";"):
            raise RadioConnectionError("Radio response timed out")
        try:
            return response.decode("ascii")
        except UnicodeDecodeError as error:
            raise RadioConnectionError("Radio returned non-ASCII data") from error

    def set_rts(self, active: bool) -> None:
        """Set the serial RTS control line."""
        self._serial.rts = active

    def set_dtr(self, active: bool) -> None:
        """Set the serial DTR control line."""
        self._serial.dtr = active

    def close(self) -> None:
        """Close the serial radio connection."""
        self._serial.close()

    def _write(self, command: str) -> None:
        if not self.is_open:
            raise RadioConnectionError("Radio serial connection is closed")
        if not command.endswith(";"):
            raise ValueError("CAT commands must end with a semicolon")
        try:
            self._serial.write(command.encode("ascii"))
            self._serial.flush()
        except (serial.SerialException, serial.SerialTimeoutException) as error:
            raise RadioConnectionError("Radio serial write failed") from error

    def __enter__(self) -> "SerialTransport":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
