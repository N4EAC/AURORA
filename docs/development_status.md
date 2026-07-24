# Aurora Development Status

Date: 2026-07-23

## Scope completed

Aurora now contains an offline Deep-mode research path for a fixed 20-byte
payload. The implementation includes:

- provisional constraint-length-10, rate-1/4 convolutional coding;
- 32-column fixed interleaving;
- 31.25-symbol/s BPSK audio waveform;
- acquisition preamble and distributed pilots;
- unknown timing, carrier, and clock search;
- 512-state soft Viterbi decoding and CRC validation;
- deterministic HF channel profiles and resumable validation campaigns;
- optional confidence-qualified, CRC-validated fading equalization fallback;
- runtime, memory, confidence-interval, and false-decode measurements.

This work is a feasibility implementation. It is not a frozen Aurora mode and
does not define or claim an over-the-air protocol.

## Files changed since the previous checkpoint

- `AGENTS.md`
- `README.md`
- `docs/deep_mode_study.md`
- `docs/performance_targets.md`
- `docs/development_status.md`
- `dsp/deep_codec.py`
- `dsp/deep_waveform.py`
- `modem/deep_mode_study.py`
- `modem/deep_validation.py`
- `tests/test_deep_codec.py`
- `tests/test_deep_mode_study.py`
- `tests/test_deep_validation.py`
- `tests/test_deep_waveform.py`

## Validation executed

The automated suite contains 147 passing tests. The Deep research campaigns
also exercised:

- 1,000 unknown-timing AWGN signal trials at -24 dB;
- 1,000 noise-only trials for the original locked receiver;
- a second 1,000 disjoint noise-only campaign for the fading fallback;
- unknown +/-2 Hz carrier offsets;
- unknown +/-100 ppm clock errors;
- moderate and severe composite HF profiles;
- isolated fading, multipath, and impulsive interference;
- multiple fading depths and rates;
- combined fading with multipath or impulses;
- runtime and traced memory of the 512-state decoder;
- receive-only 12 kHz virtual-audio loopback.

No CAT command, PTT action, RF transmission, or physical-radio test was
performed.

## Quantitative findings

The first locked K10 AWGN campaign delivered 897 of 1,000 frames at -24 dB.
The 89.7% point result and 87.66% to 91.43% Wilson interval do not establish
the 90% acceptance target.

The confidence-qualified fading fallback preserved paired AWGN delivery at
90/100 and improved isolated fading delivery from 31/100 to 43/100. It left
multipath delivery unchanged at 17/40. Zero false decodes were observed in
1,000 disjoint fallback noise trials, giving an approximately 0.383% Wilson
upper bound.

Broader screens found fallback gains mainly during faster or deeper fading.
The moderate composite profile delivered 12/12 in both modes. The severe
composite profile delivered 0/12 because every frame failed acquisition.
Severe fading plus multipath was also primarily acquisition-limited.

All four unknown carrier/clock corner combinations decoded in AWGN. When
reference-depth fading was added, two of four decoded in both modes.

## End-of-day conclusions

1. A -24 dB Aurora mode remains feasible but is not yet demonstrated.
2. The provisional K10 coding candidate is worth retaining as a comparator,
   not freezing as the final code.
3. CRC-validated equalization fallback is safer than replacing primary soft
   decisions and provides measurable fading gains.
4. Further equalizer-threshold tuning is not the highest-value task.
5. Bounded clock search and diversity acquisition substantially reduce severe
   synchronization failures; selective-fading channel estimation is now the
   dominant modeled weakness.
6. The current approximately 31.25 Hz symbol-rate waveform is comfortably
   inside 1 kHz, but future acquisition experiments may evaluate narrower or
   wider occupied bandwidth when processing gain, time diversity, or frequency
   diversity justify it.
7. Mode parameters, framing, pilot geometry, bandwidth, and FEC remain
   provisional; there is no over-the-air Aurora protocol claim.

## Prioritized next steps

1. Improve pilot-derived channel estimation under strong selective fading.
2. Compare estimator candidates at equal airtime on paired severe and selective
   channel seeds.
3. Run at least 10,000 noise-only trials for any promoted receiver path.
4. Measure the added clock-search and candidate-combination runtime.
5. Revisit pilot spacing only if estimation remains limited by channel
   variation between pilot groups.
