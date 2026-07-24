# Aurora performance targets

## Measurement convention

Aurora sensitivity figures use SNR measured in a 2,500 Hz reference bandwidth.
Every result must also identify its measurement domain, waveform, payload size,
channel profile, trial count, and confidence interval. Results using different
reference bandwidths or known timing must not be presented as equivalent.

Aurora does not claim equivalence to VARA or another modem whose sensitivity
methodology, payload, bandwidth, and channel conditions cannot be reproduced
from public technical information.

## Active development objectives

Aurora will investigate two operating objectives rather than forcing one mode
to cover every throughput and sensitivity requirement.

### Normal robust objective

- Intended sensitivity: approximately -18 to -20 dB
- Emphasis: useful interactive throughput under realistic HF impairments
- Current 31.25-symbol/s robust simulation mode remains a research baseline
- Final modulation, FEC, framing, and airtime are not yet frozen

### Deep robust objective

- AWGN research target: -24 dB
- Reference bandwidth: 2,500 Hz
- Reference payload: 20 bytes
- Desired total transmission time: 30 to 40 seconds or less
- Intended information rate: approximately 4 to 8 bit/s
- Initial realistic-HF target: -21 to -22 dB
- Unknown start time within the receiver search window
- Frequency uncertainty: at least +/-2 Hz
- Sample-clock error: at least +/-100 ppm
- CRC-confirmed delivery required

At -24 dB, ideal real-AWGN capacity in 2,500 Hz is approximately 14.3 bit/s.
Aurora therefore requires practical rate and coding margin below that limit.
The current 31.25-symbol/s, rate-1/2 BPSK selection can represent as much as
15.625 information bit/s before framing overhead and is not a credible final
Deep-mode configuration.

## Acceptance criteria under development

A future -24 dB capability claim should require all of the following:

- At least 90% CRC-confirmed delivery of the 20-byte reference payload in AWGN
- Separate acquisition, decoder, and CRC failure counts
- At least 1,000 signal-present trials near the claimed threshold
- Multiple deterministic seeds and documented confidence intervals
- Noise-only trials sufficient to state a meaningful false-decode bound
- Unknown timing, rather than a receiver given the exact frame start
- Frequency and sample-clock uncertainty included in the test
- Occupied bandwidth and complete on-air duration reported
- Repeated tests under documented fading, multipath, and impulsive interference

The number of noise-only trials required will be selected from the desired
false-decode upper bound. A handful of successful or noise-only trials is useful
for engineering diagnosis but cannot support a sensitivity claim.

## Status of -30 dB research

The `extreme_research` tools remain available because they produced useful work
on long-sequence acquisition, false-alarm diagnostics, and joint clock/carrier
hypotheses. A -30 dB payload capability is no longer an active Aurora product
requirement. Those experiments do not implement FEC, decode payloads, validate
CRC, or define an over-the-air protocol.

No production mode should adopt the provisional 7.8125-symbol/s waveforms or
ideal rate-1/8 budget solely because acquisition was observed in a small AWGN
study. Any reuse requires evaluation against the active -24 dB Deep objective.

## Deep payload feasibility implementation

The `deep_payload_research` experiment now provides a complete offline
20-byte payload path at 31.25 symbols/s. It compares the existing rate-1/2
convolutional code with provisional rate-1/4 repeated-bit constructions using
soft-likelihood combining and fixed 16- or 32-column interleaving.

This implementation exists to measure feasibility against the objectives above.
It does not freeze the FEC, framing, preamble, interleaver, or waveform and does
not define an over-the-air Aurora protocol. The repeated-bit construction is a
baseline for comparison with stronger purpose-designed low-rate codes.

The first locked K10 campaign delivered 897 of 1,000 unknown-timing AWGN
frames at -24 dB. This is 89.7%, with a 95% Wilson interval of approximately
87.66% to 91.43%, and therefore does not satisfy the 90% acceptance criterion.
Zero false decodes were observed in 1,000 noise-only trials, which provides only
a 0.383% upper confidence bound. Fading and multipath results were substantially
worse, so -24 dB remains a research target rather than an Aurora capability.

