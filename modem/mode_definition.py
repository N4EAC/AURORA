"""Central development-mode parameters for Aurora simulations.

This module selects existing DSP building blocks.  It does not define an
over-the-air protocol, mode-identification header, or negotiation mechanism.
"""

from dataclasses import dataclass, replace


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
    waveform: str = "single_carrier"
    occupied_bandwidth_hz: int = 500
    ofdm_edge_subcarrier: int = 4
    interleaver_geometry_signaled: bool = False

    def __post_init__(self) -> None:
        if self.modulation.lower() != "bpsk":
            raise ValueError("Aurora modes require BPSK subcarrier mapping")
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
        if self.waveform == "single_carrier" and self.audio_sample_rate / self.symbol_rate % 1.0:
            raise ValueError("Waveform requires an integer samples-per-symbol ratio")
        if not 0.0 < self.audio_carrier_hz < self.audio_sample_rate / 2.0:
            raise ValueError("Audio carrier must be below the Nyquist frequency")
        if self.pulse_shape not in {"root_raised_cosine", "ofdm"}:
            raise ValueError("Unsupported pulse shape")
        if not 0.0 < self.pulse_rolloff <= 1.0:
            raise ValueError("Pulse roll-off must be between zero and one")
        if self.pulse_span_symbols <= 0 or self.pulse_span_symbols % 2:
            raise ValueError("Pulse span must be a positive even symbol count")
        if self.waveform not in {"single_carrier", "ofdm"}:
            raise ValueError("Unsupported Aurora waveform")
        if self.occupied_bandwidth_hz not in {500, 2_300, 2_800}:
            raise ValueError("Aurora bandwidth must be 500, 2300, or 2800 Hz")
        if self.ofdm_edge_subcarrier <= 0:
            raise ValueError("OFDM edge subcarrier must be positive")


AURORA_SINGLE_CARRIER_RESEARCH_MODE = ModeDefinition(
    name="Aurora archived single-carrier research mode",
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


AURORA_500_MODE = ModeDefinition(
    name="Aurora OFDM 500 Hz robust mode",
    modulation="bpsk",
    symbol_rate=300.0,
    fec_rate_numerator=1,
    fec_rate_denominator=2,
    fec_constraint_length=7,
    fec_generator_polynomials=(0o171, 0o133),
    fec_terminated=True,
    interleaver_columns=8,
    audio_sample_rate=12_000,
    audio_carrier_hz=1_500.0,
    pulse_shape="ofdm",
    pulse_rolloff=0.10,
    pulse_span_symbols=2,
    waveform="ofdm",
    occupied_bandwidth_hz=500,
    ofdm_edge_subcarrier=4,
    interleaver_geometry_signaled=True,
)


AURORA_2300_MODE = replace(
    AURORA_500_MODE,
    name="Aurora OFDM 2.3 kHz standard mode",
    symbol_rate=1_575.0,
    interleaver_columns=42,
    occupied_bandwidth_hz=2_300,
    ofdm_edge_subcarrier=21,
)


AURORA_2800_MODE = replace(
    AURORA_500_MODE,
    name="Aurora OFDM 2.8 kHz wide mode",
    symbol_rate=1_950.0,
    interleaver_columns=52,
    occupied_bandwidth_hz=2_800,
    ofdm_edge_subcarrier=26,
)


AURORA_BANDWIDTH_MODES = {
    500: AURORA_500_MODE,
    2_300: AURORA_2300_MODE,
    2_800: AURORA_2800_MODE,
}

# Safe default when no trustworthy channel estimate is available.
AURORA_ROBUST_MODE = AURORA_500_MODE
