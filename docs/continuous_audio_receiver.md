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
- clears partial state when the audio layer explicitly reports a discontinuity.

DSP processing runs outside the sound-device callback. The callback only copies
immutable audio blocks into a queue, reducing the risk of callback overruns.

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
- a corrupted frame followed by a valid frame;
- invalid sample rates; and
- clean audio-device callback separation.

A real VB-CABLE test decoded `CRX` with a 0.999904 synchronization metric,
effectively zero frequency offset, and no failed windows, discontinuities, or
dropped samples.

## Remaining work

- Define provisional length and mode identification only after receiver
  architecture stabilizes.
- Detect actual callback overflow/underflow status and mark discontinuities.
- Preserve unconsumed samples after a successful frame so multiple frames in
  one block can be emitted.
- Add mid-frame timing tracking and recovery for dropped or duplicated samples.
- Validate with a known physical sound-device cable route.
- Repeat false-decode campaigns after any framing or acquisition change.

