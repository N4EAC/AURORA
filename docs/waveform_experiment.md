# Aurora offline waveform experiment

## Status

This is an offline, in-memory waveform experiment. It does not open an audio
device, key a transmitter, control a radio, or define an over-the-air protocol.
Its purpose is to connect Aurora's existing symbol-domain codec to real-valued
audio samples under repeatable test conditions.

## Provisional waveform

| Parameter | Experimental value |
|---|---|
| Modulation | BPSK |
| Symbol rate | 31.25 symbols/s |
| Audio sample rate | 12,000 samples/s |
| Samples per symbol | 384 |
| Audio carrier | 1,500 Hz |
| Pulse shape | Root-raised cosine |
| Roll-off | 0.35 |
| Filter span | 8 symbols |
| Acquisition sequence | Existing 63-symbol Aurora sequence |

The transmitter inserts the acquisition sequence, upsamples the BPSK symbols,
applies root-raised-cosine pulse shaping, and mixes the complex baseband signal
onto a real audio carrier. The offline receiver downconverts, applies the
matching filter, searches all integer sample phases for the acquisition
sequence, estimates residual carrier offset from the recovered preamble, and
returns normalized payload symbols.

Payload symbol count is currently supplied to the offline receiver. A future
over-the-air receiver will need a separately designed and validated framing or
length mechanism that is recoverable after acquisition.

## Bandwidth interpretation

The theoretical raised-cosine null-to-null bandwidth is approximately
`31.25 * (1 + 0.35) = 42.19 Hz`. Filter truncation and finite-frame effects
alter measured containment bandwidth, so tests calculate it from generated
audio rather than treating the theoretical number as a guarantee.

This robust waveform is intentionally much narrower than 1 kHz. The project's
approximately 1 kHz objective should currently be treated as a channel limit
or capacity reserved for future adaptive or parallel waveform research, not a
requirement to spread this BPSK signal artificially.

## Known limitations

- Waveform processing is batch-oriented, not streaming.
- Timing acquisition searches integer audio-sample phases.
- The payload length is known out of band by the test harness.
- No automatic gain control or interference rejection is implemented.
- No sound-card clock mismatch is modeled.
- No interoperability or regulatory emission claim is made.
