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
5. Synchronization and acquisition under severe combined channels are the
   dominant modeled failures.
6. The current approximately 31.25 Hz symbol-rate waveform is comfortably
   inside 1 kHz, but future acquisition experiments may evaluate narrower or
   wider occupied bandwidth when processing gain, time diversity, or frequency
   diversity justify it.
7. Mode parameters, framing, pilot geometry, bandwidth, and FEC remain
   provisional; there is no over-the-air Aurora protocol claim.

## Prioritized next steps

1. Record acquisition diagnostics for rejected severe-profile hypotheses:
   preamble score, timing rank, energy normalization, carrier hypothesis, and
   rejection reason.
2. Compare longer and repeated acquisition structures with time-separated
   correlation, without changing payload coding.
3. Test noncoherent or diversity-assisted acquisition when deep fades erase a
   single preamble interval.
4. Evaluate acquisition bandwidth and symbol-rate alternatives under identical
   airtime and energy accounting.
5. Rerun large paired AWGN, fading, severe-profile, and noise-only campaigns
   for any promoted acquisition design.
6. Validate through real sound hardware and a controlled radio channel before
   enabling the fading fallback or making sensitivity claims.

