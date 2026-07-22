# Aurora SNR conventions and weak-signal target

Aurora intends to provide a robust operating option capable of decoding signals
reported near -22 dB under real HF conditions. Every result must state its SNR
measurement convention; an unqualified SNR value is not sufficient.

## Reference-bandwidth SNR

Aurora simulation reports weak-signal SNR against a 2,500 Hz reference
bandwidth by default. This matches a commonly used voice-channel comparison
width and does not imply that Aurora occupies the entire reference bandwidth.

For reference-bandwidth SNR `SNR_ref`, reference bandwidth `B_ref`, and symbol
rate `R_s`, the symbol-energy ratio is:

```text
Es/N0 dB = SNR_ref dB + 10 log10(B_ref / R_s)
```

At 31.25 symbols/s, -22 dB in 2,500 Hz corresponds to approximately -3.0 dB
Es/N0. The difference is processing gain from the lower signaling rate. It is
not free sensitivity: lower rates increase transmission duration.

For a modulation carrying `k` coded bits per symbol:

```text
Eb(coded)/N0 dB = Es/N0 dB - 10 log10(k)
```

Information-bit energy must additionally account for code rate, framing
overhead, pilots, interleaving, and retransmission policy.

Aurora labels the implemented value **coded Eb/N0**. It must not be presented
as information-bit Eb/N0. For equal symbol rate and reference SNR, QPSK's coded
Eb/N0 is approximately 3.01 dB lower than BPSK because it carries two coded
bits per symbol.

## Required reporting

Tests should report:

- Reference bandwidth and SNR
- Symbol rate
- Es/N0 and coded-bit Eb/N0
- Modulation and FEC configuration
- Occupied bandwidth
- Frame and channel bit-error rates
- Net successfully delivered payload throughput
- Frame length and number of trials
- Confidence interval and random seeds
- Frequency, timing, fading, and interference impairments

## Current limitation

The present robustness sweep operates on symbols with AWGN. It does not yet
model pulse shaping, matched filtering, multipath, selective fading, impulsive
noise, oscillator phase noise, sample-clock error, or real audio hardware. A
successful -22 dB symbol test is therefore a design indicator, not proof of
over-the-air performance.

The UI and session log identify these measurements as `symbol_awgn`. Sweep-end
50%, 90%, and 95% frame-success thresholds are linearly interpolated only when
measured points bracket the requested percentage. Aurora reports an unavailable
threshold rather than extrapolating beyond the tested SNR range.

Optional controlled HF profiles are identified as `symbol_hf_sim`. They apply
deterministic symbol-domain approximations of amplitude fading, delayed-path
interference, impulsive noise, phase drift, and fractional-symbol timing error.
Every parameter is recorded in the session log. These profiles are useful for
relative regression testing, but they are not standardized propagation models
and remain distinct from waveform, audio-device, and over-the-air testing.

Fading profiles use a seeded random starting phase for every frame. This avoids
repeating a favorable or unfavorable fade at the same interleaver positions
while keeping complete runs reproducible. Session events record the policy as
`fading_phase_policy="seeded_random_per_frame"`; individual phase values are
not treated as receiver measurements.

The original **Impulsive noise only** profile retains independent single-symbol
events with `impulse_burst_symbols=1`. The separate **Impulsive bursts only**
profile uses seeded burst starts that expand across five adjacent symbols. Its
lower start probability keeps the average affected-symbol rate approximately
comparable while testing a concentrated error topology. Burst length and start
probability are recorded explicitly in every session event.

Attribution profiles reproduce one Severe HF simulation component at a time:
fading, delayed-path interference, impulsive noise, phase drift, or timing
offset. After each completed sweep, the session log emits a
`ROBUSTNESS_PROFILE_COMPARISON` event containing all thresholds collected for
that modulation during the current session. Comparisons are meaningful only
when profiles use equivalent sweep ranges, rates, frame counts, and seeds.

## Interleaver comparisons

Robustness sweeps may select the rollback baseline (`Off`) or the optional
16-column block interleaver. Valid A/B comparisons must use identical payloads,
channel profiles, SNR points, frame counts, symbol rates, reference bandwidths,
and random seeds. The selected geometry is recorded on every result. This
software metadata is not an over-the-air protocol signal; a future Aurora mode
must either fix the geometry or protect and signal it explicitly. Interleaving
adds block latency even though it does not add coded bits.

Aurora's final robust option will require independently designed framing,
synchronization, interleaving, FEC, low-rate modulation, and receiver
integration. HX modem and protocol algorithms are not part of this design.
