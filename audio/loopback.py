"""Audio-device loopback validation without radio control."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd

from audio.buffer import AudioBuffer
from audio.wav import write_wav
from dsp.core import decode_soft_symbols, encode_payload
from dsp.deep_codec import decode_deep_likelihoods, encode_deep_payload
from dsp.deep_waveform import (
    DeepWaveformResult,
    modulate_deep_audio,
    recover_deep_candidate_likelihoods,
)
from dsp.framing import FrameError
from dsp.waveform import WaveformDiagnostics, demodulate_audio, modulate_audio
from modem.deep_validation import K10_DEEP_CODEC
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


@dataclass(frozen=True, slots=True)
class AudioLoopbackResult:
    """Decoded loopback payload and reproducible capture diagnostics."""

    transmitted_text: str
    received_text: str
    capture_path: Path
    diagnostics: WaveformDiagnostics
    duration_seconds: float
    peak_level: float
    clipped: bool


@dataclass(frozen=True, slots=True)
class DeepAudioLoopbackResult:
    """CRC-confirmed result from the provisional Deep research waveform."""

    transmitted_payload: bytes
    received_payload: bytes
    capture_path: Path
    diagnostics: DeepWaveformResult
    duration_seconds: float
    peak_level: float
    clipped: bool


def run_audio_loopback(
    message: str,
    *,
    input_device: int,
    output_device: int,
    capture_path: str | Path,
    output_gain: float = 1.0,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> AudioLoopbackResult:
    """Play one Aurora frame, capture it simultaneously, and decode the result."""
    text = message.strip()
    if not text:
        raise ValueError("Enter a loopback test message")
    if not 0.0 < output_gain <= 1.0:
        raise ValueError("Loopback output gain must be greater than zero and at most one")
    transmission = encode_payload(
        text.encode("utf-8"),
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )
    waveform = modulate_audio(
        transmission.symbols,
        mode,
        leading_silence_samples=mode.audio_sample_rate,
    )
    samples = np.pad(
        np.asarray(waveform.samples, dtype=np.float32) * output_gain,
        (0, mode.audio_sample_rate),
    )
    captured = sd.playrec(
        samples[:, np.newaxis],
        samplerate=mode.audio_sample_rate,
        channels=1,
        dtype="float32",
        device=(input_device, output_device),
        blocking=True,
    )
    captured_audio = AudioBuffer(
        np.asarray(captured, dtype=np.float32).reshape(-1),
        mode.audio_sample_rate,
    )
    path = Path(capture_path)
    write_wav(path, captured_audio)
    recovered = demodulate_audio(
        captured_audio,
        len(transmission.symbols),
        mode,
    )
    frame = decode_soft_symbols(
        tuple(recovered.symbols),
        mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )
    received = frame.payload.decode("utf-8")
    peak = float(np.max(np.abs(captured_audio.samples)))
    return AudioLoopbackResult(
        text,
        received,
        path,
        recovered.diagnostics,
        captured_audio.duration_seconds,
        peak,
        peak >= 0.999,
    )


def run_deep_audio_loopback(
    payload: bytes,
    *,
    input_device: int,
    output_device: int,
    capture_path: str | Path,
    output_gain: float = 0.75,
) -> DeepAudioLoopbackResult:
    """Play, capture, and CRC-decode one provisional Deep research frame."""
    if len(payload) != 20:
        raise ValueError("Deep loopback payload must contain exactly 20 bytes")
    if not 0.0 < output_gain <= 1.0:
        raise ValueError("Loopback output gain must be greater than zero and at most one")
    encoded = encode_deep_payload(payload, K10_DEEP_CODEC)
    waveform = modulate_deep_audio(
        encoded.bits,
        leading_silence_samples=AURORA_ROBUST_MODE.audio_sample_rate,
        pilot_symbol_count=32,
    )
    samples = np.pad(
        np.asarray(waveform.samples, dtype=np.float32) * output_gain,
        (0, AURORA_ROBUST_MODE.audio_sample_rate),
    )
    captured = sd.playrec(
        samples[:, np.newaxis],
        samplerate=AURORA_ROBUST_MODE.audio_sample_rate,
        channels=1,
        dtype="float32",
        device=(input_device, output_device),
        blocking=True,
    )
    captured_audio = AudioBuffer(
        np.asarray(captured, dtype=np.float32).reshape(-1),
        AURORA_ROBUST_MODE.audio_sample_rate,
    )
    path = Path(capture_path)
    write_wav(path, captured_audio)
    candidates = recover_deep_candidate_likelihoods(
        captured_audio,
        len(encoded.bits),
        pilot_symbol_count=32,
        acquisition_diversity=True,
    )
    for candidate in candidates:
        try:
            frame = decode_deep_likelihoods(candidate.likelihoods, encoded.config)
        except (FrameError, ValueError):
            continue
        peak = float(np.max(np.abs(captured_audio.samples)))
        return DeepAudioLoopbackResult(
            payload,
            frame.payload,
            path,
            candidate,
            captured_audio.duration_seconds,
            peak,
            peak >= 0.999,
        )
    raise ValueError("Deep loopback capture did not produce a CRC-valid frame")
