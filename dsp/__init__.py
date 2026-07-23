"""Digital signal-processing core for Aurora."""

from dsp.core import (
    EncodedTransmission,
    decode_soft_symbols,
    decode_transmission,
    encode_payload,
)
from dsp.audio_channel import AudioChannelConfig, apply_audio_channel
from dsp.framing import Frame, FrameError
from dsp.interleaver import block_deinterleave, block_interleave
from dsp.receiver import AuroraReceiver, ReceiverConfig, ReceiverDiagnostics, ReceiverResult
from dsp.waveform import (
    WaveformDiagnostics,
    WaveformResult,
    demodulate_audio,
    modulate_audio,
    occupied_bandwidth_hz,
)

__all__ = [
    "EncodedTransmission",
    "AudioChannelConfig",
    "Frame",
    "FrameError",
    "AuroraReceiver",
    "ReceiverConfig",
    "ReceiverDiagnostics",
    "ReceiverResult",
    "decode_soft_symbols",
    "decode_transmission",
    "encode_payload",
    "block_deinterleave",
    "block_interleave",
    "apply_audio_channel",
    "WaveformDiagnostics",
    "WaveformResult",
    "demodulate_audio",
    "modulate_audio",
    "occupied_bandwidth_hz",
]
