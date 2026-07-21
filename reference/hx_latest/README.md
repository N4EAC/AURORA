# HX LAB v0.5.6

Supported modes remain **HX-F**, **HX-N**, and **AUTO**. This maintenance build adds a single-owner RX monitor, duplicate-frame suppression, and progressive best-effort text display. Missing or unreliable text regions are shown as `(...)`, and an incomplete message remains visible as unverified if final CRC fails. Protocol/control traffic still requires a completely valid CRC.

The DECODER OUTPUT text is gray, and the former Recommended Mode area is now a CAT-ready frequency placeholder: `---.---.---`.

# HX LAB Windows v0.4.9 - File TX queue fix

HX - Hyper eXchange adaptive digital communications for amateur radio.

This test build keeps the v0.4.5 file-transfer session guard and adds small UI safety changes:

- Operator Profile has one OK button instead of Cancel/Save.
- To: defaults to ALL when the program opens.
- To: resets to ALL after disconnect/session clear.
- Removing or clearing heard stations resets To: to ALL when appropriate.
- A newly established session no longer automatically changes To: to the peer.

Test focus:
1. Open the app and confirm To: starts as ALL.
2. Open Operator Profile and confirm there is only OK.
3. Connect/disconnect and confirm To: returns to ALL.
4. Confirm file transfer resume still requires manual user action after reconnect.


## v0.4.9 testing changes

- Manual text queued during an outbound file transfer remains held until the file transfer ends.
- File protocol ACK/NACK traffic retains priority between chunks.
- Corrected TX completion cleanup to use the sender-side `peer`.
- Corrected RX completion cleanup to use the receive-side `call`.

- Fixed file-transfer stall when a manual chat message is deferred during FILE_OFFER or chunk TX.
- Deferred manual messages no longer count as blocking protocol traffic.


### v0.4.11 testing notes
Manual text queued during outbound file transfer displays an orange notice. The Operating menu can open or delete the expanded traffic/file debug log. Press Enter in the Operator Profile dialog to save and close it. Keep-alive timing remains five attempts followed by a 60-second disconnect warning.

### v0.4.12 testing notes
During file sending or receiving on Windows, HX requests that Windows keep both the system and display awake. The request is released when the transfer completes, fails, is canceled, the session closes, or HX exits. Test with the normal screensaver/display timeout enabled and confirm the debug log contains `POWER Windows awake mode enabled` at transfer start and `released` after transfer ends.

### v0.4.13 testing notes
- Test receiver CANCEL while a chunk is on the air. The receiver should immediately show cancellation pending, send FILE_CANCEL after RX completes, and send no ACK for later chunks.
- The sender should show that the remote callsign cancelled the transfer, not that the session changed.
- Leave an incoming file-offer dialog unanswered. It should count down from 45 seconds, close, and send FILE_REJECT before the sender's 180-second offer timeout.

## HX-specific channel detection (v0.4.15)

HX LAB continuously monitors the selected RX device, but audio energy alone no longer blocks transmission. The application now requires correlation with the known coded HX pilot before entering the HX busy/receive state. Non-HX signals may move the RX meter and display SIGNAL, but SEND and protocol traffic remain available unless an HX preamble is confirmed.

For repeatable testing, play recorded HF WAV files from Audacity into the virtual audio cable selected as HX RX input. A WAV containing no HX should never place HX into a persistent busy state. Enable RX debug logging to record pilot-correlation scores and confirmation events.

### v0.4.17 receiver behavior
A valid HX frame no longer requires silence after the transmission. Once the HX pilot is confirmed, the receiver attempts decoding as samples arrive. When the frame length and CRC validate, the message is delivered immediately and monitoring resumes even if band noise continues.

### v0.4.17 receiver-state correction
This build corrects a v0.4.16 regression that could leave RX displayed as DECODING. It does not change the HX over-the-air format or file-transfer protocol.


### v0.4.18 RX decoder diagnostics

