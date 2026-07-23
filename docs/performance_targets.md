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
