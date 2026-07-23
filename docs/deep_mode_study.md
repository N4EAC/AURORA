# Aurora Deep payload feasibility study

## Purpose

This offline experiment tests whether a complete 20-byte payload can fit the
active Deep objective. It adds payload modulation, synchronization, provisional
coding, soft decoding, interleaving, and CRC validation to the existing audio
channel simulator.

It is not an over-the-air protocol, interoperability specification, or
sensitivity claim. It opens no audio device and performs no CAT or PTT action.

## Provisional candidates

All candidates use 31.25-symbol/s BPSK, the existing 63-symbol acquisition
sequence, a 1,500 Hz audio carrier, root-raised-cosine pulse shaping, and the
existing constraint-length-7 convolutional encoder.

The study compares:

- rate-1/2 convolutional coding with a 16-column interleaver;
- experimental rate-1/4 coding made by transmitting each convolutional coded
  bit twice, followed by receiver soft-likelihood combining, with 16 columns;
- the same experimental rate-1/4 construction with 32 columns;
- a native experimental rate-1/4, constraint-length-7 code with four distinct
  parity outputs and 16- or 32-column interleaving.

The repeated-bit construction is deliberately simple. It provides a controlled
low-rate baseline but is not presumed to be the final Aurora FEC.

The native comparator uses provisional octal generators `171`, `133`, `165`,
and `117`. Its 64-state soft Viterbi decoder is terminated to the zero state.
The generator selection is experimental and has not been optimized or adopted
for an Aurora protocol.

For the fixed 20-byte reference payload, the provisional rate-1/4 waveform is
approximately 37.4 seconds including acquisition, pilots, leading silence, and
pulse-shaping overhead.

## Acquisition and carrier tracking

The receiver converts normalized preamble correlation into a
background-normalized coherent acquisition score. The default threshold is
3.0. This allows controlled study below the earlier fixed 0.70 correlation
threshold while CRC validation remains mandatory.

A fixed 16-symbol pilot group is inserted between each 128-symbol coded-data
block. The 984-symbol rate-1/4 payload therefore contains seven pilot groups,
adding 112 symbols or approximately 3.6 seconds. The receiver:

1. estimates coarse residual carrier from phase progression within all pilot
   groups;
2. removes that residual across the payload;
3. measures each pilot-group phase;
4. unwraps and interpolates the remaining phase correction; and
5. removes pilots before soft decoding.

The study runs identical seeded realizations with tracking disabled and enabled.
It reports acquisition score, pilot quality, acquisition failures,
carrier-tracking failures, decoder or CRC failures, and confirmed deliveries.
Pilot geometry is fixed only for this experiment and is not signaled.

## Measurement matrix

The default SNR points are -18, -20, -21, -22, -23, and -24 dB in a 2,500 Hz
reference bandwidth. Named profiles isolate AWGN, fading, multipath, clock
error, and impulsive noise, and also provide combined moderate and severe HF
simulations.

Carrier hypotheses cover at least +/-2 Hz. Clock hypotheses cover at least
+/-100 ppm. The receiver is not given the exact start sample.

Each result separates acquisition failures, decoder or CRC failures,
CRC-confirmed deliveries, and noise-only false decodes. Small development runs
are diagnostic only. A performance claim still requires the trial counts and
confidence requirements in `performance_targets.md`.

## Initial diagnostic

A one-seed AWGN diagnostic of the rate-1/4, 16-column candidate produced no
CRC-confirmed delivery at -18, -20, -22, or -24 dB. At -18 dB the receiver
acquired the waveform but the frame failed decoding or CRC validation. At the
three lower points, acquisition remained below the current threshold.

This result is intentionally recorded as a failed feasibility baseline. One
seed cannot establish a threshold, but it shows that repeated coded bits and
one preamble-based carrier estimate are insufficient. Likely next experiments
include improved acquisition scoring, carrier tracking or distributed pilots,
and a purpose-designed low-rate code.

After distributed tracking was added, the same rate-1/4, 16-column candidate
and seed delivered the payload at -18 and -20 dB in AWGN. It did not deliver at
-22 or -24 dB. Tracking-disabled failed at all four points. This is a useful
A/B diagnostic, not a sensitivity threshold: it uses one seed, no carrier or
clock uncertainty in that focused run, and no fading.

