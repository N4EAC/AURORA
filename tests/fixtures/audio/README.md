# Aurora audio validation fixtures

These WAV files preserve the most relevant evidence from the July 25, 2026
VB-CABLE reliability campaign. Both contain the same transmitted message,
`A085`, at 12,000 samples per second.

## `a085_transient_failure.wav`

The original campaign capture synchronized successfully with a 0.999904
preamble metric, but decoding failed the frame sync-word check. Offline
inspection found 190 hard symbol errors beginning near payload symbol 46,
consistent with a transient mid-frame audio discontinuity.

SHA-256:
`a8fa3fe6e2cd03c9e073c4e68d8197a6c3997af097225fc8fc46ede21d51b92c`

## `a085_successful_retry.wav`

The first exact retry decoded `A085` successfully. Five consecutive exact
retries passed, making this file a useful control capture for comparisons with
the transient failure.

SHA-256:
`cb64a464ef0bf802d1dd521f369d3d20c3be28332543bcc00597f8a32e86c99f`

## Scope

The captures used MME `CABLE Input` as Aurora's output and MME `CABLE Output`
as Aurora's input, with 75% application output gain. No CAT, PTT, RF, or radio
hardware was active.
