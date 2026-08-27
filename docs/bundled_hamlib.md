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