## Native rate-1/4 comparison

The native four-parity code and repeated-bit baseline have identical coded
length, pilot overhead, waveform duration, and information rate. This permits
the same seeded audio-channel conditions to be compared without an airtime
advantage.

An initial four-seed AWGN comparison with tracking enabled produced identical
results for both codes: one of four payloads decoded at -20 dB, and none decoded
at -22 or -24 dB. An additional eight-seed check at -18, -19, and -20 dB also
produced identical one-of-eight delivery at each point.

The native candidate therefore shows no measurable advantage and is not
recommended as Aurora's Deep FEC. The matching, strongly seed-dependent failure
pattern suggests that receiver phase reliability remains the dominant issue.
These small runs are diagnostic and do not establish a sensitivity threshold.

## K10 bounded-receiver validation

The leading provisional comparator now uses constraint length 10, a 512-state
soft Viterbi decoder, 32-column interleaving, and octal generators `1713`,
`1475`, `1267`, and `1137`. The terminated 20-byte waveform contains 996 coded
symbols and lasts approximately 37.73 seconds. A GF(2) common-divisor check
returns one, but the generator set has not been independently established as
optimum.

A bounded 64-step trellis search found free distance 24 for the provisional
K10 set, compared with 20 for the earlier K7 four-output comparator. This is an
independent implementation check, not proof of an optimum-distance profile or
a complete distance spectrum.

The bounded receiver rejects timing positions that cannot hold a complete
frame, suppresses overlapping acquisition peaks, searches a local 16-sample
timing neighborhood, coherently ranks preamble and pilot symbols, and submits
at most three soft-likelihood candidates to CRC-validated decoding.

Locked campaign results at -24 dB in a 2,500 Hz reference bandwidth:

- AWGN: 897 of 1,000 CRC-confirmed deliveries (89.7%);
- 95% Wilson delivery interval: 87.66% to 91.43%;
- acquisition: 1,000 of 1,000;
- noise-only: zero false decodes in 1,000 trials;
- 95% Wilson false-decode upper bound: 0.383%;
- discrete -2/0/+2 Hz and -100/0/+100 ppm check: 11 of 12;
- moderate HF profile: 16 of 20;
- severe HF profile: zero of 20;
- fading only: 3 of 12;
- multipath only: 6 of 12;
- impulsive interference only: 11 of 12.

The candidate narrowly misses the 90% AWGN point target and its confidence
interval does not establish 90% delivery. Fading and multipath are the dominant
remaining modeled weaknesses. These results reject a -24 dB capability claim.

The 1,000-signal campaign preceded the coherent-score noise gate. The later
1,000 noise-only campaign used a threshold of 5.0 after sampled signal scores
ranged from 7.9 to 10.5 and sampled noise scores from 2.2 to 4.25. A new
1,000-signal campaign with that gate is required before combining the signal
and false-decode findings into one locked receiver claim.

### Experimental fading-aware CRC fallback

An optional receiver path estimates complex channel gain and estimation
variance at the preamble and distributed pilots. It smooths adjacent estimates,
measures gain changes relative to expected pilot noise, and requires both a
0.60 minimum relative gain and a 1.0 variation-confidence threshold before
applying matched reliability weighting. Hard erasure remains disabled.

The equalized likelihoods never replace the primary receiver result. Aurora
tries the unchanged receiver first and evaluates an equalized fallback only
when research mode is enabled. A fallback is accepted only through the same
frame CRC and payload validation. This structure preserved all primary
receiver successes in the paired trials.

Paired 100-seed results at -24 dB:

- AWGN: 90 of 100 for both receivers, with zero fallback recoveries;
- fading only: 31 of 100 primary deliveries and 43 of 100 with fallback;
- multipath only: 17 of 40 for both receivers;
- noise only: zero false decodes in 1,000 disjoint trials.

The combined 1,000-trial zero-event Wilson upper bound is approximately 0.383%.
Research-mode runtime increased to approximately 2.05 to 2.36 seconds per AWGN
frame and 3.23 to 3.82 seconds per fading frame per worker. These results are
promising but do not establish an Aurora sensitivity or over-the-air
capability. The fallback remains disabled by default pending broader fading
models and physical-channel validation.

### Broader fading and offset screen

