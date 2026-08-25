"""Parallel fixed-geometry Aurora receivers across the audio spectrum."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from audio.buffer import AudioBuffer
from audio.continuous_receiver import ContinuousAudioReceiver, ContinuousReceiverConfig
from modem.chat_transport import ChatMessage, encode_chat_transmission, parse_chat_ax25
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


MIN_AUDIO_FREQUENCY_HZ = 100
MAX_AUDIO_FREQUENCY_HZ = 3_000


@dataclass(frozen=True, slots=True)
class MultichannelDecodeEvent:
    """One CRC-confirmed chat message and its audio center frequency."""

    frequency_hz: int
    message: ChatMessage
    sync_metric: float
    frequency_offset_hz: float


def mode_at_frequency(mode: ModeDefinition, frequency_hz: int) -> ModeDefinition:
    """Return a mode tuned to an operator-selected audio center frequency."""
    frequency = int(frequency_hz)
    if not MIN_AUDIO_FREQUENCY_HZ <= frequency <= MAX_AUDIO_FREQUENCY_HZ:
        raise ValueError("Audio frequency must be between 100 and 3000 Hz")
    return replace(mode, audio_carrier_hz=float(frequency))


def chat_payload_symbol_count(mode: ModeDefinition = AURORA_ROBUST_MODE) -> int:
    """Return the fixed encoded symbol count shared by all chat messages."""
    return len(encode_chat_transmission("AURORA", "x", mode=mode).symbols)


class MultichannelAudioReceiver:
    """Detect occupied regions, then run bounded frequency-tuned decoders."""

    def __init__(
        self,
        frequencies_hz: tuple[int, ...],
        mode: ModeDefinition = AURORA_ROBUST_MODE,
    ) -> None:
        frequencies = tuple(dict.fromkeys(int(value) for value in frequencies_hz))
        if not frequencies:
            raise ValueError("At least one receive frequency is required")
        self._frequencies = frequencies
        self._mode = mode
        self._symbol_count = chat_payload_symbol_count(mode)
        reference = ContinuousReceiverConfig(self._symbol_count, mode=mode)
        self._frame_samples = reference.frame_sample_count
        self._maximum_samples = reference.maximum_buffer_samples
        self._retry_samples = mode.audio_sample_rate
        self._samples = np.empty(0, dtype=np.float32)
        self._samples_since_attempt = self._retry_samples

    def _spectral_candidates(self) -> tuple[int, ...]:
        """Locate a few likely channel centers with one shared FFT analysis."""
        fft_size = 4_096
        recent = self._samples[-min(len(self._samples), self._mode.audio_sample_rate * 2) :]
        if len(recent) < fft_size:
            return ()
        powers = []
        window = np.hanning(fft_size)
        for offset in range(0, len(recent) - fft_size + 1, fft_size // 2):
            spectrum = np.fft.rfft(recent[offset : offset + fft_size] * window)
            powers.append(np.abs(spectrum) ** 2)
        mean_power = np.mean(powers, axis=0)
        bins = np.fft.rfftfreq(fft_size, 1.0 / self._mode.audio_sample_rate)
        half_width = max(250.0, self._mode.occupied_bandwidth_hz / 2.0)
        scores = np.asarray(
            [
                float(
                    np.sum(
                        mean_power[
                            (bins >= frequency - half_width)
                            & (bins <= frequency + half_width)
                        ]
                    )
                )
                for frequency in self._frequencies
            ]
        )
        if len(self._frequencies) <= 4:
            return self._frequencies
        baseline = float(np.median(scores))
        if float(np.max(scores)) < max(baseline * 2.0, np.finfo(float).tiny):
            return ()
        peaks = [
            index
            for index in range(len(scores))
            if (index == 0 or scores[index] >= scores[index - 1])
            and (index == len(scores) - 1 or scores[index] >= scores[index + 1])
        ]
        peaks.sort(key=lambda index: scores[index], reverse=True)
        candidates: list[int] = []
        allowed = set(self._frequencies)
        for index in peaks[:3]:
            center = self._frequencies[index]
            for frequency in (center, center - 100, center + 100):
                if frequency in allowed and frequency not in candidates:
                    candidates.append(frequency)
        return tuple(candidates)

    def feed(
        self,
        audio: AudioBuffer,
        *,
        discontinuity: bool = False,
    ) -> tuple[MultichannelDecodeEvent, ...]:
        """Return all CRC-valid chat messages recovered from this audio block."""
        if audio.sample_rate != self._mode.audio_sample_rate:
            raise ValueError("Multichannel audio sample rate does not match the mode")
        if audio.channel_count != 1:
            raise ValueError("Multichannel receiver requires mono audio")
        if discontinuity:
            self._samples = np.empty(0, dtype=np.float32)
            self._samples_since_attempt = self._retry_samples
        incoming = np.asarray(audio.samples, dtype=np.float32).reshape(-1)
        self._samples = np.concatenate((self._samples, incoming))
        self._samples_since_attempt += len(incoming)
        if len(self._samples) < self._frame_samples:
            return ()
        if self._samples_since_attempt < self._retry_samples:
            return ()
        self._samples_since_attempt = 0
        decoded: dict[tuple[str, str], MultichannelDecodeEvent] = {}
        capture = AudioBuffer(self._samples, audio.sample_rate)
        for frequency in self._spectral_candidates():
            receiver = ContinuousAudioReceiver(
                ContinuousReceiverConfig(
                    self._symbol_count,
                    mode=mode_at_frequency(self._mode, frequency),
                )
            )
            for event in receiver.feed(capture):
                try:
                    message = parse_chat_ax25(event.payload)
                except ValueError:
                    continue
                candidate = MultichannelDecodeEvent(
                    frequency,
                    message,
                    event.diagnostics.sync_metric,
                    event.diagnostics.frequency_offset_hz,
                )
                key = (message.callsign, message.text)
                current = decoded.get(key)
                if current is None or abs(candidate.frequency_offset_hz) < abs(
                    current.frequency_offset_hz
                ):
                    decoded[key] = candidate
        if decoded:
            self._samples = np.empty(0, dtype=np.float32)
        elif len(self._samples) > self._maximum_samples:
            self._samples = self._samples[-self._maximum_samples :]
        return tuple(decoded.values())