6. Validate through real sound hardware and a controlled radio channel before
   enabling research receiver paths or making sensitivity claims.

## Post-checkpoint acquisition experiment

The first prioritized synchronization experiment retained the original
receiver and added a fallback that combines the existing preamble and pilots
noncoherently across time. It adds no waveform overhead or bandwidth.

On the established severe-profile seeds, adding unknown 0/+75 ppm clock search,
a 1.0 coherent fallback gate, and a 0.37 diversity gate improved delivery from
0/12 to 3/12. The primary AWGN result remained 90/100. An initial 100-trial
noise screen produced zero false decodes. The result identifies clock search,
time-separated acquisition evidence, and CRC-arbitrated fallback as a useful
direction, but the severe sample remains small and processing cost is high.

The following 100-seed campaign confirmed 29/100 severe-profile delivery for
the acquisition fallback, compared with 0/100 for the original receiver.
Interleaver-only comparisons then delivered 45/100 at 16 columns, 29/100 at
32 columns, and 24/100 at 64 columns. The 16-column candidate delivered 88/100
on the established AWGN seeds, compared with 90/100 at 32 columns, and zero
false decodes in 100 initial noise trials. The 16-column geometry remains
provisional pending larger AWGN evidence.

The larger evidence is now available. Paired 1,000-seed AWGN campaigns
delivered 888 frames at 16 columns and 897 at 32 columns. Paired 500-seed
severe campaigns delivered 201 and 177 respectively. A lower, CRC-protected
equalizer confidence threshold improved the 16-column severe result to
221/500. The 16-column acquisition fallback also produced zero false decodes
in 1,000 noise-only trials.

The channel model now supports independently time-varying delayed-path gain.
Moderate selective fading delivered 71/100 at 16 columns and 74/100 at
8 columns. Strong selective fading delivered only 6/100 and 14/100
respectively. This confirms that selective cancellation and post-acquisition
payload recovery remain major weaknesses, and that no single tested
interleaver geometry dominates every modeled channel.

Pilot interval and length are now configurable in the research waveform. A
near-equal-overhead 64/8 geometry was rejected after its small-screen gain
reversed. A 128/32 candidate improved severe delivery from 35/100 to 56/100
and delivered 90/100 AWGN, but adds 112 pilot symbols or approximately
3.6 seconds. Equal-airtime comparison remains required.
## Equal-airtime observation research

- Added a validation-only `soft_observation_count` control; its default remains
  one and no production mode definition changed.
- Confirmed clean two-observation decoding and 20/20 delivery in AWGN at
  -24 dB.
- Rejected naïve likelihood summation for the severe composite channel after
  0/20 payload delivery with both strict and permissive acquisition thresholds.
- Next priority: improve preamble/pilot acquisition and obtain reliability-
  normalized channel tracking before reconsidering time diversity.
## Acquisition and time-diversity calibration

- Corrected diversity-search ranking to use normalized known-symbol agreement
  instead of unnormalized coherent amplitude.
- Identified an invalid validation setup: +75 ppm clock error was being tested
  against a receiver grid containing only 0 ppm.
- Added candidate-aware, RMS-normalized soft combining for validation-only
  repeated observations.
- Achieved 45/60 severe-composite and 31/60 strong-selective deliveries at
  -24 dB with two equal-airtime observations and bounded clock search.
- Observed 0/300 noise-only false decodes; this screen is useful but too small
  for a production false-decode claim.
- Production mode parameters and protocol status remain unchanged.
## Equalized multi-observation candidates

- Corrected the time-diversity path to include CRC-arbitrated equalized
  hypotheses when fading equalization is enabled.
- Improved paired 12-seed delivery from 6 to 10 severe-composite frames and
  from 6 to 8 strong-selective frames.
- A promoted 40-seed campaign delivered 39 severe-composite and 26
  strong-selective frames.
- Corrected noise validation so it uses the configured observation count and
  the same decoder as signal trials.
- Measured approximately 20.4 seconds per two-observation noise trial with the
  seven-point clock grid. The required 10,000-trial campaign remains pending
  because the current implementation would require about 56.7 serial hours.
