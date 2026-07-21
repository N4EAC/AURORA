"""Bit scrambling for spectral whitening."""

from collections.abc import Iterable


DEFAULT_SEED = 0x1FF
REGISTER_MASK = 0x1FF


def scramble_bits(bits: Iterable[int], seed: int = DEFAULT_SEED) -> list[int]:
    """Scramble or descramble bits with the x^9 + x^5 + 1 sequence."""
    if not 0 < seed <= REGISTER_MASK:
        raise ValueError("Scrambler seed must be a non-zero 9-bit value")

    state = seed
    result: list[int] = []
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError("Scrambler input must contain only binary values")
        sequence_bit = ((state >> 8) ^ (state >> 4)) & 1
        result.append(bit ^ sequence_bit)
        state = ((state << 1) & REGISTER_MASK) | sequence_bit
    return result
