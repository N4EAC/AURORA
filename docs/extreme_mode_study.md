# Aurora extreme-mode acquisition study

## Research status

This archived exploratory study compares acquisition candidates at -30 dB SNR
in a 2,500 Hz reference bandwidth. A -30 dB payload capability is no longer an
active Aurora product requirement. The current Deep-mode research target is
-24 dB as defined in `docs/performance_targets.md`. This study is not an
over-the-air protocol and does not encode or decode payload data.

The measurement domain is `extreme_research`. Results from this study must not
be combined with `audio_sim`, `symbol_awgn`, or `symbol_hf_sim` results.

## Capacity and ideal code budget

At -30 dB, ideal real-AWGN capacity in 2,500 Hz is approximately 3.605 bit/s.
The study carries an `IdealCodeBudget` of 1,024 coded bits and 128 information
bits. At 7.8125 coded BPSK symbols/s, that represents:

- Assumed code rate: 1/8
- Assumed information rate: 0.9765625 bit/s
- Information-bit Eb/N0: approximately +4.08 dB
- Coded payload duration: approximately 131.1 seconds

The ideal budget performs arithmetic only. There is no rate-1/8 encoder,
decoder, code construction, interleaver, CRC result, or payload-success result.
Every structured event records that the ideal code is not implemented and that
payload decoding was not attempted.

## Candidate waveforms

Both candidates use 12 kHz audio, 7.8125 symbols/s, a 1,500 Hz carrier, and a
127-symbol deterministic acquisition sequence lasting approximately 16.3
seconds.

### BPSK

- Root-raised-cosine pulse shaping
- 0.35 roll-off
- Four-symbol filter span for the research waveform
- Phase-invariant matched-sequence acquisition

### 4-GFSK

- Four tones spaced by 7.8125 Hz
- Continuous phase
- Gaussian-smoothed frequency transitions with provisional BT=0.5
- Phase-invariant continuous-waveform sequence acquisition

The 4-GFSK detector ignores an unknown constant carrier phase by using
correlation magnitude. It still matches the known continuous-phase acquisition
trajectory; it is not a completed noncoherent payload symbol detector.

## Acquisition method

The receiver searches unknown sample start and a configured frequency-offset
grid using FFT correlation. Absolute correlation selects coarse time,
normalized correlation selects the frequency hypothesis, and peak-to-median
ratio provides detection confidence. Three-point parabolic interpolation
reports a fractional-sample peak and local curvature. A flat peak is therefore
visible in diagnostics rather than being presented as precise timing recovery.

The study reports mean, 95th-percentile, and maximum absolute timing error. Its
provisional acquisition criterion is within 0.10 symbol (153.6 samples). This
is a coarse acquisition tolerance, not the timing accuracy required for payload
symbol decisions.

Clock tracking is currently a discrete acquisition search, not a continuous
tracking loop. Each ppm hypothesis resamples the cached acquisition template
and compensates for the corresponding shift of the 1,500 Hz passband carrier.
The study reports selected ppm, absolute ppm error, clock match count, and the
normalized-metric margin over the next-best clock hypothesis. If the injected
clock error is absent from the grid, it is reported as unresolved and complete
acquisition cannot pass.

A full preamble-duration trailing region is included so the median represents
an actual search background rather than partial overlap with the signal. The
current threshold of 5.0 rejected the deterministic noise-only acceptance
trials, but it is provisional and requires far more noise-only trials before it
can support a false-alarm claim. Signal trials and noise-only trials have
independent counts so false-alarm testing can be expanded separately.

## Safe execution

Run the default two-signal-seed, eight-noise-trial 4-GFSK study with:

```powershell
.\.venv\Scripts\python.exe -m modem.extreme_mode_study
```

The optional `--snr-db`, `--trials`, and `--noise-trials` arguments control the
research run. The command writes an ignored session debug log and does not
initialize Tkinter, sounddevice, CAT, PTT, serial transport, or radio hardware.

Use `--modulation bpsk`, `--modulation 4gfsk`, or `--modulation all` to select
candidates. Acquisition and false-alarm results include separate Wilson 95%
confidence intervals. Small intervals remain wide even when every trial passes.

Use `--clock-search-ppm` followed by one or more numeric hypotheses for a normal
study. Use `--ppm-sweep` to inject and search the standard grid `0`, `±20`,
`±50`, `±75`, and `±100 ppm`. The sweep remains acquisition-only and is
cancellable between trials and points.

## Deterministic HF profiles

The `--profile` option selects one fully logged real-audio channel profile:

| Profile | Non-AWGN impairments |
|---|---|
| AWGN reference | None |
| Moderate HF simulation | 0.35-sample displacement, 20 ppm clock error, 2 ms/0.20 multipath, 0.35-depth one-cycle fade, seeded impulses |
| Severe HF simulation | 0.75-sample displacement, 75 ppm clock error, 5 ms/0.45 multipath, 0.65-depth two-cycle fade, stronger seeded impulses |
| Fading only | 0.65-depth, two-cycle fade |
| Multipath only | 5 ms delay, 0.45 gain |
| Clock error only | 75 ppm |
| Impulsive noise only | Seeded impulses at probability 0.00005 and scale 5.0 |

AWGN at the configured reference-bandwidth SNR remains active in every profile.
Isolated profiles support attribution; the combined profiles must not be used to
infer which individual impairment caused a failure.

## Limitations

- Only acquisition is measured.
- Frequency search uses a small discrete grid.
- The false-alarm sample count is far too small for a sensitivity claim.
- HF impairments are deterministic simulations, not measured ionospheric data.
- No user data, framing, FEC, interleaving, or CRC is exercised.
- Successful acquisition would not establish decodability at -30 dB.
