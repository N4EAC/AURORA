"""Failure-safe fake-split frequency switching through Hamlib."""

from __future__ import annotations

from collections.abc import Callable
import time

from radio.hamlib_control import HamlibController


class FakeSplitController:
    """Switch one-VFO radios between contact TX and RX dial frequencies."""

    def __init__(
        self,
        controller: HamlibController,
        *,
        settle_seconds: float = 0.15,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.controller = controller
        self.settle_seconds = max(0.0, settle_seconds)
        self._sleep = sleep

    def tune_verified(self, frequency_hz: int) -> None:
        """Tune with PTT off and require CAT readback before continuing."""
        self.controller.set_ptt(False)
        self.controller.set_frequency(frequency_hz)
        if self.controller.get_frequency() != frequency_hz:
            raise RuntimeError("Radio frequency readback did not match requested split frequency")
        self._sleep(self.settle_seconds)

    def prepare_transmit(self, transmit_frequency_hz: int) -> None:
        self.tune_verified(transmit_frequency_hz)

    def finish_transmit(self, receive_frequency_hz: int) -> None:
        self.controller.set_ptt(False)
        self.tune_verified(receive_frequency_hz)

    def restore(self, normal_frequency_hz: int) -> None:
        self.controller.set_ptt(False)
        self.tune_verified(normal_frequency_hz)
