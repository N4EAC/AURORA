# Aurora development mode definition

## Status and scope

This document records the coding selection paired with Aurora's provisional
OFDM physical layer. It is **not** a released over-the-air protocol. A
protected bootstrap now identifies the frame profile and exact payload
geometry; negotiation and controlled HF validation remain unfinished.

## Selected parameters

| Parameter | Development selection |
|---|---|
| Waveform | OFDM |
| Subcarrier constellation | BPSK, normalized unit-energy symbols |
| Aggregate constellation rate | 300, 1,575, or 1,950 symbols/s |
| FEC | Rate-1/2 convolutional code |
| Constraint length | 7 |
| Generator polynomials | 171 and 133 (octal) |
| Trellis termination | Six zero tail bits |
| Interleaver | Deterministic ragged block, 8, 42, or 52 columns |
| Interleaver placement | After FEC, before symbol mapping |
| Experimental audio sample rate | 12,000 samples/s |
| Experimental audio carrier | 1,500 Hz |
| OFDM geometry | 256-point FFT, 64-sample prefix, 8, 42, or 52 active carriers |

The corresponding immutable Python definition is
`modem.mode_definition.AURORA_ROBUST_MODE`.

The physical-layer details are defined in `docs/ofdm_mode_definition.md`.

## Interleaver decision

Each interleaver geometry aligns one row with the active carriers in its OFDM
profile. The selected geometry is fixed for a frame and transmitted in the
protected bootstrap with the bandwidth, constellation, FEC, and payload size.
The current receiver validates that advertised geometry before payload decode.

The simulation UI may disable interleaving as an explicit diagnostic override
for controlled A/B measurements. Such a run is a test variation and is not the
defined robust simulation mode.

Bootstrap acquisition under weak, fading HF conditions remains to be
characterized before this signaling format is considered stable.

## Archived research waveform

The previous root-raised-cosine BPSK waveform is retained as
`AURORA_SINGLE_CARRIER_RESEARCH_MODE`. It supports reproduction of Deep studies
and historical audio fixtures but is no longer Aurora's primary waveform.
