"""Digital signal-processing core for Aurora."""

from dsp.core import (
    EncodedTransmission,
    decode_soft_symbols,
    decode_transmission,
    encode_payload,
)
from dsp.framing import Frame, FrameError
from dsp.interleaver import block_deinterleave, block_interleave
from dsp.receiver import AuroraReceiver, ReceiverConfig, ReceiverDiagnostics, ReceiverResult

__all__ = [
    "EncodedTransmission",
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
]
