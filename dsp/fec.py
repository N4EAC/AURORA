"""Convolutional forward error correction for Aurora."""

from collections.abc import Iterable, Sequence
import math


CONSTRAINT_LENGTH = 7
MEMORY_BITS = CONSTRAINT_LENGTH - 1
STATE_COUNT = 1 << MEMORY_BITS
GENERATOR_POLYNOMIALS = (0o171, 0o133)


def _parity(value: int) -> int:
    return value.bit_count() & 1


def _validate_bits(bits: Iterable[int]) -> list[int]:
    validated = list(bits)
    if any(bit not in (0, 1) for bit in validated):
        raise ValueError("FEC input must contain only binary values")
    return validated


def _transition(state: int, bit: int) -> tuple[int, tuple[int, int]]:
    register = (state << 1) | bit
    output = tuple(_parity(register & poly) for poly in GENERATOR_POLYNOMIALS)
    return register & (STATE_COUNT - 1), output


def convolutional_encode(bits: Iterable[int], terminate: bool = True) -> list[int]:
    """Encode bits with the rate-1/2, constraint-length-7 code."""
    source = _validate_bits(bits)
    if terminate:
        source.extend([0] * MEMORY_BITS)

    state = 0
    encoded: list[int] = []
    for bit in source:
        state, output = _transition(state, bit)
        encoded.extend(output)
    return encoded


def viterbi_decode(bits: Sequence[int], terminated: bool = True) -> list[int]:
    """Hard-decision decode a rate-1/2 convolutionally encoded bit sequence."""
    received = _validate_bits(bits)
    if len(received) % 2:
        raise ValueError("Encoded FEC input must contain complete bit pairs")
    if terminated and len(received) < MEMORY_BITS * 2:
        raise ValueError("Terminated FEC input is too short")

    infinity = len(received) + 1
    metrics = [infinity] * STATE_COUNT
    metrics[0] = 0
    history: list[list[tuple[int, int] | None]] = []

    for offset in range(0, len(received), 2):
        received_pair = received[offset], received[offset + 1]
        next_metrics = [infinity] * STATE_COUNT
        predecessors: list[tuple[int, int] | None] = [None] * STATE_COUNT
        for state, metric in enumerate(metrics):
            if metric == infinity:
                continue
            for source_bit in (0, 1):
                next_state, expected = _transition(state, source_bit)
                distance = (expected[0] != received_pair[0]) + (
                    expected[1] != received_pair[1]
                )
                candidate = metric + distance
                if candidate < next_metrics[next_state]:
                    next_metrics[next_state] = candidate
                    predecessors[next_state] = state, source_bit
        metrics = next_metrics
        history.append(predecessors)

    state = 0 if terminated else min(range(STATE_COUNT), key=metrics.__getitem__)
    if metrics[state] == infinity:
        raise ValueError("FEC input has no valid decoding path")

    decoded: list[int] = []
    for predecessors in reversed(history):
        survivor = predecessors[state]
        if survivor is None:
            raise ValueError("FEC traceback failed")
        state, source_bit = survivor
        decoded.append(source_bit)
    decoded.reverse()

    if terminated:
        return decoded[:-MEMORY_BITS]
    return decoded


def viterbi_decode_soft(
    likelihoods: Sequence[float], terminated: bool = True
) -> list[int]:
    """Decode FEC using log-likelihood ratios positive toward bit zero."""
    received = [float(value) for value in likelihoods]
    if len(received) % 2:
        raise ValueError("Soft FEC input must contain complete likelihood pairs")
    if terminated and len(received) < MEMORY_BITS * 2:
        raise ValueError("Terminated soft FEC input is too short")
    if any(not math.isfinite(value) for value in received):
        raise ValueError("Soft FEC likelihoods must be finite")

    metrics = [-math.inf] * STATE_COUNT
    metrics[0] = 0.0
    history: list[list[tuple[int, int] | None]] = []
    for offset in range(0, len(received), 2):
        pair = received[offset], received[offset + 1]
        next_metrics = [-math.inf] * STATE_COUNT
        predecessors: list[tuple[int, int] | None] = [None] * STATE_COUNT
        for state, metric in enumerate(metrics):
            if metric == -math.inf:
                continue
            for source_bit in (0, 1):
                next_state, expected = _transition(state, source_bit)
                branch_score = sum(
                    (1.0 - 2.0 * bit) * value
                    for bit, value in zip(expected, pair, strict=True)
                )
                candidate = metric + branch_score
                if candidate > next_metrics[next_state]:
                    next_metrics[next_state] = candidate
                    predecessors[next_state] = state, source_bit
        metrics = next_metrics
        history.append(predecessors)

    state = 0 if terminated else max(range(STATE_COUNT), key=metrics.__getitem__)
    if metrics[state] == -math.inf:
        raise ValueError("Soft FEC input has no valid decoding path")

    decoded: list[int] = []
    for predecessors in reversed(history):
        survivor = predecessors[state]
        if survivor is None:
            raise ValueError("Soft FEC traceback failed")
        state, source_bit = survivor
        decoded.append(source_bit)
    decoded.reverse()
    return decoded[:-MEMORY_BITS] if terminated else decoded
