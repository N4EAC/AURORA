"""Composable transmit and receive DSP pipeline for Aurora."""

from dataclasses import dataclass

from dsp.fec import convolutional_encode, viterbi_decode, viterbi_decode_soft
from dsp.framing import Frame, build_frame, parse_frame
from dsp.scrambler import scramble_bits
from dsp.symbol_mapper import demap_symbols, map_bits
from dsp.soft_decision import soft_demapping


@dataclass(frozen=True, slots=True)
class EncodedTransmission:
    """Mapped symbols and the modulation needed to decode them."""

    symbols: tuple[complex, ...]
    modulation: str


def bytes_to_bits(data: bytes) -> list[int]:
    """Convert bytes to most-significant-bit-first binary values."""
    return [
        (byte >> shift) & 1
        for byte in data
        for shift in range(7, -1, -1)
    ]


def bits_to_bytes(bits: list[int]) -> bytes:
    """Convert most-significant-bit-first binary values to bytes."""
    if len(bits) % 8:
        raise ValueError("Bit count must be a multiple of eight")
    if any(bit not in (0, 1) for bit in bits):
        raise ValueError("Byte conversion input must contain only binary values")

    return bytes(
        sum(bits[offset + index] << (7 - index) for index in range(8))
        for offset in range(0, len(bits), 8)
    )


def encode_payload(
    payload: bytes, flags: int = 0, modulation: str = "qpsk"
) -> EncodedTransmission:
    """Frame, scramble, protect, and map a payload for transmission."""
    frame_bits = bytes_to_bits(build_frame(payload, flags))
    scrambled = scramble_bits(frame_bits)
    protected = convolutional_encode(scrambled)
    symbols = map_bits(protected, modulation)
    return EncodedTransmission(tuple(symbols), modulation.lower())


def decode_symbols(symbols: tuple[complex, ...], modulation: str = "qpsk") -> Frame:
    """Demap, decode, descramble, and validate received symbols."""
    protected = demap_symbols(symbols, modulation)
    scrambled = viterbi_decode(protected)
    frame_bits = scramble_bits(scrambled)
    return parse_frame(bits_to_bytes(frame_bits))


def decode_transmission(transmission: EncodedTransmission) -> Frame:
    """Decode a complete encoded transmission."""
    return decode_symbols(transmission.symbols, transmission.modulation)


def decode_soft_symbols(
    symbols: tuple[complex, ...],
    modulation: str = "qpsk",
    *,
    noise_variance: float = 1.0,
) -> Frame:
    """Decode received symbols using soft demapping and soft-input FEC."""
    likelihoods = soft_demapping(
        symbols, modulation=modulation, noise_variance=noise_variance
    )
    scrambled = viterbi_decode_soft(likelihoods)
    frame_bits = scramble_bits(scrambled)
    return parse_frame(bits_to_bytes(frame_bits))