- Adds detailed RX state transitions, pilot confirmation, buffer growth, decode-attempt results, burst termination reasons, and cleanup outcomes to the traffic/file debug log.
- Adds a conservative 180-second decoder watchdog so a damaged candidate cannot remain latched forever.
- Does not change the HX protocol, pilot threshold, file-transfer layer, or modulation.


### v0.4.21 Locked pilot/header alignment

- Locks each detected HX pilot to its absolute sample position before header decoding.
- Prevents static and prior frames from shifting HX-N/HX-R header alignment.
- Rejects a candidate if its complete header is present but CRC never validates, then resumes pilot search.

### v0.4.20 Rolling pilot alignment

The receiver now searches for each new HX pilot/header within a bounded rolling audio window. This allows continuous audio such as static → HX-F → static → HX-N → static → HX-R to be decoded without old background audio preventing later modes from synchronizing.

### v0.4.19 Exact frame-length RX
- Replaces repeated full-decoder attempts during live capture with a lightweight fixed-header probe.
- Uses the validated HX header payload length to calculate the exact expected end of the frame.
- Decodes once when the complete frame is present and returns immediately to monitoring.
- Header CRC failures no longer trigger an endless retry loop on the same growing capture.
- Keeps v0.4.18 RX diagnostics for validation.

### v0.4.22 Bounded timing recovery

For long HX-N and HX-R frames, a very small audio sample-clock mismatch can accumulate enough timing error to produce a payload CRC failure even when the pilot and header decode correctly. v0.4.22 keeps the locked-pilot receive path and, only after a payload CRC failure, tries a small bounded resampling search around nominal timing. Frames are accepted only when the standard CRC validates.

### v0.4.23 UI and diagnostics refinement

The CRC indicator now reports only the final outcome of a confirmed HX frame. Ordinary static, Morse, voice, or other non-HX bursts do not produce a red CRC MISS. The status bar separately identifies TX preference and the last decoded RX mode. Beacon history is displayed as `[BEACON] CALLSIGN GRID=...` while preserving the existing over-the-air beacon text for compatibility.



### v0.4.26 soft-decision RX and real-time decoder output

HX-N and HX-R now combine the signed confidence of their repeated symbols before making a bit decision. This improves resistance to weak or uneven interference without changing the transmitted HX protocol. A compact green-on-black decoder panel below the frame counters shows pilot lock, header validation, decode progress, timing recovery, and CRC outcomes in real time.

### v0.4.25 exact validated frame bounds

The live receiver now passes the exact frame interval established by the CRC-valid header directly to the final decoder. Long HX-R frames are no longer padded by one symbol at each end, and the decoder does not re-search around the already validated pilot. This prevents strong overlapping speech outside or near the frame boundary from turning a valid header into a false header CRC failure.

### v0.4.24 locked final-frame decode
The full-frame decoder now uses the already validated pilot/header location instead of searching the entire long capture again. This specifically protects HX-N and HX-R from false re-alignment caused by strong SSB voice peaks later in the frame.

### v0.5.2 HX-R carrier tracking
The HX-R receiver now tracks slow phase rotation independently on all three carriers. This addresses long-frame payload CRC failures caused by small sample-clock differences in Windows audio and virtual-cable paths.

## v0.5.4.2 progressive RX update

Operator text is placed immediately after a compact five-byte application prefix, allowing genuine progressive display. The provisional line uses the same style and color as verified RX text. Protocol actions still require a valid final CRC.


## v0.5.4.3 full-frame RX presentation

- Removed progressive/provisional decoded-text presentation.
- Received operator text is displayed only after the complete frame passes CRC.
- HX-F and HX-N modulation, framing, FEC, and final decoding are unchanged.
- The gray DECODER OUTPUT panel and CAT-ready frequency placeholder remain unchanged.


## v0.5.5 UTC and UI cleanup

- Removed the RX Detect line below the frequency display.
- Removed the Current Mode heading/readout from the left panel.
- Reduced the frequency placeholder font by one point.
- Message history timestamps no longer include RX or TX text; direction remains identifiable by message color.
- All displayed and logged clock times use UTC in fixed 24-hour format, without adding a UTC suffix.
- RX audio meter keeps its existing level-dependent colors; TX audio level is always red.
- Last Heard “Last” values now show dynamic age such as `now`, `18s`, `4m`, `2h`, or `3d`.
- HX-F and HX-N modem behavior is unchanged.


