"""Buffered audio playback for Aurora."""

import sounddevice as sd

from audio.buffer import AudioBuffer


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
