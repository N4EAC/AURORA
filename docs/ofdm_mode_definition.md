# Aurora OFDM development waveform

## Status

Aurora now uses OFDM as its primary development waveform. This definition is
provisional and exists to make simulations, audio loopback, and receiver work
reproducible. It is not an interoperability promise or a released on-air
standard.

The former 31.25-symbol/s single-carrier waveform remains available only as an
archived research comparator for historical Deep studies and recorded test
fixtures.

## Physical parameters

| Parameter | Selection |
|---|---|
| Audio sample rate | 12,000 samples/s |
| Audio center frequency | 1,500 Hz |
| Transform size | 256 samples |
| Subcarrier spacing | 46.875 Hz |
| Active data subcarriers | -4 through -1 and +1 through +4 |
| Active-carrier span | 375 Hz center-to-center |
| Cyclic prefix | 64 samples, 5.333 ms |
| Total OFDM block | 320 samples, 26.667 ms |
| Training | Two repeated deterministic OFDM blocks |
| Payload constellation | BPSK initially; QPSK remains available for research |
| FEC | Rate-1/2, constraint-length-7 convolutional code |
| Interleaver | Deterministic ragged block, 8 columns |
| Peak output | Normalized to 0.78 full scale |

The current waveform remains below the project's approximately 1 kHz occupied
bandwidth ceiling under the deterministic 99%-power regression measurement.
The active carriers are intentionally conservative to leave room for OFDM
sidelobes and future windowing.

## Frame construction

The transmitter applies the existing Aurora framing, CRC, scrambling, FEC, and
interleaving pipeline. The resulting BPSK values are filled across the eight
active subcarriers. A final partial OFDM block is zero padded.

Two identical training blocks precede the payload. They provide bounded frame
acquisition, residual carrier-offset measurement, and a complex channel gain
estimate for each active subcarrier. The receiver removes the cyclic prefix,
performs an FFT, equalizes each carrier independently, and returns constellation
values to the existing soft decoder.

## Unresolved protocol work

Aurora does not yet transmit a mode identifier, payload geometry, constellation
selection, or interleaver geometry. The receiver currently knows the expected
payload length during development tests. Before operational use, Aurora still
requires a robust bootstrap header, unknown-length framing, timing-drift
tracking, pilot strategy, transmitter-linearity limits, and controlled HF radio
validation.
