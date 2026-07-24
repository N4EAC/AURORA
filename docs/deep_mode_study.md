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

### Large paired geometry campaigns

The paired AWGN campaign was extended to 1,000 identical seeds:

- 16 columns: 888/1,000, with a 95% Wilson interval of 86.69% to 90.61%;
- 32 columns: 897/1,000, with a 95% Wilson interval of 87.66% to 91.43%;
- acquisition failures: zero for both.

Neither geometry establishes the 90% AWGN target. The corresponding 500-seed
severe composite campaign delivered 201/500 at 16 columns and 177/500 at
32 columns. Both had seven acquisition failures. The 16-column severe result
has a 95% Wilson interval of 35.99% to 44.56%, compared with 31.33% to 39.69%
for 32 columns.

Lowering the equalizer variation-confidence threshold from 1.0 to 0.5, while
retaining CRC-only fallback acceptance, improved the 16-column severe result
from 201/500 to 221/500. Equalization-assisted recoveries increased from 67 to
87 without changing acquisition. The 0.5 threshold is now the validation
default when the otherwise disabled research equalizer is explicitly enabled.

The 16-column acquisition-fallback candidate produced zero false decodes in
1,000 noise-only trials, for an approximately 0.383% Wilson upper bound.

### Selective-fading channel extension

The offline channel can now apply independently time-varying gain to a delayed
path. This creates deterministic frequency-selective cancellation instead of
applying one common envelope to the entire waveform.

At -24 dB, the 16-column receiver delivered 71/100 on a moderate selective
profile. An 8-column candidate delivered 74/100 on the same seeds, but scored
44/100 versus 48/100 for 16 columns on the established severe composite set.
On a strong selective stress profile, 8 columns delivered 14/100 versus 6/100
for 16 columns. The stress result remains poor in absolute terms and shows that
the scalar pilot equalizer cannot reliably invert deep frequency-selective
nulls.

These results support keeping interleaver geometry provisional. If Aurora
eventually supports multiple geometries, the selection must be fixed by mode or
explicitly signaled; it must not be guessed from a failed decode.

### Pilot geometry study

Pilot interval and group length are now explicit research parameters. The
original 128-data/16-pilot geometry inserts 112 pilot symbols into the
996-symbol coded payload. Candidate screens included:

- 64/8: 120 pilot symbols;
- 256/32: 96 pilot symbols;
- 64/16: 240 pilot symbols;
- 128/32: 224 pilot symbols.

The nearly equal-overhead 64/8 candidate looked favorable in six trials but
reversed in a 25-seed comparison, delivering 8/25 versus 10/25 on severe
composite fading and 19/25 versus 21/25 on moderate selective fading. It was
rejected.

Doubling group length at the original cadence was more consistent. In 100
severe trials, 128/32 pilots delivered 56 frames versus 35 for 128/16, removed
the one acquisition failure, and increased equalization-assisted recoveries
from 14 to 25. On the established 100-seed AWGN set it delivered 90 frames,
versus 88 for the 16-column, 128/16 comparator.

The gain costs 112 additional pilot symbols, approximately 3.6 seconds at
31.25 symbols/s. It is not an equal-airtime improvement and remains
provisional until compared with using that time for additional coding,
repetition, or other diversity.

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
### Equal-airtime soft-observation screen

An offline screen compared one 15.625-symbol/s frame with two independently
impaired 31.25-symbol/s observations of the same frame. Both alternatives use
approximately 82.6 seconds of transmitted waveform. The 31.25-symbol/s
observations were aligned independently and their soft likelihoods were summed
before the K=10 rate-1/4 decoder.

The two-observation path decoded 20/20 AWGN trials at -24 dB, but decoded 0/20
trials in the severe composite profile. Reducing the coherent acquisition
threshold from 5.0 to 1.0 converted acquisition rejections into CRC failures
without recovering payloads. Direct likelihood summation is therefore rejected
as a mode candidate: independently tracked HF observations need phase,
reliability, and gain normalization before they can be combined safely.

The result also confirms that acquisition and channel tracking, rather than
additional unqualified energy alone, are the next research priority. This is an
offline feasibility result and does not define an over-the-air protocol.
### Calibrated acquisition and normalized time diversity

Impairment attribution found that a +75 ppm channel clock error produced 0/20
deliveries when the validation receiver was configured to search only 0 ppm.
Fading alone delivered 15/20, multipath alone 20/20, and impulsive interference
16/20. A bounded clock grid of -100, -75, -20, 0, 20, 75, and 100 ppm is
therefore required for the composite research profiles; this is receiver
calibration rather than additional coding gain.

The diversity receiver now retains up to three bounded timing candidates per
observation. When coherent acquisition fails, it uses normalized noncoherent
preamble-plus-pilot agreement. Before FEC, each candidate likelihood stream is
RMS-normalized and weighted by its bounded known-symbol agreement. The decoder
tests the small Cartesian set of timing hypotheses and accepts only a
CRC-confirmed payload.

At -24 dB, 32 pilot symbols per 128 data symbols, and the bounded clock grid:

- severe composite HF: 45/60 deliveries (75.0%), zero acquisition failures;
- strong selective fading: 31/60 deliveries (51.7%), one acquisition failure;
- noise only: 0/300 false decodes, with a 95% upper confidence bound of 1.264%.

The earlier raw likelihood-summation strategy remains rejected. Normalized,
candidate-aware combining is promising but provisional. Strong selective fading
and a larger noise-only campaign remain acceptance blockers. These results do
not define an over-the-air protocol.
### Equalized candidates in normalized time diversity

The multi-observation validation path previously combined baseline candidates
even when fading equalization was requested. It now retains CRC-arbitrated
equalized hypotheses alongside baseline hypotheses. Baseline candidates remain
available, and an equalized result is accepted only when the final frame CRC
and payload check succeed.

On identical 12-seed screens at -24 dB, severe-composite delivery improved from
6/12 to 10/12 and strong-selective delivery improved from 6/12 to 8/12. A
promoted independent 40-seed campaign delivered 39/40 severe-composite frames
and 26/40 strong-selective frames. Equalized hypotheses accounted for 12 and 5
of those successful deliveries respectively.

Noise-only validation was also corrected to generate the configured number of
independent observations and route them through the same multi-observation
decoder. A 10-trial runtime sample produced zero false decodes but required
approximately 204 seconds. At that measured rate, 10,000 trials would require
about 56.7 serial hours. The large false-decode campaign remains required and
must be batched or optimized; the small runtime sample is not statistical
evidence of safety.
