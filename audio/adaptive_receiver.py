"""Coordinate simultaneous receive decoding for every Aurora bandwidth."""

from __future__ import annotations

from collections.abc import Callable

from audio.buffer import AudioBuffer
from audio.multichannel_receiver import (
    MultichannelAudioReceiver,
    MultichannelDecodeEvent,
)
from modem.mode_definition import AURORA_BANDWIDTH_MODES, ModeDefinition


ReceiverFactory = Callable[
    [tuple[int, ...], ModeDefinition], MultichannelAudioReceiver
]


class AdaptiveBandwidthAudioReceiver:
    """Decode all published occupied-bandwidth profiles from one audio stream."""

    def __init__(
        self,
        frequencies_hz: tuple[int, ...],
        *,
        receiver_factory: ReceiverFactory = MultichannelAudioReceiver,
    ) -> None:
        self._receivers = tuple(
            receiver_factory(frequencies_hz, mode)
            for mode in AURORA_BANDWIDTH_MODES.values()
        )

    def feed(
        self,
        audio: AudioBuffer,
        *,
        discontinuity: bool = False,
    ) -> tuple[MultichannelDecodeEvent, ...]:
        """Return unique CRC-valid events decoded by any bandwidth profile."""
        decoded: dict[tuple[str, int, int], MultichannelDecodeEvent] = {}
        for receiver in self._receivers:
            for event in receiver.feed(audio, discontinuity=discontinuity):
                if event.message is not None:
                    source = event.message.callsign
                elif event.station is not None:
                    source = event.station.data.callsign
                else:
                    assert event.report is not None
                    source = event.report.reporter
                decoded[(source, event.frame_id, event.frequency_hz)] = event
        return tuple(decoded.values())
