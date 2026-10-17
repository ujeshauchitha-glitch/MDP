"""First-order area and digital-power budget for the Layer-1 chip (ESTIMATES from stated assumptions;
no synthesis, placement or layout tool has been run).

Technology assumptions (sky130): xhigh-rho poly 2 kOhm/sq, width 0.35 um, ~0.25 um^2 per square incl. spacing;
MIM cap 2 fF/um^2 (1 layer pair) or 4 fF/um^2 (double MIM); D flip-flop 20 um^2, NAND2-equivalent 3.75 um^2,
std-cell utilisation 50 %; energy per flop clock edge ~20 fJ incl. local clock, per gate toggle ~5 fJ at 1.8 V.
Tiny Tapeout 1x1 tile = ~160 x 111 um = 17.9 k um^2 (a design may use up to 8x2 tiles)."""
import os
SYN = dict(trivium=8854, verifier=37772, servo=13364)   # simulation/rtl/synth_results.txt (yosys, generic gates -> sky130_fd_sc_hd areas)
CC = float(os.environ.get("CC", 50e-12))
SQ_A = 0.25            # um^2 per square of xhrpoly
ohm = lambda r: r / 2000 * SQ_A
area = {
    "Cc coupling cap (double MIM, 4 fF/um2); 50 pF baseline": CC / 4e-15,
    "T-network R1+R2 (2 x 10 Mohm)": 2 * ohm(10e6),
    "100M-range T-network (2 x 3.095 Mohm, replaces 111 Mohm parallel R, sec. 42)": 2 * ohm(3.095e6),
    "10M-range T-network (2 x 0.912 Mohm, replaces 10.1 Mohm parallel R)": 2 * ohm(0.912e6),
    "cancel-device degeneration Rs 30M + 3M + 0.3M (per range)": ohm(30e6) + ohm(3e6) + ohm(0.3e6),
    "bias degeneration 3 Mohm + 2x mirror 200 kohm + TIA 314 kohm": ohm(3e6) + ohm(0.8e6) + ohm(0.314e6),
    "feedback / compensation caps (<= 1.5 pF x3 + misc 5 pF)": 10e-12 / 2e-15,
    "cancel device cells (16 x 200 um2 gate, plus routing x1.5)": 16 * 200 * 1.5,
    "two op-amps + mirrors + switches": 2000 + 1500,
    "slow ADC 10 bit / 2 kS/s + gate-voltage DAC 12 bit (string)": 4000,
    "fast PGA preamp + 6 bit ADC ~2 MS/s": 3000,
    "Trivium RTL (synthesised cell area 8.9k) @50 % util": SYN["trivium"] / 0.5,
    "fast-path verifier RTL (corr + IIR template + residual; 6-bit samples, 38k cells) @50 % util": SYN["verifier"] / 0.5,
    "servo + auto-range RTL (13k cells) @50 % util": SYN["servo"] / 0.5,
}
tot = sum(area.values())
print("AREA estimate [um^2]")
for k, v in area.items():
    print(f"  {v:9.0f}  {k}")
print(f"  {tot:9.0f}  TOTAL = {tot/17900:.1f} Tiny-Tapeout 1x1 tiles (x1.3 routing margin: {1.3*tot/17900:.1f})")

# power from the synthesised blocks: P = f * (FF * E_ff + gates * E_g * alpha); E_ff = 15 fJ (clock pin + internal), E_g = 3 fJ, alpha = 0.25
E_ff, E_g, AL = 15e-15, 3e-15, 0.25
blocks = {"Trivium @ 480 kHz": (301, 522, 480e3), "verifier @ 1.92 MHz (1 sample/clock)": (422, 4754, 1.92e6), "servo @ 100 kHz": (126, 1934, 100e3)}
p = {k: f * (ff * E_ff + g * E_g * AL) for k, (ff, g, f) in blocks.items()}
p["fast ADC 6 bit @ 1.92 MS/s (Walden FoM 30 fJ/step) + programmable-gain preamp (assumed 5 uW)"] = 30e-15 * 2 ** 6 * 1.92e6 + 5e-6
p["slow ADC 10 bit @ 2 kS/s"] = 30e-15 * 2 ** 10 * 2e3
p["leakage ~8000 gates + 900 FF x 10 pW"] = 8900 * 10e-12
print("\nDIGITAL / MIXED-SIGNAL POWER estimate [uW] (gate counts from yosys, energies assumed)")
for k, v in p.items():
    print(f"  {v*1e6:7.2f}  {k}")
d = sum(p.values())
print(f"  {d*1e6:7.2f}  TOTAL digital+ADC;  + analog 61-74 uW (low-power bias) = {d*1e6+61:.0f}-{d*1e6+74:.0f} uW  (original goal 87 uW)")
