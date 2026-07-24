# Aurora

**Project ID:** AURORA-HF-MODEM-2026

Aurora is a new adaptive digital communications mode designed for reliable,
weak-signal operation under real-world HF propagation conditions.

## Project status

Aurora is in the initial development stage. The repository currently provides
the foundational project structure and a simulation-only operator interface.
The interface can exercise the symbol-domain codec locally and animate the
spectrum and waterfall from a synthetic test signal. It does not open audio or
radio hardware.

## Design goals

- Approximately 1 kHz occupied bandwidth
- Strong weak-signal performance and HF robustness
- Adaptive operation and efficient synchronization
- Forward error correction
- Clear diagnostics for synchronization, signal quality, offsets, CRC results,
  and FEC corrections
- A modular architecture suitable for long-term expansion

Aurora's active weak-signal research target is CRC-confirmed delivery of a
20-byte Deep-mode reference message at -24 dB SNR in a 2,500 Hz reference
bandwidth, with a desired total transmission time of 30 to 40 seconds or less.
The initial realistic-HF target is -21 to -22 dB. These are development
objectives, not current capability claims. See `docs/performance_targets.md`.

## Technology

- Python 3
- Tkinter for the desktop interface
- NumPy for numerical processing
- SciPy only where it provides a clear DSP advantage

## DSP core

The initial bit-level DSP core provides:

- Versioned binary framing with payload length and flags
- CRC-16/CCITT-FALSE integrity checking
- Additive bit scrambling for spectral whitening
- Rate-1/2 convolutional FEC with hard-decision Viterbi decoding
- Normalized BPSK and Gray-coded QPSK symbol mapping
- A composable payload-to-symbol and symbol-to-payload pipeline

The generic bit-level core remains independent of waveform filtering and
automatic gain control.

An experimental offline path now converts the robust-mode BPSK symbols into
12 kHz real-valued audio using root-raised-cosine pulse shaping and recovers
them with preamble acquisition, matched filtering, and residual carrier-offset
correction. This batch-only path uses in-memory buffers and does not open an
audio device or control a radio. See `docs/waveform_experiment.md`.

The offline robustness harness adds deterministic real-audio AWGN, timing
displacement, sample-clock error, multipath, fading, impulsive noise, and level
variation. Its results use the `audio_sim` domain so they remain distinct from
symbol-domain measurements. A small logged check can be run with
`.\.venv\Scripts\python.exe -m modem.audio_robustness`; it remains offline and
does not initialize audio or radio hardware.

An additional `extreme_research` study compares acquisition-only BPSK and
continuous-phase 4-GFSK candidates at 7.8125 symbols/s. It calculates a
theoretical rate-1/8 coding budget but deliberately provides no such encoder or
decoder and reports no payload success. Run it with
`.\.venv\Scripts\python.exe -m modem.extreme_mode_study`. See
`docs/extreme_mode_study.md` for assumptions and limitations.

The former -30 dB exploration is retained for acquisition research but is no
longer an active product requirement. It provides no payload or CRC result.

The extreme acquisition CLI supports deterministic AWGN, combined HF, fading,
multipath, clock-error, and impulsive-noise profiles. Signal and noise-only
trial counts are independent, cancellation preserves completed counts, and
Wilson intervals expose the uncertainty of small studies. These remain
acquisition-only simulations.

The extreme receiver can also compare discrete sample-clock hypotheses while
accounting for their induced passband carrier shift. A cancellable standard ppm
sweep reports selected clock error and explicitly fails complete acquisition
when the injected error is not represented by the search grid.

## Receiver

The initial receiver operates on complex baseband samples and provides:

- Normalized known-preamble acquisition and sync confidence
- Frequency-offset estimation from preamble phase slope
- Complex carrier-offset correction
- Interpolated Gardner symbol-timing recovery
- BPSK and QPSK soft log-likelihood demapping
- Soft-input Viterbi FEC decoding
- Sync, SNR, frequency-offset, and timing diagnostics

Complete audio-to-message reception still requires transmit waveform design,
pulse shaping, matched filtering, automatic gain control, and integration with
the real-time audio layer.

## Audio

Aurora provides a modular audio layer with:

- Immutable NumPy floating-point sample buffers
- Uncompressed 8-, 16-, 24-, and 32-bit PCM WAV import
- Signed 16-bit PCM WAV export
- Blocking or asynchronous buffered playback
- Input, output, and full-duplex real-time streams
- Audio device discovery and direction filtering

Real-time audio uses a 12 kHz, mono, 1,024-frame default configuration. These
values are centralized in `config/settings.py` and can be replaced as modem
waveform requirements evolve.

## Radio integration

The initial radio layer provides:

- Serial-port discovery and a thread-safe ASCII command transport
- Kenwood-style CAT frequency, mode, and PTT commands
- CAT, RTS, and DTR PTT methods with automatic release support
- SQLite contact records with UTC timestamps and operating details

Radio control is inactive at application startup. PTT is changed only through
an explicit API call, and the context-managed transmit API releases PTT when an
operation raises an exception.

