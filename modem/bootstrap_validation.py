"""Deterministic weak-signal characterization for Aurora bootstrap decoding."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audio.buffer import AudioBuffer
from dsp.audio_channel import AudioChannelConfig, apply_audio_channel
from dsp.core import decode_soft_symbols
from dsp.waveform import demodulate_audio, modulate_audio
from modem.bootstrap import (
    BootstrapHeader,
    FRAME_TYPE_CHAT,
    decode_bootstrap_frame,
    encode_bootstrap,
)
from modem.mode_definition import AURORA_BANDWIDTH_MODES


@dataclass(frozen=True, slots=True)
class BootstrapCharacterizationResult:
    """CRC-confirmed signal and noise-only outcomes for one condition."""

    bandwidth_hz: int
    snr_db: float
    signal_trials: int
    decoded_signals: int
    noise_trials: int
    false_decodes: int
    mean_sync_metric: float

    @property
    def success_rate(self) -> float:
        """Return CRC-confirmed bootstrap delivery fraction."""
        return self.decoded_signals / self.signal_trials


def run_bootstrap_characterization(
    *,
    bandwidth_hz: int = 500,
    snr_db: float = -8.0,
    signal_trials: int = 40,
    noise_trials: int = 100,
    seed: int = 20260825,
) -> BootstrapCharacterizationResult:
    """Run seeded audio-AWGN bootstrap and matched noise-only trials."""
    if signal_trials <= 0 or noise_trials < 0:
        raise ValueError("Bootstrap trial counts are invalid")
    try:
        mode = AURORA_BANDWIDTH_MODES[bandwidth_hz]
    except KeyError as error:
        raise ValueError("Bootstrap bandwidth must be 500, 2300, or 2800 Hz") from error
    header = BootstrapHeader(
        FRAME_TYPE_CHAT,
        bandwidth_hz,
        mode.interleaver_columns,
        400,
        50,
        0xA0250001,
    )
    transmission = encode_bootstrap(header, mode)
    clean = modulate_audio(transmission.symbols, mode, leading_silence_samples=211)
    random = np.random.default_rng(seed)
    decoded = 0
    metrics = []
    channel = AudioChannelConfig(snr_db=snr_db)
    for _ in range(signal_trials):
        impaired = apply_audio_channel(clean, channel, random)
        try:
            recovered = demodulate_audio(impaired, len(transmission.symbols), mode)
            frame = decode_soft_symbols(
                tuple(recovered.symbols),
                mode.modulation,
                interleaver_columns=mode.interleaver_columns,
            )
            if decode_bootstrap_frame(frame) == header:
                decoded += 1
                metrics.append(recovered.diagnostics.sync_metric)
        except ValueError:
            continue
    false_decodes = 0
    signal_rms = float(np.sqrt(np.mean(np.asarray(clean.samples) ** 2)))
    for _ in range(noise_trials):
        noise = random.normal(0.0, signal_rms, clean.frame_count).astype(np.float32)
        try:
            recovered = demodulate_audio(
                AudioBuffer(noise, clean.sample_rate),
                len(transmission.symbols),
                mode,
            )
            frame = decode_soft_symbols(
                tuple(recovered.symbols),
                mode.modulation,
                interleaver_columns=mode.interleaver_columns,
            )
            decode_bootstrap_frame(frame)
        except ValueError:
            continue
        false_decodes += 1
    return BootstrapCharacterizationResult(
        bandwidth_hz,
        snr_db,
        signal_trials,
        decoded,
        noise_trials,
        false_decodes,
        float(np.mean(metrics)) if metrics else 0.0,
    )


if __name__ == "__main__":
    for profile in (500, 2_300, 2_800):
        result = run_bootstrap_characterization(bandwidth_hz=profile)
        print(result)
