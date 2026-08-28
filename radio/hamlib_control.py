"""Thread-safe Hamlib rigctld control for Aurora."""

from __future__ import annotations

import socket
import threading
from typing import Callable


DEFAULT_RADIO_PASSBAND_HZ = 3_000


class HamlibError(RuntimeError):
    """Raised when rigctld rejects a command or returns invalid data."""


class HamlibController:
    """Minimal persistent client for Hamlib's stable rigctld protocol."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4_532,
        *,
        timeout: float = 1.0,
        connection_factory: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        if not host.strip():
            raise ValueError("Hamlib host is required")
        if not 1 <= port <= 65_535:
            raise ValueError("Hamlib port must be between 1 and 65535")
        self._lock = threading.Lock()
        self._socket = connection_factory((host.strip(), port), timeout=timeout)
        self._stream = self._socket.makefile("rwb", buffering=0)

    def _write(self, command: str) -> None:
        self._stream.write((command.rstrip("\n") + "\n").encode("ascii"))

    def _read_line(self) -> str:
        response = self._stream.readline()
        if not response:
            raise HamlibError("Hamlib connection closed")
        try:
            text = response.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise HamlibError("Hamlib returned non-ASCII data") from error
        if text.startswith("RPRT ") and text != "RPRT 0":
            raise HamlibError(f"Hamlib command failed: {text}")
        return text

    def _set(self, command: str) -> None:
        with self._lock:
            self._write(command)
            response = self._read_line()
        if response != "RPRT 0":
            raise HamlibError(f"Unexpected Hamlib response: {response}")

    def get_frequency(self) -> int:
        """Return the current VFO frequency in hertz."""
        with self._lock:
            self._write("f")
            response = self._read_line()
        try:
            return int(round(float(response)))
        except ValueError as error:
            raise HamlibError("Hamlib frequency response is invalid") from error

    def set_frequency(self, frequency_hz: int) -> None:
        """Set the current VFO frequency in hertz."""
        if frequency_hz <= 0:
            raise ValueError("Radio frequency must be positive")
        self._set(f"F {int(frequency_hz)}")

    def get_mode(self) -> tuple[str, int]:
        """Return Hamlib mode name and passband width."""
        with self._lock:
            self._write("m")
            mode = self._read_line()
            passband = self._read_line()
        try:
            return mode, int(passband)
        except ValueError as error:
            raise HamlibError("Hamlib mode response is invalid") from error

    def set_mode(self, mode: str, passband_hz: int) -> None:
        """Set the radio mode and receive passband."""
        normalized = mode.strip().upper()
        if not normalized or passband_hz <= 0:
            raise ValueError("Hamlib mode and passband must be valid")
        self._set(f"M {normalized} {int(passband_hz)}")

    def get_ptt(self) -> bool:
        """Return whether Hamlib reports transmit PTT active."""
        with self._lock:
            self._write("t")
            response = self._read_line()
        if response not in {"0", "1"}:
            raise HamlibError("Hamlib PTT response is invalid")
        return response == "1"

    def set_ptt(self, active: bool) -> None:
        """Set PTT only after an explicit caller action."""
        self._set(f"T {int(bool(active))}")

    def close(self) -> None:
        """Close the rigctld connection."""
        self._stream.close()
        self._socket.close()

    def __enter__(self) -> "HamlibController":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
