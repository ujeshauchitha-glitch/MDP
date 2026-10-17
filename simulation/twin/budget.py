"""First-order area and digital-power budget for the Layer-1 chip (ESTIMATES from stated assumptions;
no synthesis, placement or layout tool has been run).

Technology assumptions (sky130): xhigh-rho poly 2 kOhm/sq, width 0.35 um, ~0.25 um^2 per square incl. spacing;
MIM cap 2 fF/um^2 (1 layer pair) or 4 fF/um^2 (double MIM); D flip-flop 20 um^2, NAND2-equivalent 3.75 um^2,
std-cell utilisation 50 %; energy per flop clock edge ~20 fJ incl. local clock, per gate toggle ~5 fJ at 1.8 V.
Tiny Tapeout 1x1 tile = ~160 x 111 um = 17.9 k um^2 (a design may use up to 8x2 tiles)."""
SQ_A = 0.25            # um^2 per square of xhrpoly
ohm = lambda r: r / 2000 * SQ_A
area = {
    "Cc 50 pF coupling cap (double MIM, 4 fF/um2)": 50e-12 / 4e-15,
    "T-network R1+R2 (2 x 10 Mohm)": 2 * ohm(10e6),
    "Rpar 111 Mohm (100M range)": ohm(111e6),
    "Rpar 10.1 Mohm (10M range)": ohm(10.1e6),
    "cancel-device degeneration Rs 30M + 3M + 0.3M (per range)": ohm(30e6) + ohm(3e6) + ohm(0.3e6),
    "bias degeneration 3 Mohm + 2x mirror 200 kohm + TIA 314 kohm": ohm(3e6) + ohm(0.8e6) + ohm(0.314e6),
    "feedback / compensation caps (<= 1.5 pF x3 + misc 5 pF)": 10e-12 / 2e-15,
    "cancel device cells (16 x 200 um2 gate, plus routing x1.5)": 16 * 200 * 1.5,
    "two op-amps + mirrors + switches": 2000 + 1500,
    "slow ADC 10 bit / 2 kS/s + gate-voltage DAC 12 bit (string)": 4000,
    "fast preamp + 8 bit ADC ~2 MS/s": 3500,
    "Trivium (288 FF + ~100 gates) @50 % util": (288 * 20 + 100 * 3.75) / 0.5,
    "correlator (48x accumulate, 14 bit) + servo FSM + control (~3000 gate-eq)": 3000 * 3.75 / 0.5,
}
tot = sum(area.values())
print("AREA estimate [um^2]")
for k, v in area.items():
    print(f"  {v:9.0f}  {k}")
print(f"  {tot:9.0f}  TOTAL = {tot/17900:.1f} Tiny-Tapeout 1x1 tiles (x1.3 routing margin: {1.3*tot/17900:.1f})")

f_chip = 480e3
E_ff, E_g = 20e-15, 5e-15
p = {
    "Trivium 288 FF + 100 gates @ 480 kHz (x2 clock tree)": 2 * (288 * E_ff + 100 * E_g) * f_chip,
    "correlator add/sub 14 bit @ 1.92 MS/s (4 samples/chip)": 14 * 6 * E_g * 1.92e6,
    "servo logic @ 2 kHz + SD DAC @ 100 kHz": 1500 * E_g * 100e3 * 0.2,
    "fast ADC 8 bit @ 1.92 MS/s (Walden FoM 30 fJ/step)": 30e-15 * 2 ** 8 * 1.92e6,
    "slow ADC 10 bit @ 2 kS/s": 30e-15 * 2 ** 10 * 2e3,
    "leakage ~6000 gates x 10 pW": 6000 * 10e-12,
}
print("\nDIGITAL / MIXED-SIGNAL POWER estimate [uW]")
for k, v in p.items():
    print(f"  {v*1e6:7.2f}  {k}")
d = sum(p.values())
print(f"  {d*1e6:7.2f}  TOTAL digital+ADC;  + analog 61-74 uW (low-power bias) = {d*1e6+61:.0f}-{d*1e6+74:.0f} uW  (original goal 87 uW)")