The revised fading experiment uses a confidence-qualified, CRC-validated
fallback instead of replacing primary soft decisions. In paired trials it
preserved AWGN delivery at 90 of 100, improved fading-only delivery from 31 of
100 to 43 of 100, and left multipath delivery unchanged at 17 of 40. Zero false
decodes occurred in 1,000 disjoint noise-only trials. The fallback remains
disabled by default because these modeled results do not establish a
real-channel capability.

Broader 12-frame screens found fallback gains primarily in faster or deeper
fading. Shallow fading and the moderate composite profile were unchanged;
severe composite conditions remained acquisition-limited. All four unknown
carrier/clock corners decoded in AWGN, while only two of four decoded when
reference-depth fading was added. Synchronization under severe combined
conditions is therefore a higher priority than further fallback threshold
tuning.

A subsequent time-diverse acquisition fallback combines the existing preamble
and pilots without adding airtime or occupied bandwidth. With an unknown
0/+75 ppm clock search and two-stage signal gating, it improved the established
severe-profile result from 0/12 to 3/12 while preserving AWGN delivery at
90/100. Zero false decodes occurred in an initial 100-trial noise screen. This
is a research result only; larger noise and severe-profile campaigns are
required.

With acquisition largely restored, an equal-airtime interleaver comparison
found 45/100 severe-profile delivery at 16 columns, versus 29/100 at 32 columns
and 24/100 at 64 columns. The 16-column candidate delivered 88/100 in the
established AWGN set versus 90/100 for 32 columns, so the apparent AWGN
difference requires a larger paired campaign. No mode geometry is changed by
this result.

Large paired campaigns refined the tradeoff. At -24 dB, 16 columns delivered
888/1,000 AWGN frames and 201/500 severe composite frames, while 32 columns
delivered 897/1,000 and 177/500 respectively. Lowering the CRC-fallback
equalizer confidence threshold to 0.5 improved the 16-column severe result to
221/500. Zero false decodes occurred in 1,000 acquisition-fallback noise
trials.

A new independently varying delayed-path model produced 71/100 delivery for
16 columns under moderate selective fading. Eight columns delivered 74/100 in
that profile and 14/100 under strong selective fading, versus 6/100 for
16 columns in the strong profile. No interleaver geometry is frozen; these
results motivate later fixed-mode or explicitly signaled adaptation.

Pilot geometry remains provisional. A 64/8 near-equal-overhead candidate did
not survive a 25-seed comparison. Doubling pilot length from 16 to 32 symbols
at the original 128-symbol cadence improved a 100-seed severe result from
35/100 to 56/100 and delivered 90/100 on the established AWGN seeds. The
candidate adds approximately 3.6 seconds, so it must be compared against other
uses of the same airtime before promotion.
### Time-diversity acceptance requirement

Repeated observations must be compared at equal total airtime and must include
per-observation phase, gain, and reliability normalization. Raw likelihood
summation is not acceptable: it passed the AWGN screen but failed the severe
composite screen at -24 dB. Any future time-diversity candidate must improve
CRC-confirmed delivery across both composite and selective-fading profiles
without increasing false decodes.
### Calibrated receiver requirements

Composite-channel tests that inject clock error must include a receiver search
grid that brackets the injected value. Time-diversity candidates must:

- retain bounded timing hypotheses rather than assuming independent acquisitions
  select the same peak;
- normalize per-observation likelihood scale and apply a measured reliability
  weight;
- require CRC-confirmed payload delivery;
- exceed the current 75.0% severe-composite and 51.7% strong-selective baselines
  at -24 dB; and
- complete a substantially larger noise-only campaign before acceptance.
### Multi-observation validation integrity

Signal and noise campaigns must exercise the same observation count, clock
grid, acquisition fallback, candidate search, equalization options, and CRC
arbitration. The corrected receiver currently delivers 39/40 severe-composite
and 26/40 strong-selective frames at -24 dB. These small results justify further
study but not a sensitivity or false-decode claim. Optimize or batch the
receiver before completing at least 10,000 matched-path noise trials.
