# Status report 3: DAC sizing, a bandwidth correction, and the receiver bound (2026-10-17)

*Plain-language update after [report 2](2026-10-17-02-audit-and-noise.md).*

## A correction first

We had been telling you the fast (pattern) path has a bandwidth of "about 280 kHz". **That was
wrong for the final design.** The 280 kHz came from an earlier version that used four times more
bias current. The final design's response is flat only between **1.8 kHz and 63 kHz**; at the
480 kHz chip rate only 13 % of the peak gain is left, so the flicker pattern is heavily smeared.
The detection results were not affected (the detection simulation uses this exact response), but the
status page and diagram had the wrong number. Both are fixed (technical note: §38).

## Is the receiver wasting signal? No.

With such smeared chips it was reasonable to ask whether a smarter receiver would help a lot.
We computed the best any receiver could possibly do on this exact circuit. It is only **0.5 dB**
better than the simple one (needs 23.2 nA instead of 24.6 nA). So the limit really is the
circuit's noise and bandwidth, not the receiver. (We caught one of our own formula mistakes
here: our first "best possible" receiver came out *worse* than the simple one, which cannot be
true, so we found and fixed a factor-of-two error.)

Running the code slower helps only a little: at the same 100 µs window, 4x lower chip rate gives
about 12 % less current needed, but also a shorter code (weaker security). Making the window
longer is the effective lever (report 2).

## Designing the converter that cancels the steady current

The cancelling transistor is the main noise source for the pulse path (report 2). We tested how to
build it with less noise:

| Change (1 µA of steady current) | Noise |
|---|---|
| plain transistor, 200 µm² | 78 pA |
| + source resistor (0.3 V drop) | 9.5 pA |
| + 4x larger transistor | 5.5 pA |
| + 16x larger transistor | 3.5 pA |

Take-aways: the **resistor matters most**; **bigger area helps slowly** (noise falls roughly with the
square root of area); **cutting the converter into many small cells does not by itself lower the noise**
(it should be done for accuracy and glitches, not noise); a converter sized for roughly
3 000 µm² of active transistor area per µA reaches about 2x the amplifier's own noise floor.

## What this does to the pulse signal quality

With the resistor-degenerated cancel transistor in the full pulse-path simulation (auto-ranging
included), the pulse signal-to-noise ratio becomes **58 dB at 100 nA and 63 dB at 1 µA**, up
from about 45 dB before. Lock time (24 ms), range switching and pulse accuracy are unchanged.

## Where things stand

* **Good:** pulse path, stability, supply rejection, power (61–74 µW analog), detection engine.
* **Weak:** pattern check needs ≥ 24 nA at the original 100 µs window; the relay attack and the
  pattern generator still need a decision and a cryptographer; the real converter and layout
  are not designed; noise magnitudes depend on an unverified transistor model.

## Next

Pick a concrete converter design (unit cells and resistor per current range), check the claim that
cell splitting does not change noise with a real segmented design, and keep reports current.