## v0.5.6 file-transfer arbitration

The sender announces remote acceptance or rejection by voice. While an outbound file transfer is active, all non-file transmissions are deferred until the transfer ends, preventing profile requests or other queued session traffic from colliding with FILE_ACK responses.

### Debug levels and window state
HX defaults to **Normal** event logging. **Verbose** adds protocol and session detail, while **Developer** includes low-level modem diagnostics. The selected level, window geometry, and maximized state are restored at the next launch.


## Version 0.6.1

Outbound file cancellation is now arbitrated with the active chunk/ACK exchange. FILE_CANCEL waits for a safe HX transmit window instead of colliding with the peer's ACK.


## Version 0.6.8

- TX permission now depends only on actual TX activity, confirmed HX reception, and turnaround guard; the continuously running RX monitor is never treated as channel busy.
- FILE_REJECT is always sent from a background worker so queued turnaround callbacks cannot be blocked by the Tk main thread.
- Stale same-file receive state from a previous cancelled or timed-out resume attempt is cleared when a fresh offer arrives from the same station.

### Post-transfer arbitration

- Deferred operator traffic is now held on both the file-sender and file-receiver sides.
- The original file sender receives the first post-transfer transmit window.
- The file receiver waits for the later window and still obeys live RX/TX and turnaround arbitration.
- Simultaneous deferred profile requests therefore sequence instead of transmitting together.


### v0.6.8
Post-transfer deferred traffic is coordinated before keepalives resume. The received-file folder prompt is non-blocking and auto-closes after five seconds.

### v0.7.0

Post-transfer deferred traffic now uses an explicit sender/receiver token handoff rather than independent local delays. This prevents both stations from transmitting queued profile requests or text messages at the same time after a file transfer.

## v0.7.4 file-transfer operator lock

During an incoming or outgoing file transfer, HX temporarily disables ordinary text transmission, profile requests, SNR requests, and service-tag selection. The editor shows a waiting notice and is restored when the transfer ends. File cancellation remains available. Profile and peer SNR metadata are exchanged automatically in FILE_OFFER and FILE_ACCEPT before the first chunk. Post-transfer drain control frames are no longer transmitted.


## v0.7.5 CRC recovery

An unrecoverable HX header or payload CRC failure now clears the locked candidate immediately, returns the modem to Listening even when continuous SSB or other audio remains present, and applies a short 600 ms reacquisition cooldown. The red CRC ERROR indication remains available as operator feedback.

## Optional CAT / PTT Preview

Open **Operating > CAT / PTT Manager** to configure radio control. CAT is disabled by default; with CAT disabled, HX operates exactly as before.

The first supported radio is the **Yaesu FT-710**. Select its Enhanced COM port for CAT frequency/mode control, choose the matching radio baud rate, and press **CONNECT**. Available PTT methods are VOX, CAT, RTS, and DTR.

For RTS or DTR keying, confirm the FT-710 radio menu is configured for the selected hardware PTT line. Avoid assigning the same line to incompatible flow-control or keying functions.

## Version 0.8.3 CAT Preview

When CAT is enabled and a COM port profile is saved, HX makes one automatic CAT connection attempt two seconds after startup. If the radio is unavailable, HX continues normally and the operator may connect manually later.

The optional CAT/PTT subsystem now also controls PTT for the continuous 1 kHz tune function. Normal text, beacon, modem, session, and file-transfer behavior is unchanged.


### CAT startup and shutdown behavior
A saved CAT COM-port profile automatically enables CAT on the next launch. If the radio is powered off or disconnected before HX closes, expected serial transport details are shown only at the Developer debug level.


## CAT radio support in v0.8.4
- Yaesu FT-710
- Kenwood TS-2000

The TS-2000 driver reads VFO-A frequency, operating mode, and transmit/receive status. CAT PTT uses the Kenwood `TX;` and `RX;` commands.
