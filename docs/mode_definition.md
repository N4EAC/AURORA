# Aurora development mode definition

## Status and scope

This document records the coding selection paired with Aurora's provisional
OFDM physical layer. It is **not** a released over-the-air protocol. Mode
identification, parameter negotiation, and a transmitted bootstrap header
remain unspecified.

## Selected parameters

| Parameter | Development selection |
|---|---|
| Waveform | OFDM |
| Subcarrier constellation | BPSK, normalized unit-energy symbols |
| Aggregate constellation rate | 300 symbols/s |
| FEC | Rate-1/2 convolutional code |
| Constraint length | 7 |
| Generator polynomials | 171 and 133 (octal) |
| Trellis termination | Six zero tail bits |
| Interleaver | Deterministic ragged block, 8 columns |
| Interleaver placement | After FEC, before symbol mapping |
| Experimental audio sample rate | 12,000 samples/s |
| Experimental audio carrier | 1,500 Hz |
| OFDM geometry | 256-point FFT, 64-sample cyclic prefix, 8 active carriers |

The corresponding immutable Python definition is
`modem.mode_definition.AURORA_ROBUST_MODE`.

The physical-layer details are defined in `docs/ofdm_mode_definition.md`.

## Interleaver decision

The 8-column geometry aligns one interleaver row with one OFDM data block. It is
fixed by this development-mode definition and is not
signaled. A receiver exercising this exact mode must already know the geometry.
Signaling it now would imply a bootstrap header and parsing rules that have not
been designed or validated.

The simulation UI may disable interleaving as an explicit diagnostic override
for controlled A/B measurements. Such a run is a test variation and is not the
defined robust simulation mode.

If future waveform and protocol research demonstrates a need for adaptive
geometry, Aurora must first define a robust mode-identification mechanism that
can be acquired without knowing the payload interleaver.

## Archived research waveform

The previous root-raised-cosine BPSK waveform is retained as
`AURORA_SINGLE_CARRIER_RESEARCH_MODE`. It supports reproduction of Deep studies
and historical audio fixtures but is no longer Aurora's primary waveform.
