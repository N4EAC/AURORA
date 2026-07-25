"""Audio input, output, and file handling for Aurora."""

from audio.buffer import AudioBuffer
from audio.device import (
    AudioDevice,
    compatible_outputs,
    list_audio_devices,
    preferred_loopback_pair,
)
from audio.playback import play_audio, stop_playback
from audio.streaming import AudioDuplexStream, AudioInputStream, AudioOutputStream
from audio.wav import read_wav, write_wav

__all__ = [
    "AudioBuffer",
    "AudioDevice",
    "AudioDuplexStream",
    "AudioInputStream",
    "AudioOutputStream",
    "list_audio_devices",
    "compatible_outputs",
    "preferred_loopback_pair",
    "play_audio",
    "read_wav",
    "stop_playback",
    "write_wav",
]
