# TrustSense Layer 1 / Part 1 — Transimpedance Amplifier (TIA)

Status: **hand-calculated first pass, not yet simulated.** No ngspice/sky130
toolchain was available in the environment these files were generated in.
Run `simulation/spice/run-tia-sim.sh` (see [Expected vs. measured](#expected-vs-measured))
and update the "measured" column below before treating any number here as
verified.

## 0. A spec conflict worth flagging first

The brief asks for two things that don't fit together simultaneously:

- Output swing 0–1 mV for a 1 pA input ⇒ transimpedance gain = 1 mV / 1 pA =
  **1 GΩ**, not 1 kV/pA (1 kV/pA = 1 GΩ × 1000 — that would need a 1 PΩ
  feedback element, which isn't physical). The deliverable list itself asks
  for a 1 GΩ feedback resistor, so I designed to **Rf = 1 GΩ ⇒ 1 mV/pA
  transimpedance**, and I'm assuming "1 kV/pA" in the success criteria is a
  units slip for "1 mV/pA."
- **The noise target (<100 µV RMS output, SNR > 50 dB) is not achievable
  with Rf = 1 GΩ over a 5 kHz noise bandwidth — it's a physics limit, not an
  op-amp quality problem.** Worked out in §3 below: Rf's own thermal noise
  alone integrates to ~360 µV RMS at the output, 3.6x over the 100 µV
  budget, before the op-amp or photodiode contribute anything. If the 100 µV
  spec is hard, the fix has to happen downstream (narrower final bandwidth,
  or coherent averaging in the correlator block the roadmap already has
  planned) — not in this stage. Flagging this now rather than after a
  simulation run "fails" against an unreachable target.

## 1. Topology

Standard shunt-feedback TIA:

```
                     Cf (20 fF)
              +----------||----------+
              |                      |
              |      Rf (pseudo-R)   |
  photodiode ---+----/\/\/\----------+---- tia_out
  (cathode)   |                      |
             Cj                 [two-stage op-amp]---[buffer]
            (10pF)                   |
              |                      |
             gnd                    vcm (1.65V, non-inverting input)
```

- **Op-amp**: two-stage Miller-compensated, PMOS input pair (5T OTA first
  stage) + NMOS common-source second stage, NMOS source-follower output
  buffer to drive the next block's (PGA) input capacitance.
- **Feedback element**: MOS-bipolar pseudo-resistor (two anti-series,
  diode-connected `sky130_fd_pr__nfet_01v8`), not a literal poly resistor.
  See §5.
- **Bias**: single 2 µA reference branch (`Rbias` + diode-connected NMOS),
  mirrored around the chip. Total supply current budget ≈ 26.4 µA @ 3.3 V.

Full device list and node names: [`simulation/spice/tia.spice`](../simulation/spice/tia.spice)
(source of truth) and [`hardware/afe/tia.sch`](../hardware/afe/tia.sch) (schematic capture,
hand-authored — open in xschem, run ERC, and auto-route before trusting it for layout).

## 2. Component selection

**Feedback resistor → pseudo-resistor, not poly.** sky130A's highest-sheet-rho
poly option (`res_xhigh_po`) is on the order of 2–3 kΩ/sq. A literal 1 GΩ
resistor would need on the order of 300k+ squares — completely infeasible on
a 334×225 µm (2×2) Tiny Tapeout analog tile. Real low-power biosensor AFEs
(PPG/ECG) hit this same wall and universally solve it the same way: two
diode-connected MOSFETs in anti-series, biased near/below threshold, giving
GΩ-to-TΩ incremental resistance from ~2 µm² of silicon (the classic
Harrison & Charles neural-amplifier pseudo-resistor). Both terminals of the
feedback element sit at the ~1.65 V virtual-ground DC point (not across the
3.3 V rail), so I used the thin-oxide `nfet_01v8` devices for it even though
the rest of the amplifier needs the 5V-tolerant `g5v0d10v5` devices — no
overvoltage risk since the DC drop across the pseudo-resistor is ~0 V by
construction.

**Op-amp topology.** A single 5T OTA stage gives gm·ro ≈ 20–40 (26–32 dB),
not enough loop gain for <5% transimpedance error with Rf this large — the
TIA's closed-loop accuracy depends directly on loop gain (error ≈ 1/A0β).
A two-stage Miller-compensated amp gets ~84 dB (see §3), which drives the
gain error well under 1%. PMOS input pair chosen for lower 1/f noise at the
sub-µA bias currents this design runs at (flicker noise ∝ 1/(Cox·W·L), and
PMOS in sky130 has a smaller 1/f coefficient than NMOS).

**Bias current.** ~10 µA total in the first stage (8 µA tail + 2 µA
reference) trades off gm (and hence noise and GBW) against power. Lower
bias current pushes into subthreshold where gm/ID is best per µA but gm
itself drops and 1/f noise corner rises; 8 µA tail keeps M1/M2 in moderate
inversion where thermal-noise gm/ID is still decent without ballooning
device area for a target gm.

**High-voltage devices for the amplifier core.** VAPWR = 3.3 V exceeds the
~1.98 V absolute max for sky130's thin-oxide `_01v8` devices, so the
diff pair, mirror loads, gain stage, and buffer all use the thick-oxide
`sky130_fd_pr__{n,p}fet_g5v0d10v5` devices (5 V / 10.5 V rated), which is
standard practice for analog blocks running off the Tiny Tapeout 3.3 V
analog rail.

## 3. Stability analysis

Hand-calculated, long-channel square-law estimates (device sizes/currents
in `tia.spice`); treat as a starting point for tuning, not a verified
result.

| Parameter | Value |
|---|---|
| Stage 1 gm (M1/M2) | ≈ 49 µS |
| Stage 1 gain A1 | ≈ 147 V/V (43.3 dB) |
| Stage 2 gm (M6) | ≈ 89 µS |
| Stage 2 gain A2 | ≈ 107 V/V (40.6 dB) |
| **Open-loop DC gain A0** | **≈ 15,800 V/V (≈ 84 dB)** |
| Miller cap Cc | 4.2 pF |
| Nulling resistor Rz | 11 kΩ |
| **GBW** | **≈ 1.9 MHz** |
| Non-dominant pole p2 | ≈ 3.4 MHz |
| **Estimated phase margin** | **≈ 61°** (meets the >60° target) |

GBW was back-solved from the TIA bandwidth relation for a shunt-feedback
amplifier (Graeme's formula):

```
f_-3dB ≈ sqrt( GBW / (2π · Rf · Cin_total) )
```

with `Cin_total` = photodiode Cj (10 pF) + estimated op-amp input cap
(~2 pF) ≈ 12 pF. Solving for f_-3dB = 5 kHz gives GBW ≈ 1.9 MHz, which sets
Cc via `Cc = gm1 / (2π·GBW)`.

`Cf` (20 fF) is a deliberate, small, explicit compensation cap across the
pseudo-resistor rather than relying on unpredictable layout parasitics —
the "optimal" Cf from the standard feedback-pole formula
(`Cf = sqrt(Cin / (2π·Rf·GBW))`) comes out sub-femtofarad here (GBW is
already high relative to what the Rf·Cin pole needs), so 20 fF is
conservative headroom, not a critical value. **The actual -3dB point needs
to come from the AC sweep in `tia.spice`** (`.measure ac bw_3db`) — trim Cf
up/down from there to land in the 4.8–5.0 kHz window; don't treat the
1.9 MHz GBW number as exact without that feedback.

## 4. Noise budget

Noise bandwidth for a single dominant pole ≈ (π/2)·f_-3dB ≈ 7.85 kHz (at
f_-3dB = 5 kHz).

| Source | Input-referred current noise | Output-referred (× Rf = 1 GΩ) |
|---|---|---|
| **Rf (pseudo-resistor) thermal noise** | 4.07 fA/√Hz → 360 fA RMS over 7.85 kHz | **≈ 360 µV RMS** |
| Op-amp input-referred noise (≈32 nV/√Hz, × noise-gain peaking ≈3–5x) | — | ≈ 12 µV RMS (estimate) |
| Photodiode shot noise | not modeled — testbench has no DC photocurrent term (see §6) | — |
| **Total (RSS, dominated by Rf)** | | **≈ 360 µV RMS** |

Signal at Rf = 1 GΩ: 1 pA amplitude → 1 mV peak → 707 µV RMS output.

**Resulting SNR ≈ 707/360 ≈ 5.9 dB — nowhere near the 50 dB target,** and
this is before the op-amp adds anything. This is the §0 conflict in
numbers: at Rf = 1 GΩ, thermal noise from the feedback element itself is
the binding constraint, not amplifier design quality. Reducing the op-amp's
own noise contribution further (it's already only ~3% of the total) would
not move the needle. The two real levers are (a) narrowing the noise
bandwidth after this stage, or (b) relying on the downstream correlator for
coherent averaging gain — both of which live in the next block, not here.

## 5. Power / gain / bandwidth trade-offs

Budget: 87 µW @ 3.3 V = 26.4 µA total.

| Branch | Current | Rationale |
|---|---|---|
| Bias reference | 2 µA | Minimum to keep mirror devices out of deep subthreshold mismatch territory |
| Stage 1 tail (diff pair) | 8 µA | Sets gm1 → GBW → closed-loop bandwidth |
| Stage 2 | 10 µA | Sets gm2 → non-dominant pole → phase margin headroom |
| Output buffer | 6.4 µA | Sized to drive ~2 pF next-stage (PGA) input without slew-limiting at 1 kHz |
| **Total** | **26.4 µA** | **87.1 µW @ 3.3 V** |

Gain (Rf) and bandwidth (GBW) are coupled through the Graeme formula in §3
— for a fixed Rf and Cin, higher bandwidth needs proportionally more GBW²,
i.e. more bias current in stage 1. 87 µW was sized to hit 5 kHz bandwidth
with margin (61° phase margin, not marginal ~45°); pushing power lower
would either shrink phase margin or require increasing Cc (which drags
bandwidth back down) — 87 µW is close to the minimum that hits both
bandwidth and stability targets simultaneously with this topology.

## 6. Sky130 process considerations

- **Devices**: `sky130_fd_pr__{n,p}fet_g5v0d10v5` for anything across the
  3.3 V rail; `sky130_fd_pr__nfet_01v8` is fine only where both terminals
  sit at the virtual-ground DC point (the pseudo-resistor).
- **Resistors**: `Rbias` (1.2 MΩ) and `Rz` (11 kΩ) are both realistic
  values for sky130's standard poly resistor options — no exotic
  high-sheet-rho device needed for either.
- **Cc (4.2 pF)**: at sky130 MiM cap density (~2 fF/µm²) this is roughly
  2000 µm² (~45×45 µm) — a meaningful fraction of a 334×225 µm tile but
  plausible for a 2×2-tile analog macro. Worth confirming against the
  actual MiM density in the PDK's device tables before committing to
  final layout.
- **Substrate/well biasing**: NMOS bulk → `vgnd`, PMOS bulk → `vdpwr`
  throughout (standard n-well process, no deep-nwell isolation used here —
  add DNW devices if this ever needs to sit in a noisy digital-heavy tile).

## 7. Expected vs. measured

| Metric | Target | Hand-calculated expectation | Measured (run the sim) |
|---|---|---|---|
| DC gain | 1 mV/pA (1 GΩ) ± 5% | ~1 GΩ (loop gain ≫ 20 makes closed-loop error ≪ 1%) | TBD |
| -3 dB bandwidth | 4.8–5.0 kHz | ~5 kHz by construction (GBW solved for this) | TBD |
| Output noise (RTI SNR) | <100 µV RMS / >50 dB | **~360 µV RMS / ~6 dB — see §0, §4** | TBD |
| Rise time (latency) | <100 ns | Not yet estimated — GBW ~1.9 MHz suggests slew/BW-limited rise time closer to ~1–2 µs for a 1kHz-band signal, likely missing the <100 ns target; needs the `.measure tran trise` result | TBD |
| Power | <100 µW (target 87 µW) | 87.1 µW by budget construction | TBD |

Run `simulation/spice/run-tia-sim.sh` (needs ngspice + sky130A PDK on
PATH/`PDK_ROOT`) and fill in the last column. Expect at least one or two
iterations on device sizes / Cc / Cf — that's normal for a hand-calculated
first pass.

## 8. Known simplifications / next steps

- The photodiode testbench models only the AC signal (`SIN(0 1p 1k)`), no
  DC photocurrent. A real PPG photodiode sees significant DC current from
  ambient light + LED backscatter (nA–µA range), which would dominate shot
  noise and shift the op-amp's input common-mode. Add a DC term once real
  LED/photodiode operating points are known.
- The current mirrors are simple (no cascoding) — fine for a first pass,
  but output resistance (and hence DC gain) will be higher in practice with
  cascode mirrors if 84 dB turns out to be marginal.
- `hardware/afe/tia.sch` was hand-authored to match the netlist topology
  and device list, but its wire routing has not been opened/checked in the
  xschem GUI — run ERC and re-route visually before using it for layout.
- The rise-time target (<100 ns) looks hard to hit with a ~1.9 MHz GBW
  amplifier — worth revisiting once `trise` comes back from simulation;
  may need a faster (higher-power) buffer stage if this is a hard
  requirement rather than a rough target.
