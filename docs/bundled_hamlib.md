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
Aurora. PTT Control defaults to enabled, but SEND remains blocked until Hamlib
connects; PTT is keyed only for an explicit SEND action and is always released
after playback or an error. An external `rigctld` endpoint remains available
for advanced station setups.
