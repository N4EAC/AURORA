"""Research-only payload coding for Aurora Deep-mode feasibility studies."""

from dataclasses import dataclass
import math
from typing import Sequence

from dsp.core import bits_to_bytes, bytes_to_bits
from dsp.fec import convolutional_encode, viterbi_decode_soft
from dsp.framing import Frame, build_frame, parse_frame
from dsp.interleaver import block_deinterleave, block_interleave
from dsp.scrambler import scramble_bits


NATIVE_RATE_QUARTER_GENERATORS = (0o171, 0o133, 0o165, 0o117)
K10_RATE_QUARTER_GENERATORS = (0o1713, 0o1475, 0o1267, 0o1137)
CONSTRAINT_LENGTH = 7
MEMORY_BITS = CONSTRAINT_LENGTH - 1
STATE_COUNT = 1 << MEMORY_BITS


@dataclass(frozen=True, slots=True)
class DeepCodecConfig:
    """Select provisional coding parameters without defining a protocol."""

    repetition: int = 2
    interleaver_columns: int = 16
    coding_scheme: str = "repeated_rate_half"
    constraint_length: int = CONSTRAINT_LENGTH
    generator_polynomials: tuple[int, ...] = NATIVE_RATE_QUARTER_GENERATORS

    def __post_init__(self) -> None:
        if self.repetition not in (1, 2):
            raise ValueError("Deep research repetition must be one or two")
        if self.interleaver_columns <= 0:
            raise ValueError("Interleaver columns must be positive")
        if self.coding_scheme not in ("repeated_rate_half", "native_rate_quarter"):
            raise ValueError("Unsupported Deep research coding scheme")
        if self.coding_scheme == "native_rate_quarter" and self.repetition != 1:
            raise ValueError("Native rate-1/4 coding does not use repetition")
        if self.constraint_length < 2:
            raise ValueError("Constraint length must exceed one")
        if len(self.generator_polynomials) != 4:
            raise ValueError("Native rate-1/4 coding requires four generators")
        limit = 1 << self.constraint_length
        if any(
            polynomial <= 0 or polynomial >= limit
            for polynomial in self.generator_polynomials
        ):
            raise ValueError("Generator polynomial exceeds constraint length")

    @property
    def nominal_code_rate(self) -> float:
        """Return the nominal information-to-coded-bit ratio before framing."""
        if self.coding_scheme == "native_rate_quarter":
            return 0.25
        return 1.0 / (2.0 * self.repetition)


@dataclass(frozen=True, slots=True)
class DeepEncodedPayload:
    """Coded BPSK bits and the configuration required to recover them."""

    bits: tuple[int, ...]
    frame_byte_count: int
    config: DeepCodecConfig


def encode_deep_payload(
    payload: bytes,
    config: DeepCodecConfig = DeepCodecConfig(),
) -> DeepEncodedPayload:
    """Frame, scramble, convolutionally encode, repeat, and interleave payload."""
    frame = build_frame(payload)
    scrambled = scramble_bits(bytes_to_bits(frame))
    if config.coding_scheme == "native_rate_quarter":
        protected = native_rate_quarter_encode(
            scrambled,
            config.generator_polynomials,
            config.constraint_length,
        )
    else:
        convolutional = convolutional_encode(scrambled)
        protected = [
            bit
            for bit in convolutional
            for _ in range(config.repetition)
        ]
    interleaved = block_interleave(protected, config.interleaver_columns)
    return DeepEncodedPayload(tuple(interleaved), len(frame), config)


def combine_repeated_likelihoods(
    likelihoods: Sequence[float], repetition: int
) -> list[float]:
    """Sum independent log-likelihoods for each repeated coded bit."""
    values = [float(value) for value in likelihoods]
    if repetition <= 0:
        raise ValueError("Repetition must be positive")
    if len(values) % repetition:
        raise ValueError("Likelihood count is not divisible by repetition")
    return [
        sum(values[offset : offset + repetition])
        for offset in range(0, len(values), repetition)
    ]


def _native_transition(
    state: int,
    bit: int,
    generators: tuple[int, ...],
    state_count: int,
) -> tuple[int, tuple[int, ...]]:
    register = (state << 1) | bit
    output = tuple(
        (register & polynomial).bit_count() & 1
        for polynomial in generators
    )
    return register & (state_count - 1), output


def native_rate_quarter_encode(
    bits: Sequence[int],
    generators: tuple[int, ...] = NATIVE_RATE_QUARTER_GENERATORS,
    constraint_length: int = CONSTRAINT_LENGTH,
) -> list[int]:
    """Encode with an experimental four-output constraint-length-7 code."""
    source = list(bits)
    if any(bit not in (0, 1) for bit in source):
        raise ValueError("Native FEC input must contain only binary values")
    memory_bits = constraint_length - 1
    state_count = 1 << memory_bits
    source.extend([0] * memory_bits)
    state = 0
    encoded: list[int] = []
    for bit in source:
        state, output = _native_transition(state, bit, generators, state_count)
        encoded.extend(output)
    return encoded


