# Aurora robust simulation mode definition

## Status and scope

This document records a reproducible selection of Aurora DSP components for
development and symbol-domain testing. It is **not** an over-the-air protocol
specification. Aurora does not yet define waveform filtering, acquisition,
mode identification, parameter negotiation, or a transmitted mode header.

This 31.25-symbol/s selection remains the Normal robust simulation baseline. It
is not the final Deep-mode configuration and does not establish the active
-24 dB performance objective defined in `docs/performance_targets.md`.

## Selected parameters

| Parameter | Development selection |
|---|---|
| Modulation | BPSK, normalized unit-energy symbols |
| Symbol rate | 31.25 symbols/s |
| FEC | Rate-1/2 convolutional code |
| Constraint length | 7 |
| Generator polynomials | 171 and 133 (octal) |
| Trellis termination | Six zero tail bits |
| Interleaver | Deterministic ragged block, 16 columns |
| Interleaver placement | After FEC, before symbol mapping |
| Experimental audio sample rate | 12,000 samples/s |
| Experimental audio carrier | 1,500 Hz |
| Experimental pulse shape | Root-raised cosine, 0.35 roll-off, 8-symbol span |

The corresponding immutable Python definition is
`modem.mode_definition.AURORA_ROBUST_MODE`.

## Interleaver decision

The 16-column geometry is fixed by this development-mode definition and is not
signaled. A receiver exercising this exact mode must already know the geometry.
Signaling it now would imply a bootstrap header and parsing rules that have not
been designed or validated.

The simulation UI may disable interleaving as an explicit diagnostic override
for controlled A/B measurements. Such a run is a test variation and is not the
defined robust simulation mode.

If future waveform and protocol research demonstrates a need for adaptive
geometry, Aurora must first define a robust mode-identification mechanism that
can be acquired without knowing the payload interleaver.

## Deliberately unspecified

This definition does not specify an occupied waveform, pulse shaping, carrier
frequency, preamble, synchronization sequence, frame timing, on-air mode ID,
parameter negotiation, or interoperability promise. Those require separate
design, implementation, and over-the-air validation.

The provisional offline audio realization is documented separately in
`docs/waveform_experiment.md` so waveform experiments do not imply that these
values are a frozen transmission protocol.
