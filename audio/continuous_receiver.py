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

    def __post_init__(self) -> None:
        if self.payload_symbol_count <= 0:
            raise ValueError("Streaming payload symbol count must be positive")
        if self.search_margin_seconds <= 0.0:
            raise ValueError("Streaming search margin must be positive")
        if self.retry_step_samples <= 0:
            raise ValueError("Streaming retry step must be positive")

    @property
    def frame_sample_count(self) -> int:
        """Return generated waveform samples without external leading silence."""
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


@dataclass(frozen=True, slots=True)
class ContinuousDecodeEvent:
    """One CRC-confirmed message recovered from the rolling audio buffer."""

    payload: bytes
    diagnostics: WaveformDiagnostics
    buffered_samples: int


@dataclass(frozen=True, slots=True)
class ContinuousReceiverDiagnostics:
    """Cumulative streaming state and recovery counters."""

    buffered_samples: int
    decoded_frames: int
    failed_windows: int
    discontinuities: int
    dropped_samples: int


class ContinuousAudioReceiver:
    """Accumulate arbitrary blocks and recover fixed-geometry Aurora frames."""

    def __init__(self, config: ContinuousReceiverConfig) -> None:
        self.config = config
        self._samples = np.empty(0, dtype=np.float32)
        self._decoded_frames = 0
        self._failed_windows = 0
        self._discontinuities = 0
        self._dropped_samples = 0

    @property
    def diagnostics(self) -> ContinuousReceiverDiagnostics:
        """Return a coherent snapshot of current streaming state."""
        return ContinuousReceiverDiagnostics(
            len(self._samples),
            self._decoded_frames,
            self._failed_windows,
            self._discontinuities,
            self._dropped_samples,
        )

    def reset(self) -> None:
        """Discard buffered samples while retaining cumulative counters."""
        self._dropped_samples += len(self._samples)
        self._samples = np.empty(0, dtype=np.float32)

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
            self._discontinuities += 1
            self.reset()
        incoming = np.asarray(audio.samples, dtype=np.float32).reshape(-1)
        self._samples = np.concatenate((self._samples, incoming))
        while len(self._samples) >= self.config.frame_sample_count:
            capture = AudioBuffer(self._samples, audio.sample_rate)
            try:
                recovered = demodulate_audio(
                    capture,
                    self.config.payload_symbol_count,
                    self.config.mode,
                )
                frame = decode_soft_symbols(
                    tuple(recovered.symbols),
                    self.config.mode.modulation,
                    interleaver_columns=self.config.mode.interleaver_columns,
                )
            except (FrameError, UnicodeDecodeError, ValueError):
                if len(self._samples) < self.config.maximum_buffer_samples:
                    return ()
                drop = min(self.config.retry_step_samples, len(self._samples))
                self._samples = self._samples[drop:]
                self._dropped_samples += drop
                self._failed_windows += 1
                continue

            event = ContinuousDecodeEvent(
                frame.payload,
                recovered.diagnostics,
                len(self._samples),
            )
            self._decoded_frames += 1
            self._samples = np.empty(0, dtype=np.float32)
            return (event,)
        return ()
