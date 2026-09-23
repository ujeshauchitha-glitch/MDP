# TrustSense Layer 1 — AFE Architecture Spec

Status: derived, unsimulated. Every number below is tagged **[DERIVED §n]**
(traceable to a section in this doc) or **[UNMEASURED]** (needs a bench
number, listed in §7). Nothing here has been run through ngspice — no
sky130 toolchain was available where this was written. This file
supersedes the flat "1 kV/pA / SNR>50dB / <100ns / 87µW" success-criteria
block from the original brief; that block is a placeholder template, not a
reference design — see §0.

## 0. Changelog — what this supersedes and why

The original L1 brief specified a single 5 kHz TIA meant to serve both the
PPG measurement and a correlator verifying an LED perturbation at
500 kHz–1 MHz. That's physically impossible: a 5 kHz-bandwidth path
attenuates a 500 kHz–1 MHz signal by ≥80 dB (2+ decades past the pole,
rolling off at ≥40 dB/decade) — the correlator would see essentially
nothing. See [`TIA-DESIGN.md`](TIA-DESIGN.md) for the original slow-path
design and its own flagged contradiction (1 GΩ Rf's own thermal noise
already exceeds the stated 100 µV / 50 dB noise target, independent of
this bandwidth problem).

Also superseded: the "SNR > 50 dB" and "<500 ns latency" targets in the
original brief were invented placeholders with no measurement or
derivation behind them. Replaced below with a Pd/Pfa target derived from
the actual decision-rate and matched-filter math (§6), and a functional
timing spec derived from the real 100 µs sample period (§7).

## 1. Architecture decision: dual-path, shared input buffer

**Decision driver is latency, not security.** Optical injection is
broadband — an attacker can modulate a light source at MHz rates trivially,
so putting the challenge out-of-band buys no security margin by itself;
the security property here comes from code unpredictability (LFSR reseed
per sample), not frequency placement. The reason a single 5 kHz path can't
work is purely functional: **[DERIVED]**

```
chip rate = 64-128 chips / 100 us sample period = 0.64-1.28 Mchip/s
5 kHz path throughput cap ~= 5 kchip/s
decision latency at 5 kchip/s for 64-128 chips = 13-26 ms
                                                = 130-260 sample periods late
```

A correlator that produces its answer 130+ samples after the sample it's
gating is useless for a per-sample reject decision. Option (b) — folding
the perturbation into the PPG band and separating by code — doesn't fix
this; it still needs enough instantaneous bandwidth to resolve ~1 Mchip/s
transitions, which is the same requirement dual-path exists to satisfy.
(b) also structurally cannot produce a per-sample flag inside one 5 kHz
path regardless of code design.

**Structure chosen: one shared low-noise input buffer** fixing the
photodiode node's impedance, fanned out into two independent gain/filter
paths — not two competing shunt-feedback TIAs sharing the virtual-ground
node directly. Two independent feedback loops on the same node fight each
other at low frequency (both present low impedance there, splitting PPG
signal current unpredictably between paths); a shared buffer avoids that
by giving only one loop control of the input node.

```
                         +---> [slow TIA, Rf=1G, 5kHz]  --> PPG output
photodiode --> [buffer] -+
                         +---> [wideband TIA, Rf~72k, 1MHz] --> correlator
```

## 2. Path A — PPG (slow), unchanged

Full derivation in [`TIA-DESIGN.md`](TIA-DESIGN.md). Summary:
Rf = 1 GΩ (pseudo-resistor) **[DERIVED, TIA-DESIGN.md §5]**, GBW ≈ 1.9 MHz,
f_-3dB ≈ 5 kHz, ~87 µW. That doc's own noise-budget contradiction (§0/§4
there) stands: Rf's thermal noise alone (~360 µV RMS out) exceeds the
100 µV target regardless of anything done to the wideband path. Not
re-litigated here.

## 3. Path B — wideband / perturbation, new **[DERIVED]**

Same Graeme relation used throughout this project:
`f_-3dB ≈ sqrt(GBW / (2*pi*Rf*Cin))`, Cin ≈ 11 pF (10 pF photodiode Cj +
~1 pF shared-buffer input cap).

Target BW = 1 MHz (covers the stated 500 kHz–1 MHz / 0.64–1.28 Mchip/s
range with some margin at the low end, marginal at the top — see caveat
below).

| Parameter | Value | Basis |
|---|---|---|
| Rf_wide | 72.4 kΩ | solved from f_-3dB=1MHz, GBW=5MHz, Cin=11pF |
| GBW | 5 MHz | chosen so required gm (~50 µS) matches Path A's existing bias current, no extra power needed |
| Cc | 1.59 pF | `Cc = gm/(2*pi*GBW)` |
| Cf (explicit) | ~70 fF | `Cf = sqrt(Cin/(2*pi*Rf*GBW))`, conservative round number |
| Bias current | ~8 µA tail (same topology as Path A stage 1) | gm match, see above |
| Estimated power | ~87 µW (comparable to Path A) | same bias currents, smaller Cc does the BW work, not more current |

