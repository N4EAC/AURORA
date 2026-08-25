# Aurora bootstrap characterization

Aurora provides a seeded offline audio-AWGN screen in
`modem.bootstrap_validation`. It protects the bootstrap with Aurora's
rate-1/2 convolutional FEC and CRC and reports only CRC-confirmed delivery.

On August 25, 2026, seed `20260825` produced the following development result
at -8 dB SNR in the 2.5 kHz reference bandwidth:

| Profile | Signal decodes | Noise-only false decodes |
|---|---:|---:|
| 500 Hz | 0/40 | 0/100 |
| 2.3 kHz | 0/40 | 0/100 |
| 2.8 kHz | 0/40 | 0/100 |

A 20-trial-per-point threshold scan produced 8/20, 19/20, and 19/20 at +4 dB
for 500 Hz, 2.3 kHz, and 2.8 kHz respectively. The wider profiles reached
20/20 by +8 dB; 500 Hz reached 18/20 at +12 dB. These small seeded screens are
diagnostic observations, not sensitivity claims or confidence-bounded
acceptance results.

The current bootstrap is therefore suitable only for strong-signal engineering
tests. Weak-signal bootstrap coding, acquisition thresholds, and fading
behavior require further design and substantially larger validation campaigns.
