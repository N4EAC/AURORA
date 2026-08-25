# AX.25 transport over Aurora

## Scope

Aurora provides AX.25 as a parallel logical transport alongside native text
payloads. Both transports use the same Aurora framing, FEC, adaptive OFDM
waveform, audio path, and future radio interface. AX.25 does not create a
second simultaneous RF signal.

This implementation follows the TAPR AX.25 version 2.2 address and
unnumbered-information frame structure. It supports destination, source, up to
eight repeater addresses, UI control `0x03`, a PID, an information field of up
to 256 bytes, and the reflected CRC-16/X-25 frame check sequence.

Aurora carries the AX.25 frame as an octet payload, so HDLC opening/closing
flags and on-wire bit stuffing are not included. Those functions belong to a
traditional synchronous AX.25 physical link and would be redundant inside an
already framed Aurora transmission.

## Multiplexing

Aurora frame flag bit `0x01` identifies an AX.25 payload. Flag-clear frames
remain native Aurora data. This lets a receiver route both payload types after
the common Aurora CRC and FEC checks.

The current AX.25 path uses UI frames with PID `0xF0` (no layer-3 protocol).
Connected-mode AX.25, acknowledgment windows, KISS, APRS formatting, and
digipeater behavior are outside the present scope.

## Station-data information field

Aurora defines a compact, versioned information field for station metadata:

| Type | Value |
|---:|---|
| 1 | Maidenhead grid locator, 4, 6, or 8 ASCII characters |
| 2 | Latitude and longitude as signed integer microdegrees |
| 3 | Altitude as signed integer centimeters |
| 4 | UTF-8 operator comment, at most 80 bytes |

The AX.25 source address carries the station callsign and optional SSID. The
default destination is `AURORA`. The information field begins with `AU`, then
version byte `1`, followed by type-length-value fields.

GPS values entered in the UI are shown locally but are not written verbatim to
the structured session log. Operators remain responsible for deciding whether
location data is appropriate to transmit. CAT, PTT, and RF remain inactive.

## Validation boundary

The implementation validates AX.25 FCS independently of the outer Aurora CRC.
Automated tests cover the standard CRC check value, callsign and SSID encoding,
UI-frame corruption rejection, station-data validation, coexistence with native
Aurora frames, and a complete station record through OFDM audio.