**Caveat, flagged not resolved**: at the top of the chip-rate range
(1.28 Mchip/s), a 1 MHz -3dB path may under-resolve chip transitions
(rule of thumb wants BW >= chip rate for low ISI). A margin option exists
(drop Rf_wide to ~32 kΩ for BW=1.5MHz at the same power, costing ~3.5 dB
of SNR) but I'm not making that trade unilaterally — the design is already
marginal at low I_DC (§5), and trading away SNR to fix a BW margin that
may not even be a real problem needs an eye-diagram check in simulation
first, not a guess. **[OPEN — see §7]**

Total dual-path front-end power estimate: ~150–175 µW (Path A + Path B),
not simulated.

## 4. Noise budget, I_DC swept **[DERIVED]**

Two noise terms computed in closed form; a third (op-amp) estimated and
flagged as incomplete; a fourth (ambient) left as a formula pending a
bench number.

**Resistor thermal noise** (frequency-flat): `i_n,R = sqrt(4kT/Rf_wide)`
= sqrt(1.656e-20 / 72400) = **478 fA/sqrt(Hz)**, constant vs. I_DC.

**Shot noise** from the DC photocurrent: `i_n,shot = sqrt(2*q*I_DC)`.

| I_DC | i_n,shot | i_n,total = sqrt(i_n,R^2 + i_n,shot^2) | dominant term |
|---|---|---|---|
| 10 nA | 56.6 fA/sqrt(Hz) | 481.3 fA/sqrt(Hz) | thermal (8.4x) |
| 30 nA | 98.0 fA/sqrt(Hz) | 487.9 fA/sqrt(Hz) | thermal |
| 100 nA | 179 fA/sqrt(Hz) | 510.4 fA/sqrt(Hz) | thermal (2.7x) |
| 300 nA | 310 fA/sqrt(Hz) | 569.7 fA/sqrt(Hz) | thermal, narrowing |
| **713 nA** | **478 fA/sqrt(Hz)** | — | **crossover** |
| 1 uA | 566 fA/sqrt(Hz) | 740.8 fA/sqrt(Hz) | shot (1.2x) |

Resistor thermal noise dominates across nearly the entire 10 nA–1 µA
range; shot noise only overtakes it above **I_DC ≈ 713 nA**, near the top
of the stated range.

**Op-amp input-referred noise, referred to input current** — estimated,
**not** included in the table above. en ≈ 32 nV/√Hz (same topology/bias as
Path A). Referred through the feedback network: flat at low frequency
(≈ en/Rf_wide ≈ 448 fA/√Hz below the ~200 kHz corner `1/(2*pi*Rf*Cin)`),
then **rising with frequency** above that corner (≈ en·2πf·Cin), reaching
an estimated ~2.2 pA/√Hz near 1 MHz — likely exceeding both resistor and
shot noise near the top of the code band. This means §5's SNR numbers are
**optimistic at the high-chip-rate end of the integration window**. A
correct number requires ngspice's `.noise` analysis integrating the real
PSD shape, not this flat-noise hand approximation. **[UNMEASURED /
requires simulation]**

**Ambient-light shot noise**: `i_n,amb = sqrt(2*q*I_amb)`, same form as
the DC term. **I_amb is UNMEASURED** — depends on optical
filtering/shielding not yet specified. Important: DC-subtraction/chopping
cancels ambient's mean current, not its shot noise, which adds in
quadrature regardless of chopping. If unfiltered ambient current is
comparable to or exceeds I_DC, this term could dominate over both terms
in the table above. **Needs a bench number alongside I_DC.**

## 5. SNR vs. I_DC at T_int = 100 µs **[DERIVED]**

Coherent (matched-filter) correlation over one sample period, boxcar
integration collapses the noise bandwidth to `B_eq = 1/(2*T_int)`, full
coherent signal gain:

```
SNR_linear(T_int) = (I_pert / i_n,total) * sqrt(2*T_int)
T_int = 100us  =>  sqrt(2*1e-4) = 0.01414
I_pert = m * I_DC   (m = perfusion index, 0.5%-2%)
```

(Uses only the resistor+shot noise floor from §4 — see the op-amp-noise
caveat there; real numbers are somewhat lower, especially at low I_DC
where margin is already thin.)

| I_DC | I_pert (m=2%) | SNR, m=2% | I_pert (m=0.5%) | SNR, m=0.5% |
|---|---|---|---|---|
| 10 nA | 0.2 nA | 15.4 dB | 0.05 nA | 3.3 dB |
| 30 nA | 0.6 nA | 24.8 dB | 0.15 nA | 12.8 dB |
| 100 nA | 2 nA | 34.9 dB | 0.5 nA | 22.8 dB |
| 300 nA | 6 nA | 43.5 dB | 1.5 nA | 31.4 dB |
| 1 uA | 20 nA | 51.6 dB | 5 nA | 39.6 dB |

