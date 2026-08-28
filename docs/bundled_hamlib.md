# Bundled Hamlib runtime

Aurora uses a private Hamlib `rigctld` process so operators do not need to
install Hamlib separately. The runtime is platform-specific and generated
under `runtime/hamlib/` from the official checksum-verified Hamlib 4.7.2
release.

Run `python tools/bootstrap_hamlib.py` when preparing a development workspace
or application package. Release packaging must run the bootstrap once for each
target platform and include that platform's runtime directory.

Aurora starts the private service only after the operator chooses a named radio
model, CAT device, baud rate, and Connect. It binds to localhost and stops with
Aurora. On Windows it runs as a background process without opening a command
window; diagnostics remain captured by Aurora. PTT Control defaults to enabled,
but SEND remains blocked until Hamlib
connects; PTT is keyed only for an explicit SEND action and is always released
after playback or an error. An external `rigctld` endpoint remains available
for advanced station setups.

After a CAT configuration connects successfully, Aurora records that success
with the saved model, device, baud rate, or external endpoint. On the next
launch it reconnects automatically and applies the saved dial frequency and
mode without requiring the Setup dialog. A failed configuration is not promoted
to the automatic-start path. Automatic CAT startup never keys PTT and never
initiates a transmission.

Aurora initializes the radio receive passband to 3,000 Hz once when CAT
connects. After that initialization, Aurora preserves the passband reported by
Hamlib. Changing Aurora's 500 Hz, 2.3 kHz, 2.8 kHz, or automatic TX occupied-
bandwidth profile never changes the radio filter, and Reply Channel frequency
routing does not change it either.

The remembered RX audio level applies 10–200% software gain to captured samples
before decoding and display. It does not operate the radio gain or the platform
audio mixer, so physical input clipping must still be corrected at the radio or
operating-system input control.

Aurora's saved TX audio drive control adjusts sound-device modulation level,
not RF power. Its user-facing 100% maps to Aurora's validated `0.55` internal
gain ceiling rather than full-scale normalized audio. Generated-waveform
diagnostics verify peak, RMS, crest factor,
clipping, and Aurora's audio-linearity limits. Hamlib does not provide a
portable ALC measurement, so the operator must observe the radio's ALC meter
during a test transmission and reduce drive for little or no ALC compression.
The Audio setup **TUNE / TEST TX** button sends a representative identified OFDM
frame through the same guarded CAT/PTT and audio-quality path as normal SEND.
It is unavailable without CAT, PTT Control, and a selected output device, and it
is blocked while Reply Channel routing is active.
