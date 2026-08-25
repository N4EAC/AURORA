# Aurora transmitter-linearity requirements

Aurora OFDM requires a linear audio and RF chain. Immediately before radio
playback, Aurora measures normalized audio and rejects a transmission exceeding
any current limit:

| Measurement | Limit |
|---|---:|
| Absolute peak | 0.50 maximum |
| Active-sample RMS | 0.15 maximum |
| Crest factor | 3.0 through 6.0 |
| Absolute DC offset | 0.005 maximum |
| Samples at or above 0.98 | zero |

The OFDM generator peaks at 0.78 before the standard 0.55 playback gain. A
representative conditioned frame measures approximately 0.429 peak, 0.107
active RMS, and 4.0 crest factor. These software limits prevent normalized
audio clipping but cannot detect distortion introduced after the computer
output.

For radio tests, disable speech compression, processing, equalization, noise
reduction, and transmit filtering that distorts the selected passband. Set the
radio and interface gains so ALC is inactive or barely indicated. Verify RF
occupied bandwidth and intermodulation with suitable test equipment before
increasing power.