## 6. Detection target: Pd/Pfa, derived, and correlator threshold **[DERIVED]**

Replaces "SNR > 50 dB." At 10,000 decisions/second (100 µs period), a
per-decision Pfa near typical detection-theory defaults (1e-3, 1e-6)
produces multiple false flags per second — unusable for a security gate.
For aggregate session false-accept probability to stay low across ~10^5
decisions, per-decision **Pfa = 1e-8** is the right order of magnitude. On
the miss side, a missed detection drops a legitimate sample; capping that
at ~0.1%: **Pd = 99.9% (Pmd = 1e-3)**.

Standard coherent detection in AWGN: `Pd = Q(Q^-1(Pfa) - SNR_linear)`.
Solving for required SNR:

```
SNR_required = Q^-1(Pfa) + Q^-1(Pmd) = Q^-1(1e-8) + Q^-1(1e-3)
             = 5.61 + 3.09 = 8.70 (linear) = 18.8 dB
```

**Correlator threshold**: set at **η = 5.61 × σ_n** (5.61 standard
deviations above the noise floor). This gives Pfa = 1e-8 by construction,
independent of I_DC. Pd = 99.9% then requires the actual signal to sit at
least 3.09σ_n above that threshold — i.e. total SNR ≥ 8.70 (18.8 dB).

**Checked against §5's table (18.8 dB bar, resistor+shot noise only —
optimistic per the op-amp caveat in §4):**

| | m = 2% | m = 0.5% |
|---|---|---|
| Crossover I_DC | ≈ 15 nA | ≈ 60 nA |
| Below crossover | fails (10 nA: 15.4 dB) | fails (10 nA, 30 nA: 3.3, 12.8 dB) |
| Above crossover | passes, growing margin | passes, growing margin |

**Verdict**: across the stated 10 nA–1 µA range, the design closes
everywhere except the bottom of the range combined with low perfusion —
specifically it fails at I_DC = 10 nA regardless of perfusion index, and
fails up to ~60 nA at the low (0.5%) end of perfusion index. Treat these
crossover numbers as an optimistic floor, not a guarantee, until the
op-amp noise term is properly integrated in simulation.

## 7. Flag timing spec **[DERIVED from stated sample period]**

No absolute latency number (the earlier <500 ns figure is dropped, not
replaced with another guess). Spec is functional: **the decision for
sample N is available within one 100 µs sample period; firmware rejects
sample N before it enters the buffer.** This constrains the digital
comparator to resolve within the same 100 µs window used for the
correlator's integration — effectively zero added pipeline latency beyond
the correlation window itself.

## 8. Open items — what's UNMEASURED or still a design choice

- **I_DC** — real value TBD on the bench. Every SNR/margin number in §5–6
  is a function of it; replace and re-run once measured.
- **I_amb** (ambient photocurrent / shot noise) — needs bench
  characterization or an optical-filter spec; currently a formula with no
  number (§4).
- **Op-amp noise, properly integrated** — §4's flat-noise approximation is
  optimistic at high frequency; needs a real ngspice `.noise` sweep once
  the toolchain is available.
- **Rf_wide vs. BW_wide trade at the top of the chip-rate range (§3)** —
  open, not resolved. Needs an eye-diagram/ISI check in time-domain
  simulation before deciding whether to trade SNR margin for bandwidth
  margin.
- **Perfusion index (m)** — used 0.5%/2% as the stated bounds; real
  distribution depends on sensor site/population, not measured here.

## 9. Traceability quick-reference

| Number | Value | Source |
|---|---|---|
| Chip rate | 0.64–1.28 Mchip/s | given (64-128 chips / 100us) |
| Dual-path decision | shared buffer, not competing TIAs | §1, latency derivation |
| Rf_wide | 72.4 kΩ | §3, Graeme relation |
| BW_wide | 1 MHz | §3, design target (open re: top-of-range margin) |
| i_n,R | 478 fA/√Hz | §4, `sqrt(4kT/Rf_wide)` |
| i_n,shot(I_DC) | table | §4, `sqrt(2*q*I_DC)` |
| i_n,amb | — | §4, UNMEASURED |
| SNR(I_DC, m, T_int=100us) | table | §5, coherent-integration derivation |
| Pfa target | 1e-8 | §6, decision-rate argument |
| Pd target | 99.9% | §6, sample-yield argument |
| Correlator threshold | 5.61σ_n | §6, `Q^-1(Pfa)` |
| SNR required | 18.8 dB | §6, `Q^-1(Pfa)+Q^-1(Pmd)` |
| I_DC crossover (m=2%) | ≈15 nA | §6, table vs. threshold |
| I_DC crossover (m=0.5%) | ≈60 nA | §6, table vs. threshold |
| Flag latency | 1 sample period (100µs), functional | §7 |
