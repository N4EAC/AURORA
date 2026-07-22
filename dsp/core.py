"""Composable transmit and receive DSP pipeline for Aurora."""

from dataclasses import dataclass

from dsp.fec import convolutional_encode, viterbi_decode, viterbi_decode_soft
from dsp.framing import Frame, build_frame, parse_frame
from dsp.interleaver import block_deinterleave, block_interleave
from dsp.scrambler import scramble_bits
from dsp.symbol_mapper import demap_symbols, map_bits
from dsp.soft_decision import soft_demapping


@dataclass(frozen=True, slots=True)
class EncodedTransmission:
    """Mapped symbols and the modulation needed to decode them."""

    symbols: tuple[complex, ...]
    modulation: str
    interleaver_columns: int | None = None


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
    payload: bytes,
    flags: int = 0,
    modulation: str = "qpsk",
    *,
    interleaver_columns: int | None = None,
) -> EncodedTransmission:
    """Frame, scramble, protect, and map a payload for transmission."""
    frame_bits = bytes_to_bits(build_frame(payload, flags))
    scrambled = scramble_bits(frame_bits)
    protected = convolutional_encode(scrambled)
    if interleaver_columns is not None:
        protected = block_interleave(protected, interleaver_columns)
    symbols = map_bits(protected, modulation)
    return EncodedTransmission(
        tuple(symbols), modulation.lower(), interleaver_columns=interleaver_columns
    )


def decode_symbols(
    symbols: tuple[complex, ...],
    modulation: str = "qpsk",
    *,
    interleaver_columns: int | None = None,
) -> Frame:
    """Demap, decode, descramble, and validate received symbols."""
    protected = demap_symbols(symbols, modulation)
    if interleaver_columns is not None:
        protected = block_deinterleave(protected, interleaver_columns)
    scrambled = viterbi_decode(protected)
    frame_bits = scramble_bits(scrambled)
    return parse_frame(bits_to_bytes(frame_bits))


def decode_transmission(transmission: EncodedTransmission) -> Frame:
    """Decode a complete encoded transmission."""
    return decode_symbols(
        transmission.symbols,
        transmission.modulation,
        interleaver_columns=transmission.interleaver_columns,
    )


def decode_soft_symbols(
    symbols: tuple[complex, ...],
    modulation: str = "qpsk",
    *,
    noise_variance: float = 1.0,
    interleaver_columns: int | None = None,
) -> Frame:
    """Decode received symbols using soft demapping and soft-input FEC."""
    likelihoods = soft_demapping(
        symbols, modulation=modulation, noise_variance=noise_variance
    )
    if interleaver_columns is not None:
        likelihoods = block_deinterleave(likelihoods, interleaver_columns)
    scrambled = viterbi_decode_soft(likelihoods)
    frame_bits = scramble_bits(scrambled)
    return parse_frame(bits_to_bytes(frame_bits))
