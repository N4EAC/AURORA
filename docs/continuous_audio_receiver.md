# Aurora continuous audio receiver

## Status

Aurora now includes a bounded fixed-geometry continuous audio receiver for
development testing. It is not an over-the-air framing protocol and does not
solve unknown payload length or mode negotiation.

## Current behavior

The receiver:

- accepts arbitrary mono audio blocks at the configured mode sample rate;
- retains a bounded rolling sample buffer;
- searches for a fixed expected payload-symbol geometry at unknown start times;
- performs matched-filter acquisition, soft FEC decoding, and CRC validation;
- emits only CRC-confirmed payload events;
- advances through multiple failed windows without unbounded memory growth;
- records failed-window, discontinuity, and dropped-sample counters; and
- clears partial state when the audio layer reports an input overflow or
  underflow;
- preserves samples after a decoded frame; and
- can emit multiple CRC-confirmed frames from one input block;
- applies a bounded single-phase-inversion search only after normal decoding
  fails; and
- accepts a repaired candidate only when its frame CRC passes.

DSP processing runs outside the sound-device callback. The callback only copies
immutable audio blocks and normalized stream-status events into a queue,
reducing the risk of callback overruns. Stream status and its associated block
retain callback order.

## Audio UI workflow

The operator selects a compatible audio input/output pair, enters the expected
test message, and starts continuous receive. Aurora derives the fixed test
geometry from that message. `SEND TO CONT RX` plays a matching frame through
the selected output while the input stream remains active.

Changing the message requires restarting continuous receive because unknown
length signaling has not been defined.

## Validation

Deterministic tests cover:

- arbitrary block boundaries;
- bounded noise buffers;
- explicit discontinuity recovery;
- PortAudio status normalization and propagation;
- two complete frames delivered in one input block;
- CRC-confirmed recovery of the published `A085` transient-failure WAV;
- a corrupted frame followed by a valid frame;
- invalid sample rates; and
- clean audio-device callback separation.

A real VB-CABLE test decoded `CRX` with a 0.999904 synchronization metric,
effectively zero frequency offset, and no failed windows, discontinuities, or
dropped samples. Offline regression of the recorded transient failure now
recovers `A085` with the bounded phase-inversion fallback. An initial 100-trial
matched continuous-receiver noise screen produced zero false decodes; this is
not large enough for an operational false-decode claim.

## Remaining work

- Define provisional length and mode identification only after receiver
  architecture stabilizes.
- Add bounded timing recovery for discontinuities that are not adequately
  represented by a single BPSK phase inversion.
- Run a larger matched noise-only campaign for the repair-enabled receiver.
- Validate with a known physical sound-device cable route.
- Repeat false-decode campaigns after any framing or acquisition change.
