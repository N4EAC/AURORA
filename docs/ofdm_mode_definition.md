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
| Active data subcarriers | Profile dependent; symmetric around DC |
| Cyclic prefix | 64 samples, 5.333 ms |
| Total OFDM block | 320 samples, 26.667 ms |
| Training | Two repeated deterministic OFDM blocks |
| Payload constellation | BPSK |
| FEC | Rate-1/2, constraint-length-7 convolutional code |
| Interleaver | One row per profile's OFDM data block |
| Peak output | Normalized to 0.78 full scale |

## Adaptive bandwidth profiles

| Profile | Active carriers | Edge carrier | Aggregate BPSK rate | Use |
|---|---:|---:|---:|---|
| 500 Hz | 8 | +/-4 | 300 symbols/s | Weak, impaired, uncertain, or narrow channel |
| 2.3 kHz | 42 | +/-21 | 1,575 symbols/s | Moderate, adequately characterized channel |
| 2.8 kHz | 52 | +/-26 | 1,950 symbols/s | Clean, stable, high-confidence channel |

A 129-tap windowed-sinc baseband filter contains each transmitted profile.
Automated regressions measure 99%-power occupied bandwidth and require every
profile to remain within its declared ceiling.

Automatic selection considers SNR, interference, fading, multipath delay,
frequency stability, available audio passband, and measurement confidence. An
incomplete estimate or confidence below 0.70 selects 500 Hz. Operators may fix
a profile for controlled testing; such a selection disables automatic changes
and is shown in diagnostics.

## Frame construction

The transmitter applies the existing Aurora framing, CRC, scrambling, FEC, and
interleaving pipeline. The resulting BPSK values are filled across the active
subcarriers selected by the bandwidth profile. A final partial OFDM block is
zero padded.

Two identical training blocks precede the payload. They provide bounded frame
acquisition, residual carrier-offset measurement, and a complex channel gain
estimate for each active subcarrier. The receiver removes the cyclic prefix,
performs an FFT, equalizes each carrier independently, and returns constellation
values to the existing soft decoder.

Candidate thresholds are calibrated by occupied-bandwidth profile: 0.45 at
500 Hz, 0.40 at 2.3 kHz, and 0.35 at 2.8 kHz. Wider acoustic signals experience
more speaker, microphone, and room-response distortion. Acquisition only
creates a candidate; a received message is accepted and emitted only after FEC
decoding and CRC validation. A 100-seed matched noise-only screen produced a
maximum training metric below 0.14 for every profile.

## Unresolved protocol work

Aurora does not yet transmit a mode identifier, payload geometry, constellation
selection, or interleaver geometry. The receiver currently knows the expected
payload length during development tests. Before operational use, Aurora still
requires a robust bootstrap header, unknown-length framing, timing-drift
tracking, pilot strategy, transmitter-linearity limits, and controlled HF radio
validation.