## Spectrum and waterfall

Aurora includes a Hann-windowed FFT analyzer for real or complex samples, a
bounded waterfall history, and dark-themed Tkinter spectrum and waterfall
views. The views expose update APIs for future connection to live audio and
receiver processing. The current application starts them with an empty display
and does not open an audio stream automatically. Select **START SYNTHETIC
SIGNAL** to exercise the current displays without using audio hardware.

## Local operator test

The first operator iteration includes a BPSK/QPSK local codec test. Enter a
message and select **RUN LOCAL CODEC TEST** to pass it through Aurora framing,
scrambling, FEC, symbol mapping, soft decoding, and CRC validation. This is a
local software test only and does not generate an audio waveform or RF signal.

The channel test adds deterministic Clean, Moderate HF, Weak Signal, and Severe
presets. It can run one to 1,000 symbol-domain frames with injected AWGN and
carrier rotation, reporting frame success, CRC outcomes, pre-FEC channel bit
errors, recovered errors, and processing time. **RUN 100 FRAMES** provides a
repeatable threshold check. Frequency and SNR values in this test are injected,
not receiver estimates. Timing impairment is unavailable until Aurora has an
oversampled, pulse-shaped waveform.

Each application run creates a structured debug log in `logs/` named
`aurora_test_session_YYYYMMDD_HHMMSS_ffffff.log`. Test starts, results, errors,
injected conditions, frame statistics, bit-error counts, and timing information
are flushed immediately. Operator message contents are not recorded; only their
length is included. The latest session log can be reviewed after testing without
exporting data from the interface.

The **Channel Results** tab also provides a cancellable robustness sweep. Its
default range is -24 through +10 dB in a 2,500 Hz reference bandwidth, using
200 frames per point across four deterministic seeds at 31.25 symbols/s. It
reports Es/N0, BER, FER, net payload throughput, processing time, and a 95%
frame-success confidence interval. The measurement convention and the intended
-22 dB robust-mode target are defined in `docs/snr_conventions.md`.

Aurora's independent DSP pipeline includes a deterministic block interleaver
between convolutional FEC and symbol mapping. The documented robust simulation
mode selects BPSK at 31.25 symbols/s, rate-1/2 constraint-length-7 convolutional
FEC, and a fixed 16-column interleaver. The receiver applies the inverse
permutation before hard- or soft-input FEC decoding. The simulation UI retains
an explicit interleaver-off override for controlled A/B tests.

The selection is documented in `docs/mode_definition.md`. It is a development
definition for reproducible simulation and does not claim an over-the-air
protocol, signaling format, or interoperability specification.

## Project structure

```text
Aurora/
|-- audio/       Audio input and output
|-- config/      Central application settings
|-- docs/        Project documentation
|-- dsp/         Digital signal-processing algorithms
|-- gui/         Tkinter user interface
|-- logs/        Rotating application logs (created at runtime)
|-- modem/       Modem and protocol logic
|-- radio/       CAT, PTT, serial ports, and contact records
|-- tests/       Automated tests
|-- util/        Shared utilities and logging setup
|-- waterfall/   Waterfall and spectrum displays
|-- Aurora.sln   Visual Studio solution
`-- README.md    Project overview
```

## Development setup

Create a virtual environment if one does not already exist:

```powershell
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
python -m pip install -r requirements.txt
```

Run the current desktop shell with:

```powershell
.\.venv\Scripts\python.exe .\aurora.py
```

Aurora records startup, shutdown, and future operational messages in
`logs/aurora.log`. Log files rotate automatically to limit disk usage.

Run the automated tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Deep payload research

Aurora includes an offline, deterministic 20-byte payload feasibility study for
the -24 dB Deep objective. It compares a rate-1/2 convolutional baseline with
provisional rate-1/4 repeated-bit candidates, soft combining, and fixed
interleaving. It exercises acquisition, carrier and clock hypotheses, audio
channel impairments, soft decoding, and CRC validation without opening audio or
radio hardware.

The design and measurement limits are documented in
`docs/deep_mode_study.md`. These experiments do not define or claim an
over-the-air protocol.

The current implementation status, completed validation, end-of-day
conclusions, and prioritized next steps are recorded in
`docs/development_status.md`.

Long campaigns use `modem.deep_validation.DeepValidationConfig` and
`run_deep_validation`. The runner supports deterministic batch ranges,
cancellation, confidence intervals, runtime measurements, optional traced peak
memory, carrier and clock grids, named HF profiles, and an optional
CRC-validated fading fallback. Research-only candidate-aware time diversity
retains bounded timing hypotheses and combines reliability-normalized soft
observations. With a clock grid that brackets the injected channel error, the
latest -24 dB campaign delivered 45/60 severe-composite frames and 31/60
strong-selective frames. These results remain provisional and do not establish
the locked -24 dB acceptance target.

## Versioning

Aurora uses semantic versioning. The first development release will begin in
the `0.x` version range.
