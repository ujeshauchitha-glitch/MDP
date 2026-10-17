# Status report 2: audit, the noise culprit, and long integration (2026-10-17)

*Plain-language update covering the work after the [overview](2026-10-17-overview.md).*

## What we did

1. **Audited everything done so far** (technical record: §33).
2. **Found out what limits the pulse-path noise** and tested a fix (§34, §36).
3. **Worked out how long the code has to run** to detect dim signals (§35).
4. **Set up regular status reports** (this folder).

## 1. The audit: is what we reported correct?

| Check | Result |
|---|---|
| Does the detection simulator give the right answer for a case we can solve by hand? | **Yes**, within 0.1 % |
| Are the noise numbers in the right units? | **Yes**: a 1 kΩ resistor gives exactly the textbook 4.07 nV/√Hz |
| Does the very first simulation run still reproduce its numbers? | **Yes**, exactly |
| Do the committed circuit files match the scripts that generate them? | **Yes** |
| Is the repeated security study the same on the final circuit? | **Yes** (blind fake accepted 16 %, relay still works) |

**Mistakes found and fixed:**
* The allowed supply-noise limits we wrote contained arithmetic errors (one was 10x too strict).
  Corrected.
* We had blamed a simulator setting ("tight tolerances") for odd noise results without proof.
  We now have proof it can give *impossible* noise values in some circuits (below the
  resistor's own noise), so noise is always run with the default setting. We re-ran the whole
  corner/supply table with this rule and every number came out the same, so nothing earlier
  changes.
* Several lists in the one-page status were out of date (items listed as "still to do" that
  were already done). Fixed, and old claims now point to their corrections.

## 2. What limits the pulse-path noise, and a fix

We replaced the transistor that cancels the steady current with a perfect, noiseless one. The
noise of the pulse path dropped by 85–95 % at 100 nA. **So that cancelling transistor is the
main noise source**, and the converter we will eventually build to do this job matters a lot.

The fix is a standard analog trick: a resistor in the transistor's source ("degeneration").
Sized to drop about 0.3 V, it cuts the noise:

| Steady current | Noise now | With the resistor |
|---|---|---|
| 100 nA | 8.4 pA | **1.8 pA** |
| 1 µA | 78.7 pA | **10.5 pA** |

That is a pulse signal-to-noise gain of **+13 dB at 100 nA and +17.5 dB at 1 µA**
(before: about 45 dB at every level; after: 58–63 dB for bright signals). The resistor
value has to scale inversely with the current (3 MΩ at 100 nA, 300 kΩ at 1 µA), so it would be
switched per range.

## 3. How long must the code run to see a dim signal?

The first plan wanted the pattern check to work down to 10 nA of steady current. It currently
needs about 24 nA. Running the code longer helps in a predictable way (noise averages out as
1/√time):

| Code window | Lowest steady current that works (flicker = 2 % of it) |
|---|---|
| 0.1 ms (now) | 24 nA |
| 0.6 ms | **10 nA** |
| 1 ms | 7.7 nA |
| 3 ms | 4.4 nA |

If the flicker is only 1 % of the current the times are 4x longer (10 nA needs ~2.4 ms), and
0.5 % needs 16x longer (~9 ms). The catch: a longer window means slower decisions, and this
calculation assumes only white noise (real sensors also see slow lighting flicker), so it is
optimistic for windows over about 1 ms.

## 4. Open items (unchanged, short list)

* Fast optical **relay attack** and the **secret-pattern generator** need a security decision
  and a cryptographer's review.
* A **real converter** for the steady-current canceller (noise, glitch, area) is not designed.
* **Digital power, layout and area** are not included.
* The transistor **noise model** has no real-silicon check.

## Next

Commit to a reference design for the canceller converter (degenerated unit cells), look at
whether the fast-path bandwidth can be pushed toward the 480 kHz target, and keep the reports
current.
