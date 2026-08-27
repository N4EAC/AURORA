# Aurora native transport and AX.25 separation

Aurora chat uses a native variable-length transport. It is not encapsulated in
AX.25 and does not reserve or transmit zero padding for a maximum-size message.

The protected bootstrap preceding a payload identifies protocol version, frame
type, occupied bandwidth, BPSK constellation, convolutional rate-1/2 FEC,
interleaver columns, exact protected payload byte/symbol counts, and a 32-bit
frame identifier.

Native chat version 3 contains compact source/destination callsigns, the frame
identifier, optional operator name, text length, and only the UTF-8 bytes entered
by the operator. It can also carry a contact identifier, Reply-To dial frequency,
bounded reply window, and the `BTY` or `EOC` control. Version 2 native chat
remains decodable. AX.25 remains a distinct payload type for station data:
callsign, optional operator name, grid, GPS position, altitude, and comment.
Location transmission remains operator-controlled and is not repeated in every
chat message. The Station ID tab provides an explicit SEND STATION DATA action;
Aurora never silently attaches location to SEND.

Reception reports are another native payload type. They identify the reporter
and earlier frame ID and carry SNR, frequency offset, timing offset, and FEC
corrections using compact fixed-point fields. SNR describes a previously
received frame; a transmitter cannot measure its own outgoing signal's SNR.

## Canned-message tokens

Templates are expanded immediately before native chat encoding:

- `<NAME>` uses the saved operator name;
- `<CALL>` uses the saved station callsign; and
- `<TNAME>` uses the selected other station's operator name;
- `<TCALL>` uses the selected other station's callsign;
- `<SPLT>` uses the armed or accepted Reply Channel frequency; and
- `<TIME>` uses current UTC time formatted as `HH:MM UTC`.

`<BTY>` and `<EOC>` are directives: Aurora removes them from displayed chat
text and sets native-transport control bits. They are mutually exclusive. All
other tokens are expanded text, so receivers do not need to understand their
syntax.

The `CQ Reply` canned message is `CQ CQ de <CALL> listening on <SPLT>`. The
expanded frequency is operator-readable text only; the protected Reply-To field
remains authoritative. A receiving operator must explicitly select the decoded
Reply action, after which Aurora creates the complementary route automatically:
the responder transmits on the advertised Reply frequency and continues to
receive on the caller's original frequency.

## Reply Channel operation

Reply Channel is an optional, connectionless operating aid. An outgoing native
message may advertise a different dial frequency within 10 kHz of its calling
frequency. For same-frequency operation, leave Reply Channel off and use simplex.
The receiving operator must explicitly accept the offer. Aurora then maintains
complementary receive and transmit dial frequencies using verified fake-split
tuning: PTT is off while tuning, the selected frequency is read back before PTT,
and the radio returns to the receive frequency immediately after transmission.

The contact identifier associates later `BTY` and `EOC` controls with the
selected station. `BTY` indicates that the sender has finished its current turn;
it never triggers an automatic transmission. `EOC` is a courtesy indication
that the sender is leaving the Reply Channel arrangement.

There is deliberately no connected-mode handshake or persistent link. The
RETURN TO NORMAL control is always a local action and never waits for `BTY`,
`EOC`, or another received signal. It clears Reply Channel state immediately and,
when Hamlib is connected, restores the saved normal dial frequency and mode.
The bounded reply window defaults to 300 seconds and displays a live MM:SS
countdown. Matching contact traffic refreshes it; expiration performs the same
local return. A lost or undecodable signal therefore cannot leave the operator
trapped in split operation.

If the operator changes the radio dial directly during an active fake-split
arrangement, Hamlib reports only the radio's current VFO state; it does not
rewrite both Aurora route frequencies. Aurora therefore cancels the stale split,
adopts the newly reported dial frequency as simplex, and warns the operator that
the Reply Channel contact was interrupted.

## Decoded-station actions

Other Signals rows retain the decoded callsign and audio center. Their context
menu can retune the Hamlib-controlled radio dial so the signal moves to Aurora's
fixed 1,500 Hz audio center, or retune and prepare a directed native reply.
USB and LSB dial adjustments use opposite signs. Double-clicking a row performs
the prepare-contact action. Aurora never transmits automatically; the operator
must review and select SEND. Decoded Reply-To offers add a separate explicit
accept action.
