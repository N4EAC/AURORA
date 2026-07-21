"""Fail-safe push-to-talk control for Aurora."""

from contextlib import contextmanager
from enum import Enum
import threading
from typing import Iterator, Protocol

from radio.cat import CatController


class ControlLineTransport(Protocol):
    """Serial control-line operations available to PTT."""

    def set_rts(self, active: bool) -> None: ...

    def set_dtr(self, active: bool) -> None: ...


class PttMethod(str, Enum):
    """Supported radio keying methods."""

    CAT = "cat"
    RTS = "rts"
    DTR = "dtr"


class PttController:
    """Explicit, thread-safe PTT control with automatic release support."""

    def __init__(
        self,
        method: PttMethod,
        *,
        cat: CatController | None = None,
        transport: ControlLineTransport | None = None,
    ) -> None:
        if method is PttMethod.CAT and cat is None:
            raise ValueError("CAT PTT requires a CAT controller")
        if method in (PttMethod.RTS, PttMethod.DTR) and transport is None:
            raise ValueError("Control-line PTT requires a serial transport")
        self._method = method
        self._cat = cat
        self._transport = transport
        self._active = False
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        """Return whether PTT was successfully activated."""
        return self._active

    def set_active(self, active: bool) -> None:
        """Set PTT state through the configured control method."""
        with self._lock:
            if active == self._active:
                return
            if self._method is PttMethod.CAT:
                assert self._cat is not None
                self._cat.set_ptt(active)
            elif self._method is PttMethod.RTS:
                assert self._transport is not None
                self._transport.set_rts(active)
            else:
                assert self._transport is not None
                self._transport.set_dtr(active)
            self._active = active

    @contextmanager
    def transmit(self) -> Iterator[None]:
        """Key the transmitter for the context and always release it afterward."""
        self.set_active(True)
        try:
            yield
        finally:
            self.set_active(False)

    def close(self) -> None:
        """Release PTT if it is currently active."""
        if self.active:
            self.set_active(False)
