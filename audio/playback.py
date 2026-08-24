"""Buffered audio playback for Aurora."""

import numpy as np
import sounddevice as sd

from audio.buffer import AudioBuffer


def condition_playback(
    audio: AudioBuffer,
    *,
    gain: float = 0.55,
    fade_seconds: float = 0.02,
    trailing_silence_seconds: float = 0.10,
) -> AudioBuffer:
    """Add monitor headroom and click-free boundaries to buffered audio."""
    if not 0.0 < gain <= 1.0:
        raise ValueError("Playback gain must be greater than zero and at most one")
    if fade_seconds < 0.0 or trailing_silence_seconds < 0.0:
        raise ValueError("Playback fade and trailing silence must not be negative")
    samples = np.asarray(audio.samples, dtype=np.float32).reshape(-1).copy()
    samples *= gain
    fade_count = min(round(fade_seconds * audio.sample_rate), len(samples) // 2)
    if fade_count:
        phase = np.linspace(0.0, np.pi, fade_count, endpoint=True)
        ramp = (0.5 - 0.5 * np.cos(phase)).astype(np.float32)
        samples[:fade_count] *= ramp
        samples[-fade_count:] *= ramp[::-1]
    trailing_count = round(trailing_silence_seconds * audio.sample_rate)
    if trailing_count:
        samples = np.pad(samples, (0, trailing_count))
    return AudioBuffer(samples.astype(np.float32), audio.sample_rate)


def play_audio(
    audio: AudioBuffer, *, blocking: bool = False, device: int | str | None = None
) -> None:
    """Play an audio buffer through an output device."""
    sd.play(
        audio.samples,
        samplerate=audio.sample_rate,
        device=device,
        blocking=blocking,
    )


def stop_playback() -> None:
    """Stop playback started through the buffered playback API."""
    sd.stop()
