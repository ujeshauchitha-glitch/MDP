# Status report 6: closing the open items (2026-10-17)

*Plain-language. Simulation only; nothing is built. Technical detail: [`../afe-architecture.md`](../afe-architecture.md) §42–§48; code in `simulation/rtl/` and `simulation/twin/`.*

## What was asked
Finish everything that was still undone. This report lists what was finished, what was found along the way, and what truly cannot be done without a chip, a lab or other people.

## Finished
| Item | Result |
|---|---|
| **Smaller area** | Each gain range gets its own small resistor network instead of one huge 111 MΩ resistor: same gain, speed and noise, ≈ 14 000 µm² saved. A smaller 25 pF coupling capacitor would save another 6 000 µm² but costs 11 % in reach. |
| **Digital circuits as real hardware descriptions** | The code generator (Trivium), the pattern verifier and the steady-current servo are now written as hardware (Amaranth), simulated and synthesised (yosys). The generator matches the reference output exactly; the verifier matches a fixed-point model bit for bit; the servo, run against the fitted analog models, locks in 25 ms and switches ranges at the right currents. |
| **Cost of the digital part** | About 8 900, 37 800 and 13 400 µm² of cells. The verifier (with its fake-light check) is by far the largest part. |
| **Cheaper fake-light check** | The full check was too costly for hardware; a simple filter that imitates the sensor's response keeps the protection against random fakes and nearly all of it against attackers who know most of the code. |
| **Converter for the steady-current canceller** | A voltage-driven converter with a sigma-delta stage: the ripple it leaves at the pulse output is below 0.06 mV, outside the pulse band. |
| **Key and synchronisation rules** | One on-chip generator drives both the LED and the verifier, so no synchronisation problem. Replaying an old recording, or using another device's key, is rejected. **Reusing a starting value (IV) would be fatal** (replay accepted 100 %), so the session counter must never repeat. A timing error of up to half a chip is harmless. |
| **Noise-model check** | The model's flicker noise for the cancel transistor was extracted. It cannot be confirmed without a real chip; the pulse noise scales with the square root of that value. |

## Found along the way (new problems)
1. **Ambient light flicker breaks the fixed fake-light check.** A mains-light flicker of just 1 % of the signal at 1 kHz makes genuine frames fail. Adjusting the thresholds from "LED-off" frames fixes it up to about 10 % (mains) or 1 % (lamp PWM at kHz). Such dark frames and the adaptation logic must be added.
2. **The digital part is expensive.** In total about 161 000 µm² (roughly 9 Tiny-Tapeout tiles, 12 with routing margin) and about 92–105 µW, which misses the 87 µW goal. A simple correlator-only verifier would be much smaller, but it accepts random fakes 16 % of the time.

## Cannot be finished here
* Real layout and place-and-route (no layout tool in this setup); the areas are synthesis-based estimates.
* Checking the noise model against silicon; the random-number generator and key memory circuits; a cryptographer's review.
* Defending against a fast optical relay: needs measures in the module or a higher layer.
* The transistor-level converter string, switches and ADCs.
