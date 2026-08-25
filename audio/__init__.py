"""Audio input, output, and file handling for Aurora."""

from audio.buffer import AudioBuffer
from audio.continuous_receiver import (
    ContinuousAudioReceiver,
    ContinuousDecodeEvent,
    ContinuousReceiverConfig,
    ContinuousReceiverDiagnostics,
)
from audio.device import (
    AudioDevice,
    compatible_outputs,
    list_audio_devices,
    preferred_loopback_pair,
)
from audio.multichannel_receiver import (
    MAX_AUDIO_FREQUENCY_HZ,
    MIN_AUDIO_FREQUENCY_HZ,
    MultichannelAudioReceiver,
    MultichannelDecodeEvent,
    mode_at_frequency,
)
from audio.playback import condition_playback, play_audio, stop_playback
from audio.streaming import (
    AudioDuplexStream,
    AudioInputStream,
    AudioOutputStream,
    AudioStreamStatus,
)
from audio.wav import read_wav, write_wav

__all__ = [
    "AudioBuffer",
    "ContinuousAudioReceiver",
    "ContinuousDecodeEvent",
    "ContinuousReceiverConfig",
    "ContinuousReceiverDiagnostics",
    "MAX_AUDIO_FREQUENCY_HZ",
    "MIN_AUDIO_FREQUENCY_HZ",
    "MultichannelAudioReceiver",
    "MultichannelDecodeEvent",
    "AudioDevice",
    "AudioDuplexStream",
    "AudioInputStream",
    "AudioOutputStream",
    "AudioStreamStatus",
    "list_audio_devices",
    "mode_at_frequency",
    "compatible_outputs",
    "condition_playback",
    "preferred_loopback_pair",
    "play_audio",
    "read_wav",
    "stop_playback",
    "write_wav",
]
