# Status report 5: digital twin built, open items closed or decided (2026-10-17)

*Plain-language. All simulation, nothing built. Technical detail: [`../afe-architecture.md`](../afe-architecture.md) §39–§41, code in `simulation/twin/`.*

## 1. The digital twin exists
`simulation/twin/` now holds one program that models the whole chain: light on the photodiode (steady
level, heartbeat, the chip's own coded flicker, an attacker's light) → the slow pulse path with its automatic
steady-current canceller and range switching → the fast verification path with the 48-chip correlator → a
"trusted / rejected" verdict.

It is built from the circuit simulations, not from guesses, and it was checked against them:
| Check | Twin | Earlier stand-alone result |
|---|---|---|
| Fast-path detection strength at 10 nA…1 µA | within 1.2 % | (reference) |
| Minimum steady current for reliable detection | 23–36 nA (24 nA at 100 nA) | 24 nA |
| Canceller lock time, range chosen | 24.5 ms, same range at all five currents | same |
| Pulse gain / pulse-band noise (5 nA…1 µA) | 0.997–0.999 / 0.6–8.8 pA | 0.999 / 0.7–10.5 pA |

Scenarios (`scenarios.txt`): genuine contact accepted 60/60; blind fake light 0/60 (even 30x brighter);
an attacker who knows 90 % of the chips 5/60; a fast relay (130 ns) passes 56/60, a slow one (520 ns) 0/60.

## 2. Decisions taken
* **Chip generator = Trivium**, a small standard keyed stream cipher (checked against its published test
  vector). It replaces the shift-register generator that could be predicted after 64 chips.
* **Relay attack cannot be stopped inside this chip.** An attacker who copies each flicker within tens of
  nanoseconds always keeps up with a 2 µs chip. It needs a physical measure (sealed LED-to-sensor path, LED current
  sensing) or a higher layer. The security claim should say: resists blind and guessing attacks, not a real-time optical relay.
* **Bandwidth (63 kHz vs 480 kHz target):** the bias setting was already optimised (300 nA is the best trade);
  the shortfall costs about 1.2 dB. Closed as an accepted deviation.

## 3. New design pieces
* **Cancel converter:** a 12-bit voltage DAC driving the gate of the quiet, resistor-degenerated cancel
  transistor. A 100 kΩ DAC output adds under 0.1 pA of noise. Splitting the transistor into 4 or 16 cells gives exactly the same noise.
* **Fast-path digitiser (was missing):** needs about 2 million samples/s (4 per chip) and fine steps of 300 µV
  or less at the input (a gain stage plus an 8-bit converter); this costs at most 0.6 dB.

## 4. Size and power (rough estimates, no layout tool run)
About **90 000 µm², roughly five Tiny-Tapeout tiles, so it does not fit one**. The biggest pieces: logic, the
111 MΩ resistor, the 50 pF capacitor, the code generator. Digital and converter power about 22 µW, total about
83–96 µW against the 87 µW goal.

## 5. Still open
Silicon-level truth of the transistor noise model; real layout and a synthesis run; cryptographic key
storage and synchronisation between LED driver and verifier; transistor-level design of the DAC string, switches, and ADCs;
relay defence at module level; shrinking the area to the tile budget.
