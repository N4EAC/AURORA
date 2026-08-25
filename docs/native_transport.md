# Aurora native transport and AX.25 separation

Aurora chat uses a native variable-length transport. It is not encapsulated in
AX.25 and does not reserve or transmit zero padding for a maximum-size message.

The protected bootstrap preceding a payload identifies protocol version, frame
type, occupied bandwidth, BPSK constellation, convolutional rate-1/2 FEC,
interleaver columns, exact protected payload byte/symbol counts, and a 32-bit
frame identifier.

Native chat contains compact source/destination callsigns, the frame identifier,
text length, and only the UTF-8 bytes entered by the operator. AX.25 remains a
distinct payload type for station data: callsign, optional grid, GPS position,
altitude, and comment. Location transmission remains operator-controlled and
is not repeated in every chat message. The Station ID tab provides an explicit
SEND STATION DATA action; Aurora never silently attaches location to SEND.

Reception reports are another native payload type. They identify the reporter
and earlier frame ID and carry SNR, frequency offset, timing offset, and FEC
corrections using compact fixed-point fields. SNR describes a previously
received frame; a transmitter cannot measure its own outgoing signal's SNR.

## Canned-message tokens

Templates are expanded immediately before native chat encoding:

- `<NAME>` uses the saved operator name;
- `<CALL>` uses the saved station callsign; and
- `<TIME>` uses current UTC time formatted as `HH:MM UTC`.

These are UI template tokens, not protocol flags. Receivers obtain ordinary
expanded text and do not need to understand token syntax.

## Decoded-station actions

Other Signals rows retain the decoded callsign and audio center. Their context
menu can tune the shared TX/RX center or tune and prepare a directed native
reply. Double-clicking a row performs the prepare-contact action. Aurora never
transmits automatically; the operator must review and select SEND. Later
exchange-state, acknowledgement, and signal-report actions can extend this
menu without changing the native chat format.
