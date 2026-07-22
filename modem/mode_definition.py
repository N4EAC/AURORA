"""Central development-mode parameters for Aurora simulations.

This module selects existing DSP building blocks.  It does not define an
over-the-air protocol, mode-identification header, or negotiation mechanism.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModeDefinition:
    """Immutable selection of DSP parameters for a development mode."""

    name: str
    modulation: str
    symbol_rate: float
    fec_rate_numerator: int
    fec_rate_denominator: int
    fec_constraint_length: int
    fec_generator_polynomials: tuple[int, ...]
    fec_terminated: bool
    interleaver_columns: int
    audio_sample_rate: int
    audio_carrier_hz: float
    pulse_shape: str
    pulse_rolloff: float
    pulse_span_symbols: int
    interleaver_geometry_signaled: bool = False

    def __post_init__(self) -> None:
        if self.modulation.lower() != "bpsk":
            raise ValueError("The Aurora robust development mode requires BPSK")
        if self.symbol_rate <= 0.0:
            raise ValueError("Symbol rate must be positive")
        if self.fec_rate_numerator <= 0 or self.fec_rate_denominator <= 0:
            raise ValueError("FEC rate terms must be positive")
        if self.fec_constraint_length <= 1:
            raise ValueError("FEC constraint length must exceed one")
        if not self.fec_generator_polynomials:
            raise ValueError("At least one FEC generator polynomial is required")
        if self.interleaver_columns <= 0:
            raise ValueError("Interleaver columns must be positive")
        if self.audio_sample_rate <= 0:
            raise ValueError("Audio sample rate must be positive")
        if self.audio_sample_rate / self.symbol_rate % 1.0:
            raise ValueError("Waveform requires an integer samples-per-symbol ratio")
        if not 0.0 < self.audio_carrier_hz < self.audio_sample_rate / 2.0:
            raise ValueError("Audio carrier must be below the Nyquist frequency")
        if self.pulse_shape != "root_raised_cosine":
            raise ValueError("Unsupported pulse shape")
        if not 0.0 < self.pulse_rolloff <= 1.0:
            raise ValueError("Pulse roll-off must be between zero and one")
        if self.pulse_span_symbols <= 0 or self.pulse_span_symbols % 2:
            raise ValueError("Pulse span must be a positive even symbol count")
        if self.interleaver_geometry_signaled:
            raise ValueError("Aurora has no signaling protocol for mode geometry")


AURORA_ROBUST_MODE = ModeDefinition(
    name="Aurora robust simulation mode",
    modulation="bpsk",
    symbol_rate=31.25,
    fec_rate_numerator=1,
    fec_rate_denominator=2,
    fec_constraint_length=7,
    fec_generator_polynomials=(0o171, 0o133),
    fec_terminated=True,
    interleaver_columns=16,
    audio_sample_rate=12_000,
    audio_carrier_hz=1_500.0,
    pulse_shape="root_raised_cosine",
    pulse_rolloff=0.35,
    pulse_span_symbols=8,
)
