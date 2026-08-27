"""Parallel variable-length Aurora chat receivers across the audio spectrum."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from audio.buffer import AudioBuffer
from dsp.core import decode_soft_symbols
from dsp.ofdm import config_for_mode, frame_sample_count
from dsp.waveform import demodulate_audio, demodulate_audio_candidates
from modem.bootstrap import (
    FRAME_TYPE_AX25_STATION,
    FRAME_TYPE_CHAT,
    FRAME_TYPE_RECEPTION_REPORT,
    bootstrap_symbol_count,
    decode_bootstrap_frame,
)
from modem.chat_transport import (
    CHAT_TEXT_BYTES,
    ChatMessage,
    decode_chat_transport,
    encode_chat_air_transmission,
)
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition
from modem.reception_report import ReceptionReport, decode_reception_report
from modem.station_data import StationDataFrame, decode_station_transport


MIN_AUDIO_FREQUENCY_HZ = 100
MAX_AUDIO_FREQUENCY_HZ = 3_000


@dataclass(frozen=True, slots=True)
class MultichannelDecodeEvent:
    """One CRC-confirmed native chat message and its audio frequency."""

    frequency_hz: int
    message: ChatMessage | None
    station: StationDataFrame | None
    report: ReceptionReport | None
    frame_id: int
    sync_metric: float
    frequency_offset_hz: float
    timing_offset_samples: float
    equalized_symbols: tuple[complex, ...]
    subcarrier_quality: tuple[float, ...]
    snr_db: float


def audio_center_limits(mode: ModeDefinition) -> tuple[int, int]:
    """Return centers that keep the occupied profile inside 100–3000 Hz."""
    half_bandwidth = mode.occupied_bandwidth_hz / 2.0
    minimum = int(np.ceil(MIN_AUDIO_FREQUENCY_HZ + half_bandwidth))
    maximum = int(np.floor(MAX_AUDIO_FREQUENCY_HZ - half_bandwidth))
    if minimum > maximum:
        raise ValueError("Aurora bandwidth does not fit the radio audio passband")
    return minimum, maximum


def mode_at_frequency(mode: ModeDefinition, frequency_hz: int) -> ModeDefinition:
    """Return a mode tuned to an operator-selected audio center frequency."""
    frequency = int(frequency_hz)
    minimum, maximum = audio_center_limits(mode)
    if not minimum <= frequency <= maximum:
        raise ValueError(
            f"{mode.occupied_bandwidth_hz} Hz profile center must be between "
            f"{minimum} and {maximum} Hz"
        )
    return replace(mode, audio_carrier_hz=float(frequency))


def chat_payload_symbol_count(
    text: str = "x", mode: ModeDefinition = AURORA_ROBUST_MODE
) -> int:
    """Return the exact bootstrapped symbol count for one native message."""
    return len(
        encode_chat_air_transmission("AURORA", text, frame_id=0, mode=mode).symbols
    )


class MultichannelAudioReceiver:
    """Detect occupied regions and decode bootstrapped native chat frames."""

    def __init__(
        self,
        frequencies_hz: tuple[int, ...],
        mode: ModeDefinition = AURORA_ROBUST_MODE,
    ) -> None:
        frequencies = tuple(dict.fromkeys(int(value) for value in frequencies_hz))
        if not frequencies:
            raise ValueError("At least one receive frequency is required")
        minimum, maximum = audio_center_limits(mode)
        self._frequencies = tuple(
            value for value in frequencies if minimum <= value <= maximum
        )
        if not self._frequencies:
            raise ValueError("No receive centers fit the selected bandwidth")
        self._mode = mode
        self._bootstrap_symbols = bootstrap_symbol_count(mode)
        maximum_symbols = chat_payload_symbol_count("x" * CHAT_TEXT_BYTES, mode)
        config = config_for_mode(mode)
        self._minimum_samples = frame_sample_count(self._bootstrap_symbols, config)
        self._maximum_samples = (
            frame_sample_count(maximum_symbols, config) + mode.audio_sample_rate * 2
        )
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
                float(np.sum(mean_power[(bins >= f - half_width) & (bins <= f + half_width)]))
                for f in self._frequencies
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

    def _decode_frequency(
        self, capture: AudioBuffer, frequency_hz: int
    ) -> MultichannelDecodeEvent | None:
        mode = mode_at_frequency(self._mode, frequency_hz)
        samples = np.asarray(capture.samples, dtype=np.float64).reshape(-1)
        spectrum = np.fft.rfft(samples)
        bins = np.fft.rfftfreq(len(samples), 1.0 / capture.sample_rate)
        half_width = mode.occupied_bandwidth_hz / 2.0 + 100.0
        spectrum[(bins < frequency_hz - half_width) | (bins > frequency_hz + half_width)] = 0
        isolated = np.fft.irfft(spectrum, n=len(samples)).astype(np.float32)
        candidate_capture = AudioBuffer(isolated, capture.sample_rate)
        try:
            bootstrap_result = demodulate_audio(
                candidate_capture, self._bootstrap_symbols, mode
            )
            bootstrap_frame = decode_soft_symbols(
                tuple(bootstrap_result.symbols),
                mode.modulation,
                interleaver_columns=mode.interleaver_columns,
            )
            header = decode_bootstrap_frame(bootstrap_frame)
        except ValueError:
            return None
        if (
            header.frame_type not in {
                FRAME_TYPE_CHAT,
                FRAME_TYPE_AX25_STATION,
                FRAME_TYPE_RECEPTION_REPORT,
            }
            or header.bandwidth_hz != mode.occupied_bandwidth_hz
            or header.interleaver_columns != mode.interleaver_columns
            or header.payload_symbol_count != header.payload_size * 16 + 12
        ):
            return None
        total_symbols = self._bootstrap_symbols + header.payload_symbol_count
        try:
            candidates = demodulate_audio_candidates(
                candidate_capture, total_symbols, mode
            )
        except ValueError:
            return None
        for recovered in candidates:
            try:
                frame = decode_soft_symbols(
                    tuple(recovered.symbols[self._bootstrap_symbols :]),
                    mode.modulation,
                    interleaver_columns=mode.interleaver_columns,
                )
                message = None
                station = None
                report = None
                if header.frame_type == FRAME_TYPE_CHAT:
                    message = decode_chat_transport(frame)
                    if message.frame_id != header.frame_id:
                        continue
                elif header.frame_type == FRAME_TYPE_AX25_STATION:
                    station = decode_station_transport(frame)
                else:
                    report = decode_reception_report(frame)
            except ValueError:
                continue
            symbols = np.asarray(recovered.symbols, dtype=np.complex128)
            decisions = np.where(symbols.real >= 0.0, 1.0, -1.0)
            gain = np.vdot(decisions, symbols) / max(len(symbols), 1)
            residual = symbols - gain * decisions
            signal_power = float(abs(gain) ** 2)
            noise_power = float(np.mean(np.abs(residual) ** 2))
            snr_db = (
                float("inf")
                if noise_power <= 0.0
                else 10.0 * np.log10(max(signal_power, 1e-15) / noise_power)
            )
            carrier_count = len(config_for_mode(mode).data_subcarriers)
            quality = []
            normalized = symbols / gain if abs(gain) > 1e-12 else symbols
            errors = np.minimum(abs(normalized - 1.0), abs(normalized + 1.0))
            for index in range(carrier_count):
                carrier_errors = errors[index::carrier_count]
                mean_error = float(np.mean(carrier_errors)) if len(carrier_errors) else 1.0
                quality.append(1.0 / (1.0 + mean_error))
            return MultichannelDecodeEvent(
                frequency_hz,
                message,
                station,
                report,
                header.frame_id,
                recovered.diagnostics.sync_metric,
                recovered.diagnostics.frequency_offset_hz,
                recovered.diagnostics.timing_offset_samples,
                tuple(complex(value) for value in symbols),
                tuple(quality),
                float(snr_db),
            )
        return None

    def feed(
        self,
        audio: AudioBuffer,
        *,
        discontinuity: bool = False,
    ) -> tuple[MultichannelDecodeEvent, ...]:
        """Return all CRC-valid native chat messages recovered from a block."""
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
        if len(self._samples) < self._minimum_samples:
            return ()
        if self._samples_since_attempt < self._retry_samples:
            return ()
        self._samples_since_attempt = 0
        decoded: dict[tuple[str, int], MultichannelDecodeEvent] = {}
        capture = AudioBuffer(self._samples, audio.sample_rate)
        for frequency in self._spectral_candidates():
            candidate = self._decode_frequency(capture, frequency)
            if candidate is not None:
                if candidate.message is not None:
                    source = candidate.message.callsign
                elif candidate.station is not None:
                    source = candidate.station.data.callsign
                else:
                    assert candidate.report is not None
                    source = candidate.report.reporter
                decoded[(source, candidate.frame_id)] = candidate
        if decoded:
            self._samples = np.empty(0, dtype=np.float32)
        elif len(self._samples) > self._maximum_samples:
            self._samples = self._samples[-self._maximum_samples :]
        return tuple(decoded.values())