A follow-up deterministic screen varied fading depth and rate. Each entry used
12 paired frames at -24 dB:

- depth 0.35 at 0.5 and 2.0 cycles per frame: unchanged at 11/12 and 12/12;
- depth 0.65 at 0.5 cycles: unchanged at 7/12;
- depth 0.65 at 2.0 cycles: improved from 3/12 to 5/12;
- depth 0.80 at 0.5 cycles: improved from 1/12 to 2/12;
- depth 0.80 at 4.0 cycles: improved from 0/12 to 1/12.

Combined 12-frame screens improved from 5/12 to 6/12 with moderate
multipath and from 2/12 to 3/12 with impulsive interference. Severe multipath
was unchanged at 2/12 because nine frames failed acquisition. The existing
moderate composite profile remained 12/12, while the severe composite profile
remained 0/12 with all frames acquisition-limited.

All four unknown +/-2 Hz carrier and +/-100 ppm clock-error corners decoded in
AWGN while searching the complete three-by-three hypothesis grid. With
reference-depth fading, two of four corners decoded in both modes; the fallback
did not recover either failed frame. This small screen reinforces that the
fallback can repair some post-acquisition fading errors but does not address
the severe-profile synchronization limit.

### Time-diverse acquisition fallback

The first severe-channel acquisition experiment preserves the original
preamble-only receiver as the primary path. If that path fails its score or
CRC checks, an optional fallback noncoherently combines the existing preamble
and distributed pilots across the frame. The calibrated fallback requires a
coherent score of at least 1.0, a time-diversity score of at least 0.37, CRC
validation, and an unknown 0/+75 ppm clock search for the severe profile.

This reuses existing known symbols and adds no airtime or bandwidth. Twelve
severe signals scored 0.379 to 0.518 on the diversity statistic, while 30
sampled noise trials scored 0.211 to 0.359.

On the established severe-profile seeds, the original configuration delivered
0/12. Clock search plus a lower CRC-protected coherent gate delivered 2/12,
and time-diverse acquisition added one recovery for 3/12. Two successful
frames also used fading equalization. The fallback-only architecture preserved
AWGN delivery at 90/100, and an initial 100-trial noise screen produced zero
false decodes.

The diversity gate reduced noise-screen runtime by approximately 3.6 times
compared with an unqualified lower coherent gate. Severe research runs still
required approximately 6.2 to 8.4 seconds per frame per worker. The feature
remains disabled by default and does not support a capability claim.

### Severe-profile interleaver comparison

Once time-diverse acquisition reduced severe-profile acquisition failures to
3/100, interleaver geometry became the next controlled variable. All candidates
used the same K10 rate-1/4 code, 996 coded symbols, waveform, airtime, energy,
and bandwidth.

On 12 screening seeds, 16, 32, 64, and 128 columns delivered 4, 3, 4, and 2
frames respectively. The promoted 100-seed comparisons delivered:

- 16 columns: 45/100 severe and 88/100 AWGN;
- 32 columns: 29/100 severe and 90/100 AWGN;
- 64 columns: 24/100 severe.

The 16-column geometry substantially improves this severe fading model, but
its two-frame AWGN difference is unresolved at 100 trials. It produced zero
false decodes in an initial 100-trial noise screen. Sixteen columns are
therefore a provisional research candidate, not a new mode definition. A
larger paired AWGN campaign is required before changing the documented robust
mode geometry.

Normal execution took approximately 1.4 to 1.8 seconds per frame per worker.
An instrumented frame took 5.15 seconds and reached 28,182,286 bytes of traced
peak memory. A receive-only VB-Cable loopback at 12 kHz decoded successfully.
No physical radio interface was present, and no CAT, PTT, or RF transmission
was attempted.

Published rate-1/4 optimum-distance-profile work exists, but it does not
independently validate Aurora's provisional K10 generators:
https://ntrs.nasa.gov/citations/19770046212

## Running the experiment

The runner is intentionally a Python API while its runtime and receiver
behavior are being stabilized:

```python
from modem.deep_mode_study import DeepStudyConfig, run_deep_mode_study

result = run_deep_mode_study(DeepStudyConfig())
for point in result.points:
    print(point)
```

Use smaller seed, candidate, SNR, frequency, and clock selections for focused
engineering checks. The full default matrix is computationally expensive.
