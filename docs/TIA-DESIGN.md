# TrustSense Layer 1 / Part 1 — Transimpedance Amplifier (TIA)

Status: **simulated (ngspice 47, sky130 tt corner, hand-fixed netlist).** The
hand-calculated first pass did not work as written; see §9 for what the first
real run found and what was changed. §1-§6 below are the original hand
derivation and are **partly superseded by §9** (pseudo-resistor, bandwidth,
noise). Reproduce with `simulation/spice/run-tia-sim.sh`.

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
| DC gain | 1 mV/pA (1 GΩ) ± 5% | ~1 GΩ (loop gain ≫ 20 makes closed-loop error ≪ 1%) | **0.997 GΩ (pass)** |
| -3 dB bandwidth | 4.8–5.0 kHz | ~5 kHz by construction (GBW solved for this) | **2.33 kHz (miss, see §9)** |
| Output noise (RTI SNR) | <100 µV RMS / >50 dB | **~360 µV RMS / ~6 dB — see §0, §4** | **1.56 mV RMS, 10 Hz–100 kHz (fail, see §9)** |
| Rise time (latency) | <100 ns | Not yet estimated — GBW ~1.9 MHz suggests slew/BW-limited rise time closer to ~1–2 µs for a 1kHz-band signal, likely missing the <100 ns target; needs the `.measure tran trise` result | **136 µs (fail, ~1000x over target, see §9)** |
| Power | <100 µW (target 87 µW) | 87.1 µW by budget construction | **85.3 µW (pass)** |

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

## 9. Simulation results and what the first run found (2026-10-15)

Tooling: ngspice 47 (Windows build), sky130 models from
`google/skywater-pdk-libs-sky130_fd_pr` (tt corner; the runner generates a
trimmed model library because the full `sky130.lib.spice` fails in ngspice on
the nvt/esd models). Numbers below are from `tia.spice` / `tia_wide.spice` as
committed.

**Defects in the hand-written netlist, found only by running it:**

1. MOS devices were instantiated as `M...`; sky130 devices are subcircuits and
   need `X...` instances, plus `.option scale=1u` for W/L in µm. The netlist
   did not load.
2. `Rsh` (500 MΩ photodiode shunt to ground) out-competes the pA-level DC path
   of the pseudo-resistor and pins the input near 0 V. Removed (dark current
   belongs in Iph's DC term).
3. The NMOS pseudo-resistor (gates on the outer terminals, bulk at gnd) is
   one-sided: it measured ~650 GΩ and could not pull the input to VCM. Replaced
   with the standard back-to-back PMOS pair (gates on the shared node, body on
   source); W=94 µm, L=0.15 µm, m=2 gives 0.997 GΩ. This is **not** "~2 µm² of
   silicon" as §2 assumed (~190 µm of total width).
4. The circuit has a second, latched DC state (`amp_out` railed at 3.3 V).
   A `.nodeset` steers the solver to the intended state. Whether it settles
   there by itself at power-up in silicon is **not verified** (needs a
   start-up transient or reset switch).
5. `i(Iph)` is not valid for a current source in ngspice; gain now uses the
   known 1 pA AC magnitude. Rise time is measured on a 1 pA step (the output
   falls: the TIA inverts).

**Slow path (Path A), measured:**

| Metric | Target | Measured |
|---|---|---|
| DC transimpedance | 1 GΩ ±5% | 0.997 GΩ |
| -3 dB bandwidth | 4.8–5.0 kHz | **2.33 kHz** |
| Peaking | none | 0 dB |
| 10-90% rise time | <100 ns | **136 µs** |
| Output noise 10 Hz–100 kHz | <100 µV | **1.56 mV RMS** |
| Power (op / transient) | <100 µW | 85.3 µW |

- **Bandwidth is not GBW-limited.** Cc from 4.2 pF down to 0.5 pF moved BW
  only 1.79 → 1.64 kHz. The pole is Rf × (Cf + pseudo-resistor parasitics),
  about 0.1 pF effective, set mostly by ~190 µm of PMOS width. §3's
  "GBW 1.9 MHz → 5 kHz" derivation does not apply. Reaching 5 kHz at 1 GΩ needs
  less parasitic capacitance per GΩ (not demonstrated here).
- **Rise time ≈ 0.35/BW**, so <100 ns is unreachable by ~3 orders of magnitude
  for any 1 GΩ, kHz-class TIA. Drop the target or move it to the wideband path.
- **The 1.56 mV noise is a wide-band integral** (10 Hz–100 kHz) dominated by
  out-of-band noise gain; it has not been re-integrated over the signal band,
  so the 360 µV hand estimate in §4 is neither confirmed nor refuted.
- **Loop gain / phase margin** (AC voltage injected in series with the
  feedback path, `simulation/spice/loopgain_pm.py`): DC loop gain 82.5 dB,
  unity-gain at 12.4 kHz, **phase margin 81°**. Single-injection method (the
  feedback network is GΩ-class vs. a low-impedance follower output, so the
  Middlebrook correction is small); not cross-checked with a two-injection run.

## 10. Wideband path (Path B), `simulation/spice/tia_wide.spice`

Same two-stage op-amp with Rbias 600 kΩ (about 2x currents), Cc 2 pF, ideal
Rf = 314 kΩ (placeholder; to become a poly resistor) and Cf = 1.4 pF for
peaking control. Found by sweeping Rbias/Cc/Cf: at the original bias with
Cf≈0 the amp peaked 10–19 dB.

| Metric | Target (afe-architecture §3) | Measured |
|---|---|---|
| Transimpedance | 314 kΩ | 314 kΩ |
| -3 dB bandwidth | 480 kHz | 483 kHz |
| Peaking | none | 0 dB |
| 10–90% rise time (1 nA step) | ≤ 1 chip period (2.1 µs) | 0.77 µs |
| Power | "~87 µW class" | **169 µW** |
| Input-referred noise | 236 fA/√Hz (I_DC = 10 nA) | **363 fA/√Hz @10 kHz, 391 @100 kHz, 724 @316 kHz, 505 @1 MHz** |

Noise is 1.5x the budget at low frequency and about 3x near the top of the
code band (op-amp noise, as the caveat in afe-architecture §4 predicted).

Loop gain / phase margin (same method as §9): DC loop gain 72.6 dB, unity-gain
at 711 kHz, **phase margin 67°**.
