"""Bounded continuous audio reception for fixed Aurora test-frame geometry."""

from dataclasses import dataclass

import numpy as np

from audio.buffer import AudioBuffer
from dsp.core import decode_soft_symbols
from dsp.framing import FrameError
from dsp.preamble import PREAMBLE_SYMBOL_COUNT
from dsp.waveform import (
    WaveformDiagnostics,
    demodulate_audio,
    root_raised_cosine_taps,
    samples_per_symbol,
)
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


@dataclass(frozen=True, slots=True)
class ContinuousReceiverConfig:
    """Configure one bounded fixed-geometry streaming receiver."""

    payload_symbol_count: int
    mode: ModeDefinition = AURORA_ROBUST_MODE
    search_margin_seconds: float = 2.0
    retry_step_samples: int = 1_024
    phase_repair_step_symbols: int = 8

    def __post_init__(self) -> None:
        if self.payload_symbol_count <= 0:
            raise ValueError("Streaming payload symbol count must be positive")
        if self.search_margin_seconds <= 0.0:
            raise ValueError("Streaming search margin must be positive")
        if self.retry_step_samples <= 0:
            raise ValueError("Streaming retry step must be positive")
        if self.phase_repair_step_symbols <= 0:
            raise ValueError("Phase repair step must be positive")

    @property
    def frame_sample_count(self) -> int:
        """Return generated waveform samples without external leading silence."""
        if self.mode.waveform == "ofdm":
            from dsp.ofdm import config_for_mode, frame_sample_count

            return frame_sample_count(
                self.payload_symbol_count,
                config_for_mode(self.mode),
            )
        ratio = samples_per_symbol(self.mode)
        taps = root_raised_cosine_taps(
            ratio,
            self.mode.pulse_rolloff,
            self.mode.pulse_span_symbols,
        )
        return (
            (PREAMBLE_SYMBOL_COUNT + self.payload_symbol_count) * ratio
            + len(taps)
            - 1
        )

    @property
    def maximum_buffer_samples(self) -> int:
        """Return the bounded frame plus unknown-start search window."""
        return self.frame_sample_count + round(
            self.search_margin_seconds * self.mode.audio_sample_rate
        )

    @property
    def matched_filter_delay_samples(self) -> int:
        """Return the combined transmit/receive pulse-filter timing offset."""
        if self.mode.waveform == "ofdm":
            return 0
        ratio = samples_per_symbol(self.mode)
        taps = root_raised_cosine_taps(
            ratio,
            self.mode.pulse_rolloff,
            self.mode.pulse_span_symbols,
        )
        return len(taps) - 1


@dataclass(frozen=True, slots=True)
class ContinuousDecodeEvent:
    """One CRC-confirmed message recovered from the rolling audio buffer."""

    payload: bytes
    diagnostics: WaveformDiagnostics
    buffered_samples: int
    recovery: str | None = None
    repair_symbol: int | None = None


@dataclass(frozen=True, slots=True)
class ContinuousReceiverDiagnostics:
    """Cumulative streaming state and recovery counters."""

    buffered_samples: int
    decoded_frames: int
    failed_windows: int
    discontinuities: int
    dropped_samples: int
    phase_repairs: int


class ContinuousAudioReceiver:
    """Accumulate arbitrary blocks and recover fixed-geometry Aurora frames."""

    def __init__(self, config: ContinuousReceiverConfig) -> None:
        self.config = config
        self._samples = np.empty(0, dtype=np.float32)
        self._decoded_frames = 0
        self._failed_windows = 0
        self._discontinuities = 0
        self._dropped_samples = 0
        self._phase_repairs = 0

    @property
    def diagnostics(self) -> ContinuousReceiverDiagnostics:
        """Return a coherent snapshot of current streaming state."""
        return ContinuousReceiverDiagnostics(
            len(self._samples),
            self._decoded_frames,
            self._failed_windows,
            self._discontinuities,
            self._dropped_samples,
            self._phase_repairs,
        )

    def reset(self) -> None:
        """Discard buffered samples while retaining cumulative counters."""
        self._dropped_samples += len(self._samples)
        self._samples = np.empty(0, dtype=np.float32)

    def mark_discontinuity(self) -> None:
        """Discard partial state after an audio-stream continuity failure."""
        self._discontinuities += 1
        self.reset()

    def _decode_with_phase_repair(
        self,
        symbols: np.ndarray,
    ) -> tuple[bytes, int]:
        """CRC-decode one bounded mid-frame BPSK phase-inversion hypothesis."""
        step = self.config.phase_repair_step_symbols
        for cut in range(step, len(symbols), step):
            repaired = np.concatenate((symbols[:cut], -symbols[cut:]))
            try:
                frame = decode_soft_symbols(
                    tuple(repaired),
                    self.config.mode.modulation,
                    interleaver_columns=self.config.mode.interleaver_columns,
                )
            except (FrameError, ValueError):
                continue
            return frame.payload, cut
        raise FrameError("No CRC-valid bounded phase repair was found")

    def feed(
        self,
        audio: AudioBuffer,
        *,
        discontinuity: bool = False,
    ) -> tuple[ContinuousDecodeEvent, ...]:
        """Consume one block and return any CRC-confirmed fixed test frame."""
        if audio.sample_rate != self.config.mode.audio_sample_rate:
            raise ValueError("Streaming audio sample rate does not match the mode")
        if audio.channel_count != 1:
            raise ValueError("Streaming receiver requires mono audio")
        if discontinuity:
            self.mark_discontinuity()
        incoming = np.asarray(audio.samples, dtype=np.float32).reshape(-1)
        self._samples = np.concatenate((self._samples, incoming))
        events: list[ContinuousDecodeEvent] = []
        while len(self._samples) >= self.config.frame_sample_count:
            capture = AudioBuffer(self._samples, audio.sample_rate)
            try:
                recovered = demodulate_audio(
                    capture,
                    self.config.payload_symbol_count,
                    self.config.mode,
                )
            except ValueError:
                recovered = None
            recovery = None
            repair_symbol = None
            try:
                if recovered is None:
                    raise FrameError("Waveform acquisition failed")
                frame = decode_soft_symbols(
                    tuple(recovered.symbols),
                    self.config.mode.modulation,
                    interleaver_columns=self.config.mode.interleaver_columns,
                )
                payload = frame.payload
            except (FrameError, ValueError):
                if recovered is None:
                    payload = None
                else:
                    try:
                        payload, repair_symbol = self._decode_with_phase_repair(
                            recovered.symbols
                        )
                    except FrameError:
                        payload = None
                    else:
                        recovery = "phase_inversion"
                        self._phase_repairs += 1
            if payload is None:
                if len(self._samples) < self.config.maximum_buffer_samples:
                    return tuple(events)
                drop = min(self.config.retry_step_samples, len(self._samples))
                self._samples = self._samples[drop:]
                self._dropped_samples += drop
                self._failed_windows += 1
                continue

            event = ContinuousDecodeEvent(
                payload,
                recovered.diagnostics,
                len(self._samples),
                recovery,
                repair_symbol,
            )
            self._decoded_frames += 1
            events.append(event)
            # Acquisition reports the matched-filter sample location. Remove
            # both pulse-filter delays to locate the frame in captured audio.
            frame_start = max(
                0,
                recovered.diagnostics.symbol_start_sample
                - self.config.matched_filter_delay_samples,
            )
            consumed = min(
                len(self._samples),
                frame_start + self.config.frame_sample_count,
            )
            self._samples = self._samples[consumed:]
        return tuple(events)