def native_rate_quarter_decode_soft(
    likelihoods: Sequence[float],
    generators: tuple[int, ...] = NATIVE_RATE_QUARTER_GENERATORS,
    constraint_length: int = CONSTRAINT_LENGTH,
) -> list[int]:
    """Soft-decode the experimental terminated four-output code."""
    received = [float(value) for value in likelihoods]
    output_count = len(generators)
    memory_bits = constraint_length - 1
    state_count = 1 << memory_bits
    if len(received) % output_count:
        raise ValueError("Native soft FEC requires complete four-value groups")
    if len(received) < memory_bits * output_count:
        raise ValueError("Native soft FEC input is too short")
    if any(not math.isfinite(value) for value in received):
        raise ValueError("Native soft FEC likelihoods must be finite")

    metrics = [-math.inf] * state_count
    metrics[0] = 0.0
    history: list[list[tuple[int, int] | None]] = []
    for offset in range(0, len(received), output_count):
        group = received[offset : offset + output_count]
        next_metrics = [-math.inf] * state_count
        predecessors: list[tuple[int, int] | None] = [None] * state_count
        for state, metric in enumerate(metrics):
            if metric == -math.inf:
                continue
            for source_bit in (0, 1):
                next_state, expected = _native_transition(
                    state, source_bit, generators, state_count
                )
                branch_score = sum(
                    (1.0 - 2.0 * bit) * value
                    for bit, value in zip(expected, group, strict=True)
                )
                candidate = metric + branch_score
                if candidate > next_metrics[next_state]:
                    next_metrics[next_state] = candidate
                    predecessors[next_state] = state, source_bit
        metrics = next_metrics
        history.append(predecessors)

    state = 0
    if metrics[state] == -math.inf:
        raise ValueError("Native soft FEC input has no terminated path")
    decoded: list[int] = []
    for predecessors in reversed(history):
        survivor = predecessors[state]
        if survivor is None:
            raise ValueError("Native soft FEC traceback failed")
        state, source_bit = survivor
        decoded.append(source_bit)
    decoded.reverse()
    return decoded[:-memory_bits]


def decode_deep_likelihoods(
    likelihoods: Sequence[float],
    config: DeepCodecConfig = DeepCodecConfig(),
) -> Frame:
    """Deinterleave and soft-decode one research payload with CRC validation."""
    ordered = block_deinterleave(likelihoods, config.interleaver_columns)
    if config.coding_scheme == "native_rate_quarter":
        scrambled = native_rate_quarter_decode_soft(
            ordered,
            config.generator_polynomials,
            config.constraint_length,
        )
    else:
        combined = combine_repeated_likelihoods(ordered, config.repetition)
        scrambled = viterbi_decode_soft(combined)
    frame_bits = scramble_bits(scrambled)
    return parse_frame(bits_to_bytes(frame_bits))


def polynomial_gcd(polynomials: Sequence[int]) -> int:
    """Return the greatest common divisor over GF(2)."""
    values = [int(value) for value in polynomials]
    if not values or any(value <= 0 for value in values):
        raise ValueError("Generator polynomials must be positive")

    def remainder(dividend: int, divisor: int) -> int:
        while dividend.bit_length() >= divisor.bit_length():
            dividend ^= divisor << (
                dividend.bit_length() - divisor.bit_length()
            )
        return dividend

    result = values[0]
    for value in values[1:]:
        while value:
            result, value = value, remainder(result, value)
    return result


def bounded_free_distance(
    generators: tuple[int, ...],
    constraint_length: int,
    *,
    maximum_steps: int = 64,
) -> int:
    """Return the minimum remerging path weight within a bounded trellis."""
    if maximum_steps < constraint_length:
        raise ValueError("Free-distance search depth is too short")
    state_count = 1 << (constraint_length - 1)
    state, output = _native_transition(0, 1, generators, state_count)
    paths = {state: sum(output)}
    best = math.inf
    for _ in range(1, maximum_steps):
        next_paths: dict[int, int] = {}
        for current_state, weight in paths.items():
            for source_bit in (0, 1):
                next_state, encoded = _native_transition(
                    current_state,
                    source_bit,
                    generators,
                    state_count,
                )
                candidate = weight + sum(encoded)
                if next_state == 0:
                    best = min(best, candidate)
                    continue
                previous = next_paths.get(next_state)
                if previous is None or candidate < previous:
                    next_paths[next_state] = candidate
        paths = next_paths
        if not paths:
            break
    if best == math.inf:
        raise ValueError("No nonzero path remerged within search depth")
    return int(best)
