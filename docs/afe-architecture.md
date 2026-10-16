# TrustSense Layer 1 — AFE Architecture Spec

> **Current status: see [`STATUS.md`](STATUS.md).** §3–§6 below are the
> pre-simulation hand analysis; simulated results are in §11–§21 and several
> of the numbers here were superseded.

Status (original, v2): derived, unsimulated. Every number below is tagged **[DERIVED §n]**
(traceable to a section in this doc) or **[UNMEASURED]** (needs a bench
number, listed in §9). Nothing here has been run through ngspice — no
sky130 toolchain was available where this was written. This file
supersedes the flat "1 kV/pA / SNR>50dB / <100ns / 87µW" success-criteria
block from the original brief; that block is a placeholder template, not a
reference design — see §0.

## 0. Changelog

- v1: dual-path via shared buffer decided on latency grounds (5kHz path
  is ~130-260 samples late for a 100us per-sample flag). Wideband path
  sized to Rf_wide=72.4kΩ, BW=1MHz. SNR vs I_DC swept, Pd/Pfa target
  derived (18.8dB / Pfa=1e-8 / Pd=99.9%), correlator threshold = 5.61σ_n.
- **v2 (this version)**: corrected two things in v1's own math.
  (1) N (chip count) does not appear in the SNR formula at all — it was
  being conflated with security margin. Split into two independent
  numbers: Pfa (AWGN, detection-theoretic) vs. 2^-N (attacker guessing,
  cryptographic) — see §1a. Minimum defensible N derived, and it's well
  below the 64-128 chips originally assumed.
  (2) That headroom was spent: minimum N -> minimum chip rate -> minimum
  bandwidth -> **maximum Rf_wide**, recovering real dB of SNR margin
  exactly where the design was failing (§3, §4). Design point updated
  from Rf_wide=72.4kΩ to **314kΩ** (N=48). Old 72.4kΩ numbers are
  superseded but kept in git history (see previous commit), not
  duplicated here.
  Also added: a named clinical limitation (§7), a check on whether
  adaptive LED-wavelength selection reinforces the Rf/N mechanism (§7),
  and an explicit peak-vs-RMS statement for I_pert (§8).

## 1. Architecture decision: dual-path, shared input buffer

**Decision driver is latency, not security.** Optical injection is
broadband — an attacker can modulate a light source at MHz rates
trivially, so out-of-band placement alone buys no security margin. The
reason a single 5 kHz path can't work is purely functional: **[DERIVED]**

```
chip rate = N chips / 100us sample period
5 kHz path throughput cap ~= 5 kchip/s
at N=64-128: decision latency = 13-26 ms = 130-260 sample periods late
```

A correlator producing its answer 130+ samples after the sample it's
gating is useless for a per-sample reject decision. Folding the
perturbation into the PPG band (option b, previous turn) doesn't fix
this — it still needs the same instantaneous bandwidth to resolve
chip-rate transitions, and structurally cannot produce a per-sample flag
inside one 5 kHz path regardless of code design.

**Structure: one shared low-noise input buffer** fixing the photodiode
node's impedance, fanned out into two independent gain/filter paths —
not two competing shunt-feedback TIAs on the same node (which would fight
over signal current at low frequency; see previous turn for why).

```
                         +---> [slow TIA, Rf=1G, 5kHz]  --> PPG output
photodiode --> [buffer] -+
                         +---> [wideband TIA, Rf=314k, 480kHz] --> correlator
```

## 1a. Security model: two independent numbers, not one **[DERIVED]**

The SNR formula used throughout (§4) is `(I_pert/i_n)*sqrt(2*T_int)` — T_int
appears, N (chip count) does not. This is a real, general property of
coherent/matched-filter detection: rejecting Gaussian noise depends on
integrated signal energy over a fixed duration, not on how many discrete
chips subdivide that duration. **Integration time buys nothing against an
attacker who isn't noise.**

Two independent numbers, not one:

- **Pfa = 1e-8** (§6): probability random noise accidentally crosses the
  detection threshold and reads as a valid code. This is what the AWGN
  derivation in §6 covers, and what T_int/SNR determine.
- **2^-N**: probability an attacker who does not know the code guesses it
  correctly. Combinatorial, not statistical. An attacker with unlimited
  SNR still only guesses right 1 time in 2^N, because the AWGN model has
  nothing to say about an adversary that isn't noise.

**Caveat on 2^-N, not resolved here**: this is only the right formula if N
chips carry N independent bits of entropy. If the code generator is a
*classical linear-feedback* shift register, real guess-resistance is
bounded by the register length L (Berlekamp-Massey reconstructs an L-bit
LFSR's full state, taps included, from 2L observed output chips, in
polynomial time) — not by chip count N, and typically L << N. Once an
attacker has observed 2L consecutive chips from *any* sample, they predict
every future output of that register; chip count buys nothing at that
point. Per-sample reseeding only rescues this if the reseed value itself
comes from a source the attacker cannot predict (a real TRNG/CSPRNG) —
that is a separate design question outside the AFE. **This needs a
cryptographer's review of the actual generator, not a derivation from
noise physics.**

**Minimum N, assuming ideal (CSPRNG-quality) generation**: threat model is
an attacker guessing blind once per 100us decision, continuously, for a
session. For aggregate break probability < 1e-6:

```
N_min = log2(attempts_per_session) + log2(1/target)
1-minute session (6e5 attempts):    N_min = 39.1 -> ~40 bits
8-hour session   (2.88e8 attempts): N_min = 48.0 -> ~48 bits
```

**Recommendation: N = 48 bits.** Covers multi-hour continuous monitoring
at 1e-6 aggregate break probability, and is well below the 64-128 chips
originally assumed — that headroom is spent in §3.

## 2. Path A — PPG (slow), unchanged

Full derivation in [`TIA-DESIGN.md`](TIA-DESIGN.md). Rf = 1 GΩ
(pseudo-resistor), GBW ≈ 1.9 MHz, f_-3dB ≈ 5 kHz, ~87 µW. That doc's own
noise-budget contradiction stands (Rf's thermal noise alone exceeds the
100 µV target) — not re-litigated here.

## 3. Path B — wideband / perturbation, resized for N=48 **[DERIVED]**

Same Graeme relation as before: `f_-3dB ≈ sqrt(GBW / (2*pi*Rf*Cin))`,
Cin ≈ 11 pF. Bandwidth target now driven by the *minimum defensible* chip
rate (§1a), not the originally-assumed 0.6-1.3 Mchip/s — running the
relation backwards: minimum N -> minimum chip rate -> minimum bandwidth ->
maximum Rf, holding GBW=5MHz fixed for a controlled comparison against the
old design point.

| N | chip rate | BW target | Rf_wide | i_n,R (thermal) | i_n,total @ I_DC=10nA | dB recovered vs. old (72.4kΩ) |
|---|---|---|---|---|---|---|
| 40 | 400 kchip/s | 400 kHz | 452 kΩ | 191.4 fA/√Hz | 199.6 fA/√Hz | +7.64 dB |
| **48 (chosen)** | **480 kchip/s** | **480 kHz** | **314 kΩ** | **229.6 fA/√Hz** | **236.5 fA/√Hz** | **+6.17 dB** |
| 64 | 640 kchip/s | 640 kHz | 176.7 kΩ | 306.1 fA/√Hz | 311.3 fA/√Hz | +3.79 dB |
| 96 | 960 kchip/s | 960 kHz | 78.5 kΩ | 459.3 fA/√Hz | 462.8 fA/√Hz | +0.34 dB |
| 128 | 1.28 Mchip/s | 1.28 MHz | 44.2 kΩ | 612.1 fA/√Hz | 614.8 fA/√Hz | **-2.13 dB (worse)** |

Notable: N=128 (the original upper bound) is *worse* than the old 72.4kΩ
design point — that design was already implicitly under-margined against
its own stated upper chip rate (flagged, unresolved, in the previous
version of this doc).

**Chosen design point: N=48, Rf_wide = 314 kΩ, BW = 480 kHz.**
Cc, GBW, bias current unchanged in form from the previous design (same
Graeme-relation approach, same ~87 µW class) — not re-derived component by
component here; treat as a placeholder pending the same device-level pass
done for the 72.4kΩ point, still unsimulated either way.

**Open, not resolved**: BW-vs-chip-rate margin at the top of *whatever*
range is finally chosen (same open item as v1, now at 480kHz/480kchip/s
instead of 1MHz/1.28Mchip/s) — still wants an eye-diagram/ISI check in
time-domain simulation before being trusted.

## 4. Noise budget, I_DC swept, N=48 design point **[DERIVED]**

`i_n,R = sqrt(4kT/Rf_wide) = sqrt(1.656e-20 / 314000) = 229.6 fA/sqrt(Hz)`
(down from 478 fA/√Hz at the old 72.4kΩ point), constant vs. I_DC.

`i_n,shot = sqrt(2*q*I_DC)`, unchanged formula, unchanged by Rf choice.

| I_DC | i_n,shot | i_n,total | dominant term |
|---|---|---|---|
| 10 nA | 56.6 fA/√Hz | 236.5 fA/√Hz | thermal (4.2x) |
| 30 nA | 98.0 fA/√Hz | 249.6 fA/√Hz | thermal |
| 100 nA | 179 fA/√Hz | 291.1 fA/√Hz | thermal (1.6x) |
| **165 nA** | **229.6 fA/√Hz** | — | **crossover (moved down from 713nA)** |
| 300 nA | 310 fA/√Hz | 385.8 fA/√Hz | shot |
| 1 uA | 566 fA/√Hz | 610.8 fA/√Hz | shot (1.85x) |

Lowering the noise floor pulls the thermal/shot crossover down from
713 nA (old design) to **≈165 nA** — expected, since there's less thermal
noise for shot noise to out-run.

Op-amp noise caveat from v1 still applies unchanged: frequency-dependent,
flat below ~200kHz, rising above it, likely dominant near the top of the
code band. Not included in the table above; makes it optimistic at the
high-chip-rate end. Still **[UNMEASURED / requires simulation]**.

Ambient-light shot noise (`i_n,amb = sqrt(2*q*I_amb)`) still
**[UNMEASURED]** — noted as your first bench measurement (§9). Does not
cancel via DC chopping (only the mean cancels, not the shot noise).

## 5. SNR vs. I_DC at T_int = 100 µs, N=48 design point **[DERIVED]**

Same derivation as v1 (coherent boxcar integration, `SNR_linear =
(I_pert/i_n,total) * sqrt(2*T_int)`, T_int=100us), re-run against the new
noise floor. I_pert = m*I_DC, peak chip amplitude — see §8 for why peak=RMS
here and no correction factor is needed.

| I_DC | SNR, m=2% | SNR, m=0.5% |
|---|---|---|
| 10 nA | 21.6 dB | 9.5 dB |
| 30 nA | 30.6 dB | 18.6 dB |
| 100 nA | 39.8 dB | 27.7 dB |
| 300 nA | 46.9 dB | 34.8 dB |
| 1 uA | 53.3 dB | 41.3 dB |

## 6. Detection target: Pd/Pfa, threshold — unchanged math, re-checked against new table

Detection-theory derivation is independent of Rf/N choice (§1a already
separated it from the security question). Unchanged from v1:

```
Pfa = 1e-8, Pd = 99.9% (Pmd = 1e-3)
SNR_required = Q^-1(1e-8) + Q^-1(1e-3) = 5.61 + 3.09 = 8.70 (linear) = 18.8 dB
Threshold: eta = 5.61 * sigma_n  (Pfa=1e-8 by construction)
```

**Checked against §5's new table:**

| | m = 2% | m = 0.5% |
|---|---|---|
| Old crossover (Rf=72.4kΩ) | ≈15 nA | ≈60 nA |
| **New crossover (Rf=314kΩ, N=48)** | **passes even at 10 nA (21.6dB)** | **≈31 nA** |

**Verdict, updated**: at m=2% the design now closes across the *entire*
stated 10nA-1uA range. At m=0.5% (low perfusion, the harder case) it
still fails below ~31nA — improved from ~60nA, not eliminated. Still
optimistic per the op-amp-noise caveat in §4.

## 7. Clinical limitation, and whether wavelength selection reinforces the fix

**Named limitation**: Low I_DC + low perfusion = higher melanin, poor
peripheral perfusion, cold extremities. **The verifier fails on exactly
the patients who are already underserved by pulse oximetry.**

**Does adaptive per-patient LED wavelength selection (maximizing I_DC for
that patient) also raise verifier SNR — and does it reinforce §3's fix?**
Yes, and specifically in the regime that's failing. Below the thermal/shot
crossover (§4, now ≈165nA — most of the failing range), noise is
essentially constant, so `SNR ≈ m*I_DC/i_n,R` — **linear** in I_DC. A k×
improvement in I_DC from choosing a better-penetrating wavelength for that
patient's skin buys a full `20*log10(k)` dB, not the diminished
`10*log10(k)` you'd get once shot noise dominates (sqrt(I_DC) regime,
I_DC above crossover). **The two mechanisms compound in the same
regime, for the same underlying reason** — both work by raising SNR
before shot noise sets a sub-linear ceiling.

**Illustrative only — no validated k-factor for this system, not a
physiological measurement**: at the N=48 design point, worst case
(I_DC=10nA, m=0.5%) sits at 9.5dB, needs 18.8dB. k≈3.2x improvement in
I_DC (10nA->32nA) from wavelength selection alone closes it to the
threshold; k≈5x gives ~2.4dB of margin. Real k depends on the wavelength
subset and skin-tone data this doc doesn't have — replace this estimate
with the number from the separate provisional.

## 8. Signal convention: I_pert is peak, and peak=RMS here — checked, not assumed

I_pert has been used as **peak chip amplitude** throughout (`I_pert =
m*I_DC`), matching how it was originally defined. For a bipolar (±1)
square-wave chip sequence, peak = RMS — unlike a sine wave (RMS =
peak/sqrt(2), a real 3dB gap), a square wave sits at constant magnitude at
every instant, so there's no averaging-down of its power.

Checked via independent derivation, not assumed: matched-filter SNR from
signal energy for a constant-amplitude chip sequence
(`E_s = I_pert^2 * T_int`, standard `2E/N0` result) reproduces
`(I_pert/i_n)*sqrt(2*T_int)` exactly — the same formula already in use in
§5. **No hidden 3dB in the numbers reported.** If the perturbation were
ever a sinusoidal dither instead of a chip code, this would overstate SNR
by 3dB and I_pert would need reinterpreting as RMS (=peak/sqrt(2)) —
flagged as a future trap, not a live problem given the chip-code design.

## 9. Open items — what's UNMEASURED or still a design choice

- **I_DC** — UNMEASURED, real value TBD on the bench. Every SNR/margin
  number in §5-7 is a function of it.
- **I_amb** (ambient photocurrent / shot noise) — UNMEASURED, your first
  bench measurement. Formula in §4, no number yet.
- **Op-amp noise, properly integrated** — §4's flat-noise approximation is
  optimistic at high frequency; needs a real ngspice `.noise` sweep.
- **Code generator entropy source** (§1a) — is it a plain LFSR
  (Berlekamp-Massey-breakable, real security = 2^-L not 2^-N) or a
  CSPRNG-quality generator (2^-N valid)? Needs a cryptographer, not a
  noise-physics derivation.
- **N=48 chosen, not yet confirmed** — pending your sign-off; §3's sweep
  table gives the tradeoff if a different point is preferred.
- **Wavelength k-factor (§7)** — illustrative only, replace with the
  number from the separate provisional.
- **Rf_wide=314kΩ device-level design** (Cc, bias currents, device sizes)
  — not yet re-derived component-by-component the way the 72.4kΩ point
  was in the previous turn; same Graeme-relation approach applies, still
  unsimulated either way.
- **BW-vs-chip-rate margin at N=48's 480kHz/480kchip/s** — same open item
  as v1, moved to a new operating point, still wants an eye-diagram check.

## 10. Traceability quick-reference

| Number | Value | Source |
|---|---|---|
| Dual-path decision | shared buffer, latency-driven | §1 |
| Pfa vs 2^-N split | independent axes | §1a |
| N_min (1-min session) | ~40 bits | §1a |
| **N recommended** | **48 bits** | §1a, 8hr-session target |
| LFSR entropy caveat | 2^-L not 2^-N if plain LFSR | §1a, UNRESOLVED |
| Rf_wide (new) | 314 kΩ | §3, backwards from N=48 |
| BW_wide (new) | 480 kHz | §3 |
| i_n,R (new) | 229.6 fA/√Hz | §4 |
| thermal/shot crossover (new) | ≈165 nA | §4 |
| dB recovered @ I_DC=10nA | +6.17 dB | §3 sweep table |
| SNR(I_DC, m, N=48) | table | §5 |
| SNR required | 18.8 dB (unchanged) | §6 |
| Crossover, m=2% (new) | closes across full range | §6 |
| Crossover, m=0.5% (new) | ≈31 nA | §6 |
| Clinical limitation | named, verbatim | §7 |
| Wavelength reinforcement | yes, compounds in thermal regime | §7, illustrative k only |
| I_pert convention | peak = RMS (square code) | §8, checked not assumed |

## 11. Simulation check of this spec (2026-10-15)

First ngspice runs exist now (details in [`TIA-DESIGN.md`](TIA-DESIGN.md) §9–§10).
They change the picture in §3–§6:

- Rf_wide = 314 kΩ at 483 kHz is achievable, but the amp needs **169 µW**, not
  the "87 µW class" assumed in §3.
- Measured input-referred noise is **363–391 fA/√Hz** in the chip-rate band
  (**~724 fA/√Hz** near 316 kHz), vs the 236 fA/√Hz in §4. That is a 3.7 dB
  (low band) to ~10 dB (316 kHz) SNR loss vs §5. At m = 2 %, I_DC = 10 nA the
  §5 figure of 21.6 dB drops to roughly 17–18 dB at 100 kHz-band noise, below
  the 18.8 dB required in §6 (hand-adjusted from the §5 formula, not
  re-simulated with a coherent-detection testbench).
- The "shared input buffer" of §1 is **not designed and not simulated**. A
  source-follower buffer cannot feed a shunt-feedback TIA (which needs its
  own virtual ground at the photodiode node), so the two-path split needs an
  explicit topology decision (e.g. current-mode splitting through a
  regulated cascode / current mirror). Open.

## 12. Shared input: regulated-cascode + current-mirror split (simulated 2026-10-16)

Netlist: `simulation/spice/afe_front.spice`, generated by
`simulation/spice/tools/gen_afe.py` from the two TIA netlists (AC/noise
driver: `tools/afe_ac.py`). Topology: photodiode node `x` held low-Z by a PMOS
regulated cascode (Mc, NMOS booster Mb, bias Ib), photocurrent sinks into an
NMOS mirror diode Mm, copied 1:1 (Mo1, Mo2) into the wideband and slow TIAs.

**Bugs found while bringing it up** (all in the first draft of this topology):
the cascode must be a **PMOS** (current flows into `x` and onward), and the
first NMOS version was positive feedback and latched `x` at 14 V.

**Result 1, a fixed bias current through the mirror is mandatory.** With no
bias, input-node gm scales with photocurrent: bandwidth was 7.4 kHz at
I_DC = 10 nA and 23 Hz at 10 pA. Holding IBX through Mc/Mm fixes the bandwidth
but injects IBX into both TIA inputs, which must be cancelled there.

**Result 2, wideband path works but pays in noise vs bandwidth** (I_DC = 10 nA,
Rf = 314 kΩ confirmed at 314 kΩ, IBX cancelled at the TIA input; IBX and
Icomp are **ideal current sources**, not yet real PMOS mirrors):

| IBX | -3 dB BW | input-referred noise @100 kHz | vs 236 fA/√Hz budget |
|---|---|---|---|
| 100 nA | 62 kHz | 418 fA/√Hz | 1.8x |
| 300 nA | 140 kHz | 598 fA/√Hz | 2.5x |
| 1 µA | 256 kHz | 996 fA/√Hz | 4.2x |
| 3 µA | 321 kHz | 1869 fA/√Hz | 7.9x |

None reaches the 480 kHz target. At 1 µA the noise is ~12 dB over the §4
budget (mirror-device thermal noise, two devices in the path), so the §6
requirement (18.8 dB at m = 2 %, I_DC = 10 nA) is **not met** by this
front end; a standalone wideband TIA (TIA-DESIGN §10) is ~4 dB over budget.
Mitigations not tried: source degeneration in the mirror, a cascoded or
lower-gm mirror, taking the wideband copy at gain < 1.

**Result 3, the slow (PPG) path is not working in this configuration.** At
1 GΩ any DC photocurrent (nA-µA) saturates the TIA (10 nA × 1 GΩ = 10 V),
independent of the split topology. An ideal `Icomp` was used to cancel it
and the slow path still did not reach a valid gain (railed amplifier,
~2 kΩ measured instead of 1 GΩ), so slow-path numbers from `afe_front.spice`
should be ignored. A real **DC-cancellation servo** for the slow path is the
next block to design; the cancellation current has to be accurate to well
under 1 nA.

**Not done:** real PMOS bias/cancel mirrors (IBX is an ideal source),
mirror-mismatch / temperature check, front-end noise breakdown by device,
and a coherent-detection (chip-code) simulation of the end-to-end SNR.

## 13. Slow-path DC-cancellation servo (simulated 2026-10-16)

Replaces the ideal `Icomp` of §12. In `afe_front.spice` (generated by
`tools/gen_afe.py`, driver `tools/afe_servo_tran.py`): a real thick-oxide PMOS
current source `Msv` (W=100 µm, L=2 µm) injects into the slow-TIA input the
DC that the mirror sinks (IBX + I_DC), driven by a **behavioral** integrator
(`Bint`/`Cint`) that watches `s_out` against VCM.

**Why behavioral:** with Rf = 1 GΩ a ~0.1 Hz servo corner needs
ω_u = gm_i·gm_p·Rf/C ≈ 1 rad/s, i.e. tens of nF of on-chip capacitance with a
real gm-C stage. The real implementation has to be digital-assisted: ADC on
the slow path output → digital integrator → current DAC. `Bint` models that
loop; it is **not** a circuit design for the DAC/ADC.

**What the transient (power-up from 0 V, 8 s) shows:**

| I_DC | input `s_in` | `s_out` settled | 10 pA test pulse |
|---|---|---|---|
| 100 nA | 1.6504 V (virtual ground) | 1.648–1.650 V (within ~3 mV of VCM) | ≈ +10 mV step (1 GΩ) |
| 1 µA | 1.6504 V | 1.650–1.654 V | ≈ +10 mV step |

- Pulse droop ≈ 4 mV of 10 mV over 1 s (about a 2 s time constant, high-pass
  corner ≈ 0.08 Hz): inside a PPG-friendly range, set by `GMI/CINT`.
- Overall slow-path polarity is non-inverting (the mirror flips the TIA's
  sign).

**Things the sim made me add (each was a real failure):**
1. Servo gate cap referenced to `vdpwr`, not ground; otherwise `Msv` powers up
   fully on and rails the input at 3.3 V.
2. **Coarse acquisition**: integrator gain ×1e5 while |s_out − VCM| > 0.15 V.
   With only the slow fine loop the amplifier stays railed for minutes (a
   10-90 % time constant of ~1 s per 5 µV of gate movement). Lock takes ≈ 1.5 s.
3. `.option gmin=1e-17`: the default 1e-12 S leaks more from the floating
   integrator node than the fine loop drives, and stalls `s_out` ~0.15 V
   off-center. This is a simulator artifact, but a real floating node would
   have similar leakage limits (use the digital loop).
4. The `.op` solution of this circuit is a latched wrong state at any I_DC
   (`.nodeset` does not rescue it); only the power-up **transient** gives the
   intended state. Bench/silicon start-up behavior is therefore not guaranteed.

**Noise: my first estimate here (shot-noise-level, ~18–25 fA/√Hz from `Msv`) was wrong by ~1000x. See §14 for the simulation.**

## 14. Slow-path noise, simulated with the mirror and servo in place (2026-10-16)

Method (`tools/afe_slow_noise.py`): the behavioral servo is replaced by a fixed
`Msv` gate voltage bisected so `s_out` = VCM (the circuit has a latched wrong
`.op` state, and the in-band window is only tens of µV wide); `Msv`'s own
device noise is kept, the digital loop's is not. Input-referred noise =
output noise / measured 1 GΩ gain. I_DC = 100 nA.

| IBX | mirror area | density @10 Hz | @100 Hz | @1 kHz | RMS 0.5–100 Hz | RMS 0.5–5 kHz |
|---|---|---|---|---|---|---|
| 100 nA | 1x | 6975 fA/√Hz | 2520 | 861 | 50 pA | 70 pA |
| 300 nA | 1x | 13233 | 4766 | 1583 | 95 pA | 132 pA |
| 1 µA | 1x | 32892 | 11820 | 3835 | 237 pA | 325 pA |
| 3 µA | 1x | 78748 | 28251 | 8687 | 567 pA | 763 pA |
| 100 nA | 4x | 3593 | 1321 | 501 | 26 pA | 38 pA |
| 1 µA | 4x | 18463 | 6659 | 2202 | 133 pA | 184 pA |

Compare: Rf = 1 GΩ thermal noise is **4.07 fA/√Hz** (TIA-DESIGN §4), so the
mirror-split slow path is 200–8000x above it.

**What carries it:**
- **The mirror (Mm, Mo1, Mo2), not the servo.** Quadrupling `Msv`'s area
  (W×4) changes nothing (32.8 vs 32.9 pA/√Hz at 10 Hz); quadrupling the mirror
  area drops it to 18.5 pA/√Hz (≈90 % of the noise power).
- **It is flicker (1/f) noise** scaling with mirror gm: density falls ≈ 1/√f
  (10 Hz → 1 kHz is ÷8.6) and rises roughly in proportion to total mirror
  current (IBX + I_DC). Lowering IBX buys a lot, but not below the floor set by
  I_DC itself, and IBX cannot go low without losing wideband bandwidth
  (§12 table: 62 kHz at 100 nA).
- Whether the HV g5v0d10v5 flicker model is pessimistic is **not checked**
  (no bench or silicon data); treat these as model results.

**Consequences for the slow path (PPG), all at I_DC = 100 nA:** a 1 % AC
modulation is 1 nA; against 50–237 pA RMS (0.5–100 Hz) that is ~26 down to
~13 dB SNR before any further averaging. At low perfusion (I_DC = 10 nA, 1 % =
100 pA) the mirror current is smaller too, but the IBX-set part of the noise
is unchanged, so SNR can fall below 0 dB at IBX = 1 µA. The design target of
the TIA-DESIGN §4 hand estimate (Rf-limited, ~360 µV RMS output) is
irrelevant while the mirror is in the path.

**Options, none simulated yet:**
1. Take the slow path **directly off the photodiode** (own low-impedance
   TIA input, no mirror) and use the mirror/regulated cascode only for the
   wideband path. Removes this noise entirely but needs the photodiode node
   shared between two TIA inputs, i.e. the original contention problem.
2. Bigger mirror area (4x gives ~1.8x less, costs input capacitance and
   wideband BW) and lower IBX.
3. Source-degenerate the mirror.

## 15. Option 1 simulated: slow path direct off the photodiode (2026-10-16)

Netlist `simulation/spice/afe_direct.spice` (generator
`tools/gen_afe_direct.py`, AC/noise driver `tools/afe_direct_noise.py`).
Photodiode node `x` goes straight into the 1 GΩ slow TIA (virtual ground, no
mirror). The wideband path hangs off `x` through a coupling capacitor `Cc`
into the regulated cascode + mirror, biased at the cascode side by IBX, so
**photodiode DC and IBX never touch the slow path or the mirror's DC**. The
slow-path DC cancel is now an **NMOS sink** at `x` (the photocurrent enters
`x`; the previous PMOS source would have added to it). I_DC = 100 nA, IBX =
1 µA. Servo again replaced by a bisected fixed gate voltage for AC/noise.

**Slow path (PPG):**

| Cc | gain @10 Hz | -3 dB | density @10 Hz / 100 Hz / 1 kHz | RMS 0.5–100 Hz |
|---|---|---|---|---|
| 10 pF | 1.00 GΩ | 3.2 kHz | 1144 / 430 / 203 fA/√Hz | 8.3 pA |
| 50 pF | 1.00 GΩ | 2.8 kHz | 1144 / 431 / 230 | 8.3 pA |
| 200 pF | 1.00 GΩ | 1.6 kHz | 1145 / 445 / 468 | 8.3 pA |

vs 237 pA RMS with the mirror in the path (IBX = 1 µA, §14): **~29x better**,
and it no longer depends on IBX. Still ~2 orders above the Rf thermal floor
(4 fA/√Hz); the remaining noise is 1/f-shaped (source not isolated: op-amp
and the sink device are candidates). For a 1 % modulation at I_DC = 100 nA
(1 nA) that is ~41 dB SNR in 0.5–100 Hz.

**Node contention (the thing option 1 risked):** signal current at `x` splits
between the slow TIA, `Cj` and the AC-coupled wideband branch.
- Low frequency (PPG band): the wide branch takes 0.1–0.3 % of the current at
  100 Hz, so the slow gain is unaffected (1.00 GΩ).
- Crossover: wide path gain is 94 % of 314 kΩ at 3 kHz while the slow path has
  fallen to 0.46 GΩ there; above 10 kHz the slow path is gone (<4 %).
- At Cc = 200 pF a resonance between `Cc` and the slow TIA's rising input
  impedance gives **+32 % gain peaking near 1 kHz** on the wide path.

**Wideband path, gain as % of 314 kΩ and noise (referred to input at local gain):**

| Cc | 3 kHz | 100 kHz | 316 kHz | 1 MHz | noise @10k / 100k / 316k / 1M (fA/√Hz) |
|---|---|---|---|---|---|
| 10 pF | 27 % | 48 % | 36 % | 12 % | 3488 / 1993 / 2233 / 4593 |
| 50 pF | 94 % | 79 % | 56 % | 15 % | 1957 / 1262 / 1739 / 4373 |
| 200 pF | 103 % | 89 % | 61 % | 15 % | 1736 / 1132 / 1663 / 4343 |

At Cc = 50 pF the wideband -3 dB point is ≈ 280–300 kHz, essentially the
same as the mirror-only front end (§12: 256 kHz at IBX = 1 µA) and noise at
100 kHz is only ~1 dB worse (1262 vs 996 fA/√Hz). Neither meets the 480 kHz /
236 fA/√Hz targets, but **option 1 does not make the wideband path
measurably worse while making the slow path ~29x quieter.**

**Cost / caveats:**
- **Cc area.** ~2 fF/µm² MiM puts 50 pF at ~25,000 µm² (about a third of a
  334×225 µm tile); 200 pF (~100,000 µm²) does not fit. Cc = 50 pF is the
  practical choice; Cc = 10 pF loses half the wideband gain.
- IBX and the wideband-input cancel `Icompw` are still **ideal current
  sources**; the DC servo is still behavioral; the slow-path `.op` still
  latches without the fixed-gate method (start-up not guaranteed).
- Only I_DC = 100 nA and IBX = 1 µA were simulated. I_DC dependence and an
  IBX sweep for this topology were not run; the slow-path noise is expected
  to be insensitive to IBX, the wideband noise sensitive (as in §12).
- No coherent-detection (chip-code) simulation of the end-to-end SNR yet.

## 16. End-to-end coherent detection, option-1 front end (2026-10-17)

Testbench: `simulation/detect/coherent_mc.py`; channel data from ngspice in
`simulation/spice/results/chan_<I_DC>.txt` (extracted by
`simulation/spice/tools/afe_wide_channel.py`); raw output in
`simulation/spice/results/detect_results.txt`.

**Method.** The front end is linear for these signals, so ngspice supplies the
complex wideband response H(f) and the output noise PSD (device noise; I_DC
= 10 n…1 µ, IBX = 1 µA, Cc = 50 pF, servo as a fixed gate bias). A Monte Carlo
then drives random **48-chip** bipolar codes (480 kchip/s, T_int = 100 µs,
peak amplitude m·I_DC) through H(f) with Gaussian noise (SPICE device noise
+ photodiode shot noise 2qI_DC added at the input), 5 consecutive random
symbols per trial so inter-symbol interference is included, and correlates
the middle one with the known code after a fixed receiver delay (0.65 µs,
picked to maximise the mean). Threshold η = 5.61 σ (Pfa = 1e-8 by the
Gaussian tail), 20 000 trials per point. Detection SNR is d = μ/σ₀ with
20·log10(d) quoted; 18.8 dB (d = 8.70) is the §6 requirement for
Pd = 99.9 %.

**Noise-only correlator output is Gaussian where it can be checked:**
kurtosis 3.02–3.11, skew |≤0.06|, P(|z|>3σ) = 0.0027–0.0034 (Gaussian 0.0027).
Tails at 1e-8 cannot be verified by Monte Carlo (needs ~1e9 trials), so Pfa
= 1e-8 rests on the Gaussian-noise assumption, not on measurement.

| I_DC | m = 2 % | m = 1 % | m = 0.5 % |
|---|---|---|---|
| 10 nA | 4.9 dB, Pd 6e-5 | −1.2 dB, Pd 1e-6 | −7.3 dB |
| 30 nA | 14.5 dB, Pd 0.38 | 8.5 dB, Pd 0.002 | 2.4 dB |
| 100 nA | 24.8 dB, Pd ≈ 1 | **18.8 dB, Pd 0.998** | 12.8 dB, Pd 0.11 |
| 300 nA | 34.1 dB, Pd 1 | 28.1 dB | 22.1 dB, Pd 1 |
| 1 µA | 43.9 dB, Pd 1 | 37.9 dB | 31.8 dB |

(Pd at Pfa = 1e-8; empirical Pd from the Monte Carlo agrees with the Gaussian
formula to within trial statistics.)

**Minimum I_DC for Pd ≥ 99.9 % at Pfa = 1e-8** (d is linear in m·I_DC, since
σ₀ is nearly constant at 24–27 µV): **≈ 50 nA at m = 2 %, ≈ 100 nA at
m = 1 %, ≈ 200 nA at m = 0.5 %.**

**Versus the §5/§6 hand budget:** that analysis claimed 21.6 dB at (10 nA,
2 %) and a pass at every I_DC ≥ 10 nA for m = 2 % (≥ 31 nA for m = 0.5 %). The
simulated front end gives 4.9 dB at (10 nA, 2 %), i.e. **~16.7 dB worse**,
and needs ~5x (m = 2 %) to ~6x (m = 0.5 %) more photocurrent. The gap is the
noise: the effective input-referred noise that reproduces the simulated d is
about 1.6 pA/√Hz versus the 0.236 pA/√Hz budget (consistent with the
1.1–1.7 pA/√Hz measured at 100–316 kHz in §15), plus lost matched-filter
gain from the 280–300 kHz channel bandwidth.

**This is a result for the AWGN false-alarm and detection requirement only**
(it says nothing about an adversary), and it still rests on: ideal IBX and
cancel currents, a behavioral servo (fixed gate bias here), tt corner / room
temperature, ideal timing recovery, noise limited to the 3.84 MHz sampling
band, and the Gaussian-tail assumption above.

## 17. Wideband-noise reduction in the option-1 front end (2026-10-17)

Tools: `simulation/spice/tools/wide_noise_sweep.py` (one variant per call),
`make_chan_opt.py` (full-chain channel for the optimised stage); raw sweep
output `simulation/spice/results/wide_noise_sweeps.txt`; final Monte Carlo
`simulation/spice/results_opt/detect_results.txt`.

**Figure of merit.** Detection SNR d = μ/σ₀ for the same 48-chip correlator as
§16, with σ₀ computed analytically from the SPICE output-noise PSD
(σ₀² = (N/N_S²)·∫S_out·D(f)df, rect-chip kernel D) and μ from a noise-free pass
through H(f). Checked against the §16 Monte Carlo on the same channel: σ₀
24.30 vs 24.13 µV, d 17.30 vs 17.45. Quoted as the I_DC needed for
Pd = 99.9 % at Pfa = 1e-8 (d = 8.70) at m = 2 %.

**Where the wideband noise comes from (m = 2 % minimum I_DC, nA):**

| variant | min I_DC | note |
|---|---|---|
| full chain, §15 stage (baseline) | 50.3 | |
| slow path removed | 48.6 | slow path adds only ~3 % |
| mirror area x4 | 39.4 | mirror thermal/flicker is the biggest single term |
| mirror degeneration 20 k / 50 k | 40.7 / 35.2 | |
| IBX 300 nA / 3 µA | 31.2 / 93.6 | gm of the cascode and mirror scales with IBX |
| Mc W x4, wide-TIA bias x2 | 48.9 / 48.7 | **no effect** |
| Cc 100 pF | 45.4 | small gain, large area |

**Findings that changed the design:**
1. **The regulated-cascode booster was not regulating.** In every §12–§16
   run the gate node `gc` sat at ~0 V (Mb pulling it to ground), so the stage
   behaved as a plain common-gate PMOS. A thick-oxide PMOS needs ~1.0 V Vsg
   but `gc` cannot go below 0 V from a ~1.0 V source node, so the loop cannot
   close. Forcing it into regulation (thin-oxide Mc with its own n-well, Mb
   re-sized, booster current raised) gave **worse** results (31–63 nA): the
   booster's bias noise couples into Mc's gate. Removing the booster and
   driving Mc's gate from a fixed voltage reproduces the best result at any
   gate voltage (24.4 nA at Vgc = 0, 0.4 or 0.8 V). The Mb/Ib/Rib/Mc-gate
   network is therefore unnecessary; the earlier "regulated cascode" label in
   §12–§16 was a misdescription.
2. **IBX has an optimum near 300 nA** (100 nA: 30 nA, 300 nA: 24–25 nA, 1 µA:
   27–28 nA with the improved mirror). Too low and the input node (Zin ~ 1/gm)
   is slow, too high and mirror noise rises.
3. **The wide TIA op-amp is not the limiter** (2x bias: no change).

**Optimised stage:** common-gate PMOS Mc (W = 80 µm, L = 1 µm, gate on a
fixed DC voltage), IBX = 300 nA, mirror devices x4 (m = 4) with 200 kΩ source
degeneration each, Cc = 50 pF, wide TIA unchanged (~170 µW total with the
slow path). Analytic minimum I_DC = 22.0 nA (m = 2 %).

**Full Monte Carlo on the optimised stage** (all five I_DC, slow path and
servo-as-fixed-bias included; noise-only correlator kurtosis 3.00–3.03):

| I_DC | m = 2 % | m = 1 % | m = 0.5 % |
|---|---|---|---|
| 10 nA | 11.7 dB, Pd 0.047 | 5.7 dB | −0.4 dB |
| 30 nA | 21.3 dB, Pd 1 | 15.2 dB, Pd 0.56 | 9.2 dB |
| 100 nA | 31.3 dB | 25.3 dB | **19.2 dB, Pd 0.9985** |
| 300 nA | 39.8 dB | 33.8 dB | 27.8 dB |
| 1 µA | 47.8 dB | 41.8 dB | 35.7 dB |

**Minimum I_DC for Pd ≥ 99.9 % at Pfa = 1e-8:** ≈ **24 nA (m = 2 %),
≈ 48 nA (m = 1 %), ≈ 95 nA (m = 0.5 %)**, versus 50 / 100 / 200 nA before: a
**~2.1x improvement** (+6.9 dB SNR at fixed I_DC). The hand budget in §5/§6
(pass at all I_DC ≥ 10 nA for m = 2 %) is still not met: 10 nA / 2 % reaches
11.7 dB, 7 dB short of the 18.8 dB requirement.

**Caveats:** the 480 kHz bandwidth target is still not met (|H| rolls off
earlier; see §15); IBX, the wide-input cancel and the gate bias are ideal
sources; at I_DC = 1 µA the fixed servo bias leaves s_out at 1.70 V (not
1.65), and 300 nA / 100 nA at 1.636 / 1.644 V (the Msv gate voltages were
bisected for the pre-optimisation netlist); tt corner, 27 °C; degeneration
resistors were assumed ideal poly (their thermal noise is in the PSD but
mismatch/area are not evaluated); same Gaussian-noise assumption for Pfa as §16.

## 18. Real PMOS bias mirror replaces the ideal sources (2026-10-17)

The §17 stage used three ideal sources: IBX into the cascode node `xc`, an
equal cancel current into the wideband TIA input `w_in`, and a fixed gate
voltage on `Mc`. In the real stage:
- the **gate "source" is Vgc = 0 V, i.e. a wire to ground** (the booster that
  would have needed a bias was removed in §17), so it needs no circuit;
- IBX and the cancel current come from a **degenerated PMOS mirror**: a
  diode-connected reference PMOS programmed by a resistor to ground (Rref,
  gate filtered by Cref to the supply) and two 1:1 output PMOS (one into `xc`,
  one into `w_in`), all with the same source resistor Rs, W/L = 10/4 µm.
  Rref is trimmed to 300 nA (`tools/real_bias_sweep.py`, `make_chan_opt.py
  REAL=1`).

**Noise/figure-of-merit penalty (analytic, wideband path, I_DC = 100 nA, min
I_DC for Pd 99.9 % at Pfa 1e-8, m = 2 %):**

| bias | min I_DC | σ₀ | notes |
|---|---|---|---|
| ideal sources (§17) | 22.0 nA | 8.64 µV | |
| real mirror, Rs = 300 kΩ | 24.7 nA | 9.68 µV | |
| real mirror, Rs = 1 MΩ | 23.2 nA | 9.13 µV | Rref 6.11 MΩ |
| real mirror, **Rs = 3 MΩ** | **22.5 nA** | 8.83 µV | Rref 3.63 MΩ (chosen) |

Cref (2 / 20 / 100 pF) and the mirror device size (10/4 vs 20/8 µm) change
nothing: with source degeneration the output currents are insensitive to
reference-gate noise, and the dominant added noise is the thermal noise of
Rs (about 4kT/Rs per leg). Output currents match the reference (301 / 301 nA
at 300 nA target) and `w_in` stays at 1.6505 V.

**Full Monte Carlo with the real mirror** (Rs = 3 MΩ; all five I_DC, slow path
and servo-as-fixed-bias included, 20 000 trials per point; noise-only
correlator kurtosis 3.00–3.03):

| I_DC | m = 2 % | m = 1 % | m = 0.5 % |
|---|---|---|---|
| 10 nA | 11.5 dB, Pd 0.039 | 5.5 dB | −0.6 dB |
| 30 nA | 21.1 dB, Pd 1 | 15.0 dB, Pd 0.52 | 9.0 dB |
| 100 nA | 31.1 dB | 25.1 dB | 19.1 dB, Pd 0.9975 |
| 300 nA | 39.7 dB | 33.7 dB | 27.6 dB |
| 1 µA | 47.7 dB | 41.7 dB | 35.7 dB |

vs §17 (ideal sources): 11.7 / 21.3 / 31.3 dB at (10 nA, 30 nA, 100 nA; m =
2 %), so the real bias costs **≈ 0.1–0.2 dB of SNR**. **Minimum I_DC for Pd ≥
99.9 % at Pfa = 1e-8: ≈ 24.3 nA (m = 2 %), ≈ 48.6 nA (m = 1 %), ≈ 97 nA
(m = 0.5 %)**, about 2.5 % above the ideal-source numbers.

**Caveats:** (i) tt corner, 27 °C, no mismatch/Monte Carlo: output-leg
mismatch only changes the DC current into the 314 kΩ TIA (10 % of IBX = 30 nA
→ ≈ 9 mV of output offset), which is harmless here, but this was not simulated;
(ii) Rs, Rref are ideal resistors in SPICE (their thermal noise is included,
temperature coefficient and mismatch are not); 3 MΩ + 3 MΩ + 3 MΩ + 3.6 MΩ of
poly and a 20 pF reference-gate cap were not sized for area; (iii) the Msv
servo bias is still a fixed gate voltage standing in for the digital/DAC
loop, and the wideband bandwidth shortfall (§15, §17) is unchanged.

## 19. Process corners and temperature (2026-10-17)

Tool: `simulation/spice/tools/corner_run.py`; raw output
`simulation/spice/results/corner_sweep.txt`. Optimised stage with the **real
PMOS bias mirror** (§18), I_DC = 100 nA, servo replaced by a bisected fixed
Msv gate voltage per corner (the job the digital servo would do), Rref
**not** re-trimmed (it is a fixed resistor in silicon), solver tolerances
tightened (abstol 1e-16 A) because picoamp cancel currents through multi-GΩ
feedback are otherwise below the default resolution.

| corner / temp | bias Ixc = Iw | w_in | slow-path Z @10 Hz | wide RTI @100 kHz | min I_DC (m = 2 %) |
|---|---|---|---|---|---|
| tt / 27 °C | 298 nA | 1.650 V | **1.0 GΩ** | 628 fA/√Hz | 24.3 nA |
| tt / −40 °C | 284 nA | 1.650 V | 25 GΩ † | 331 | 14.2 nA |
| tt / 125 °C | 319 nA | 1.651 V | **0.79 MΩ** | 1244 | **52.4 nA** |
| ss / 125 °C | 309 nA | 1.651 V | 7.8 MΩ | 679 | 33.8 nA |
| ff / −40 °C | 294 nA | 1.650 V | 42 GΩ † | 330 | 14.1 nA |
| sf / 27 °C | 285 nA | 1.650 V | 120 GΩ † | 405 | 17.0 nA |
| fs / 27 °C | 312 nA | 1.650 V | **14 MΩ** | 587 | 26.9 nA |

† `s_out` could not be centred (1.75–1.85 V) even with a bisected gate
voltage and tight tolerances; treat the gain as indicative only.

**Wideband path: robust enough.** The degenerated mirror holds the bias
current within 284–319 nA (≈ ±6 %) and `w_in` within 1 mV of 1.65 V at every
corner. Minimum I_DC for Pd 99.9 % at Pfa = 1e-8 (m = 2 %) stays 14–34 nA
except at 125 °C typical, where it doubles to **52 nA** (input-referred noise
2x: ≈ 1244 fA/√Hz): that is the worst case found and sets the real photocurrent
requirement if 125 °C operation is required (a wearable is not; at 85 °C it
would sit between).

**Slow path (PPG) is NOT robust: the pseudo-resistor is the problem.** The
nominal 1 GΩ transimpedance spans **0.8 MΩ to 120 GΩ** (five decades) over
PVT, because the back-to-back PMOS pseudo-resistor is a subthreshold device
(current ∝ exp(q·V/nkT·...) with Vt shifting by corner). At 125 °C or in the
fs corner the "1 GΩ" TIA is 1–14 MΩ: the PPG signal is 70–1000x smaller than
planned and the 2-3 kHz bandwidth becomes MHz-class. At cold / sf it is
25–120 GΩ and the DC window the servo must hit shrinks in proportion.
Nothing in the §9–§18 slow-path results survives off tt/27 °C. A feedback
element whose value is set by a *resistor* (poly T-network) or by a
calibrated/replica-biased gate voltage, not a bare subthreshold device, is
needed.

**Not done:** mismatch Monte Carlo (only global corners here), supply
variation, and a Monte Carlo of the coherent detector at the 125 °C and
ss/125 channels (analytic figure of merit only for the corners).

## 20. Slow-path feedback made PVT-robust: poly T-network (2026-10-17)

§19 showed the PMOS pseudo-resistor spans 0.8 MΩ – 120 GΩ over PVT. Replaced
by a **poly T-network**: R1 = R2 = 10 MΩ in series from the photodiode node `x`
to `s_out`, R3 = 102 kΩ from their junction to VCM, Cf = 50 fF across the
whole feedback. Rf_eff = R1 + R2 + R1·R2/R3 ≈ 1.0 GΩ is set by resistor
*ratios*, so it does not move with the subthreshold device physics.
(Netlist option `tnet=1 t1= t3= tcf=` in `tools/wide_noise_sweep.py`; poly
resistors are ideal in SPICE, so thermal noise is included but absolute
tolerance and tempco are not.) Raw data:
`simulation/spice/results/corner_sweep_tnet.txt`.

**PVT results, I_DC = 100 nA, real bias mirror (§18), Msv gate bisected per
corner:**

| corner / temp | slow Z @10 Hz | slow -3 dB | slow noise RMS 0.5–100 Hz | wide RTI @100 kHz | wide min I_DC (m = 2 %) |
|---|---|---|---|---|---|
| tt / 27 °C | 0.993 GΩ | 2.82 kHz | 8.4 pA | 624 fA/√Hz | 24.1 nA |
| tt / −40 °C | 0.993 GΩ | 2.82 kHz | 9.5 pA | 546 | 21.3 nA |
| tt / 125 °C | 0.992 GΩ | 2.66 kHz | 7.4 pA | 736 | 28.0 nA |
| ss / 125 °C | 0.990 GΩ | 2.52 kHz | 7.6 pA | 745 | 28.4 nA |
| ff / −40 °C | 0.995 GΩ | 2.99 kHz | 9.2 pA | 542 | 21.0 nA |
| sf / 27 °C | 0.995 GΩ | 2.82 kHz | 8.0 pA | 629 | 24.3 nA |
| fs / 27 °C | 0.986 GΩ | 2.66 kHz | 8.7 pA | 620 | 23.9 nA |

Compared with the pseudo-resistor at the same corners: transimpedance now
within 1.5 % of 1 GΩ at every corner (was 0.79 MΩ … 120 GΩ), `s_out` centres
at all of them (it did not at cold and sf), bandwidth 2.5–3.0 kHz everywhere
(was 2.5 kHz … 224 kHz), and slow-path noise does not degrade (7.4–9.5 pA vs
8.2 pA at tt27). **Side benefit:** the worst wideband case improves from
52.4 nA (tt/125 °C) to **28.4 nA (ss/125 °C)**; the 0.8 MΩ pseudo-resistor was
a thermal-noise shunt on the shared node `x` at high temperature.

**Wideband minimum I_DC across all seven corners with the T-network: 21 – 28 nA
(m = 2 %)**, i.e. ≤ 1.2x the typical value.

**Limits of this check:**
- Poly resistor absolute tolerance (typ. ±20 %) shifts Rf_eff proportionally
  (R1·R2/R3 scales with the same factor), so the *gain* is not within 1.5 % in
  silicon, only the corner-to-corner device spread is gone; ratio mismatch of R3
  vs R1/R2 (~1 %) changes Rf_eff by about 1 %. The slow gain is then a
  calibratable constant, not a drifting nonlinear element.
- Area: 20 MΩ of series poly (≈ 10 000 squares of xhigh-ρ poly, assumed ≈
  1–2 k µm²) plus R3 and a 50 fF cap; not laid out.
- Wideband numbers at each corner were taken with default solver tolerances;
  the slow-path numbers with tight tolerances (abstol 1e-16 A). Reason: same
  netlist, tight tolerances intermittently gave a wideband `.noise` result ~40 %
  too low (e.g. 391 vs 624 fA/√Hz at tt27, changing with R3 = 102 k vs 101 k),
  which was treated as an analysis artifact. This also means the earlier §19
  table's wideband entries (run with tight tolerances) should be read with that
  caveat; this section supersedes them.
- Only I_DC = 100 nA; mismatch Monte Carlo and supply variation not done.

## 21. Chip rate and code length vs. the real channel (2026-10-17)

Tool: `simulation/detect/chip_rate_sweep.py` (analytic matched-filter figure of
merit of §17 on the simulated wideband channel `results_real/chan_100n.txt`,
real bias mirror, m = 2 %). Question: the channel's −3 dB bandwidth is only
≈ 250–300 kHz, below the 480 kHz the 480 kchip/s code was sized for; does
that shortfall matter, and is 480 kchip/s the right operating point?

| chip rate | N | T_int | min I_DC (m = 2 %) |
|---|---|---|---|
| 240 kchip/s | 24 | 100 µs | 21.7 nA |
| 320 kchip/s | 32 | 100 µs | 22.6 nA |
| 400 kchip/s | 40 | 100 µs | 23.3 nA |
| **480 kchip/s** | **48** | **100 µs** | **24.3 nA** |
| 600 kchip/s | 60 | 100 µs | 26.0 nA |
| 720 kchip/s | 72 | 100 µs | 27.6 nA |
| 960 kchip/s | 96 | 100 µs | 31.0 nA |
| 320 kchip/s | 48 | 150 µs | 18.3 nA |
| 240 kchip/s | 48 | 200 µs | 15.3 nA |
| 480 kchip/s | 96 | 200 µs | 17.2 nA |
| 480 kchip/s | 144 | 300 µs | 14.0 nA |

**Findings**
1. **The bandwidth shortfall costs little.** At fixed T_int = 100 µs, going
   from 240 to 480 kchip/s costs only 12 % in required photocurrent (≈ 1 dB),
   and doubling again to 960 kchip/s costs a further 28 %. The channel is
   not the bottleneck for detection; its noise is (§17).
2. **Latency, not chip rate, is the real lever.** Holding N = 48 (the §1a
   security target) and allowing T_int = 200 µs (a decision every other
   100 µs sample, or a 200 µs window) cuts the required I_DC by 37 %
   (24.3 → 15.3 nA at 240 kchip/s). Staying at 480 kchip/s and doubling N to 96
   gives 17.2 nA but also doubles T_int.
3. **Lowering the rate at fixed 100 µs shortens the code**, so N falls below
   the §1a minimum (≥ 40–48 bits for 1e-6 break probability over a session):
   240 kchip/s would be N = 24. The recommended point stays **480 kchip/s,
   N = 48, 100 µs** unless the latency requirement relaxes, in which case
   **240–320 kchip/s with N = 48 and T_int = 150–200 µs** gives the best SNR
   per chip, and also loosens the wideband TIA bandwidth requirement
   (≈ 160 kHz) and power.

**Caveats:** one channel (I_DC = 100 nA, tt, 27 °C); no ISI penalty beyond what
the 5-symbol Monte Carlo of §16 shows; the analytic figure of merit assumes
Gaussian noise and the rectangular-chip correlator with a fixed receiver
delay; security margin (§1a) is unchanged by the chip rate as long as N does not
drop.

## 22. Supply voltage sensitivity, and the fix: VCM 1.65 → 1.4 V (2026-10-17)

Tool: `corner_run.py ... vdd=<V> vcm=<V>`; raw data
`simulation/spice/results/supply_sweep.txt`. T-network slow path, real PMOS
bias mirror, I_DC = 100 nA, Msv gate bisected per run.

**Problem found.** With both TIAs centred at VCM = 1.65 V (VDD/2 at 3.3 V),
**VDD = 2.97 V (−10 %) breaks the design**:

| run (VCM = 1.65 V) | slow Z @10 Hz | slow -3 dB | wide \|H\|@100 kHz | wide min I_DC (m = 2 %) |
|---|---|---|---|---|
| tt/27 °C, 3.63 V | 0.996 GΩ | 3.0 kHz | 2.1e5 V/A | 23.7 nA |
| tt/27 °C, **2.97 V** | **0.42 GΩ** | **447 Hz** | **3.0e4** | **81.6 nA** |
| ff/−40 °C, **2.97 V** | 0.33 GΩ | 399 Hz | 1.3e4 | **135 nA** |
| ss/125 °C, 2.97 V | 0.56 GΩ | 563 Hz | 1.8e5 | 29.0 nA |

Cause: both op-amps end in an NMOS source follower (`M9`) whose output tops out
near VDD − Vgs ≈ 1.6 V at typical device speed, so the output cannot sit at
1.65 V when the rail drops (the slow Z falls because its output also clips,
w_in/x lock at 1.64 V instead of 1.65). It is a headroom bug in the
amplifier output stage, not noise.

**Fix.** Move the common-mode level down to **VCM = 1.4 V** (a parameter,
`vcm=1.4`; the servo target, node sets and cancel-current set point follow).
With it (VDD = 2.97 V, tt/27 °C): slow Z 0.993 GΩ, 2.7 kHz, wide min I_DC
24.6 nA; ff/−40 °C: 21.4 nA. VCM = 1.3 V works equally; VCM = 1.5 V is
marginal (slow bandwidth 2.4 kHz).

**PVT × supply matrix, VCM = 1.4 V, I_DC = 100 nA, m = 2 %:**

| corner / temp / VDD | slow Z | slow -3 dB | slow noise (0.5–100 Hz) | wide min I_DC | IBX |
|---|---|---|---|---|---|
| tt / 27 / 3.3 | 0.996 GΩ | 2.8 kHz | 8.4 pA | 24.1 nA | 298 nA |
| tt / 27 / 2.97 | 0.993 GΩ | 2.7 kHz | 8.4 pA | 24.6 nA | 255 nA |
| tt / 27 / 3.63 | 0.997 GΩ | 3.0 kHz | 8.4 pA | 23.7 nA | 342 nA |
| tt / −40 / 2.97 | 0.992 GΩ | 2.7 kHz | 9.5 pA | 21.7 nA | 241 nA |
| tt / −40 / 3.63 | 0.997 GΩ | 3.2 kHz | 9.5 pA | 21.0 nA | 328 nA |
| tt / 125 / 2.97 | 0.992 GΩ | 2.5 kHz | 7.4 pA | 28.8 nA | 276 nA |
| tt / 125 / 3.63 | 0.996 GΩ | 2.8 kHz | 7.4 pA | 27.5 nA | 363 nA |
| ss / 125 / 2.97 | 0.990 GΩ | 2.4 kHz | 7.6 pA | **29.2 nA** | 266 nA |
| ss / 125 / 3.63 | 0.996 GΩ | 2.7 kHz | 7.6 pA | 27.8 nA | 352 nA |
| ff / −40 / 2.97 | 0.995 GΩ | 2.8 kHz | 9.2 pA | 21.4 nA | 250 nA |
| ff / −40 / 3.63 | 0.997 GΩ | 3.2 kHz | 9.2 pA | **20.8 nA** | 338 nA |
| sf / 27 / 2.97 | 0.995 GΩ | 2.7 kHz | 8.0 pA | 24.9 nA | 242 nA |
| fs / 27 / 2.97 | 0.986 GΩ | 2.5 kHz | 8.7 pA | 24.4 nA | 268 nA |

Across all of these, **slow Z stays within 1.5 % of 1 GΩ, wide min I_DC is
20.8 – 29.2 nA (≤ 1.21x the tt/27/3.3 V value), and IBX moves 241 – 363 nA
(roughly ∝ supply, since the resistor-programmed reference is not
supply-independent)**. IBX at 255 nA (low supply) costs nothing measurable.

**Caveats.** Earlier sections (§13–§21) used VCM = 1.65 V at VDD = 3.3 V, where
the numbers are unchanged to within 1 % by moving VCM to 1.4 V (24.1 vs 24.3 nA
at tt/27/3.3 V). Supply noise/PSRR was not simulated (DC supply levels only).
The photodiode reverse bias is set by `x`, so lowering VCM reduces it by 0.25 V
(the PPG/photodiode model here has no bias dependence; real junction
capacitance rises as reverse bias falls, which was not modelled).

## 23. Digital DC-cancellation servo: sizing and closed-loop simulation (2026-10-17)

Code: `simulation/servo/servo_loop.py` (loop + plant), `study.py` (studies),
`spice_check.py` (transistor-level cross-check), plant/noise data from ngspice in
`simulation/servo/data/`, summarised results in `simulation/servo/results.txt`.
Replaces the behavioral integrator of §13.

**Architecture simulated.** Slow TIA output `s_out` → **10-bit ADC**
(±0.5 V around VCM, LSB 0.98 mV ≈ 1 pA at 1 GΩ, 0.5 LSB rms noise, 2 kS/s) →
digital controller → **12-bit coarse current DAC** (LSB 0.5 nA, range 2.05 µA)
**plus a first-order sigma-delta fine path** clocked at 100 kHz from a
24-bit-equivalent accumulator (so the effective resolution is ~pA, avoiding a
0.5 nA = 500 mV output step per LSB at 1 GΩ). Controller: **(1) SAR
acquisition** (12 bits, 3 ADC samples wait per decision, ≈ 24 ms) at power-up
and whenever |error| > 0.3 V for 5 ms; **(2) integrator** tracking with a
0.05 Hz high-pass corner (gain 2π·fc/Fs per sample); **(3) boost ×20** when
the 2 s signed mean of the error exceeds 30 mV (a PPG waveform averages out, a
DC step does not). The plant is a 2nd-order fit (Z0 = 1.02 GΩ, f0 = 2.3 kHz,
Q = 0.84) to the transistor-level slow TIA; analog noise is the simulated
slow-path input-referred PSD at the same I_DC (it already includes the real
NMOS cancel device). Both PPG tests below use a 1.2 Hz sine.

**Power-up acquisition.** Locks (DAC mean within ±50 pA of final for 50 ms) in
**≈ 88 ms for every I_DC from 10 nA to 1 µA (101 ms at 2 µA)**; the noiseless
run locks in 25 ms to 100.00 nA, so most of the 88 ms is the 50 ms hold
criterion plus a few noise-induced SAR corrections.

**Steady state (I_DC = 100 nA, 150 pA PPG):**

| fc | PPG gain | phase | added noise 0.5–100 Hz |
|---|---|---|---|
| 0.02 Hz | 0.995 | +0.6° | 8.6 pA |
| 0.05 Hz | 0.994 | +2.1° | 8.5 pA |
| 0.10 Hz | 0.991 | +4.5° | 8.5 pA |

At I_DC = 10 nA: gain 0.998, 1.6 pA; at 300 nA: 0.983, 24.9 pA. These noise
values equal the analog SPICE results (8.4 / 1.6 / 24.4 pA), i.e. **the ADC,
the DAC quantisation and the sigma-delta loop add no measurable noise**.
Chosen: **fc = 0.05 Hz** (≤ 0.7 % gain loss and ≤ 2.5° at the PPG fundamental).

**Ambient-light steps (I_DC = 100 nA):** +100 pA settles in **0.95 s** (4.5 s
without the boost); ≥ +1 nA steps clip the output (±0.45 V) and are re-acquired
in **53–113 ms**, each costing one SAR pass of PPG data.

**Failures found by the simulation (not fixable by the loop):**
1. **PPG amplitude ceiling at 1 GΩ: ≈ ±150–250 pA.** A 1 nA PPG (1 % of
   100 nA) is 1 V at the output and clips; with a 300 pA amplitude the output
   peaks reach the 0.3 V re-acquire threshold and the loop collapses (gain
   0.57, 53 re-acquisitions). The slow path therefore needs a **switchable
   transimpedance** (e.g. 1 GΩ / 100 MΩ / 10 MΩ via R3 or the T-network) and a
   range-select policy; the 1 GΩ setting is only usable for I_DC ≲ 15–25 nA at
   1 % modulation.
2. **I_DC ≳ 1 µA at 1 GΩ is unusable:** the cancel device's 1/f noise grows
   ∝ I_DC (1.6 pA at 10 nA → 78 pA at 1 µA → 150 pA at 2 µA, 0.5–100 Hz); at 1 µA
   with 150 pA PPG the loop reports gain 0.81, 115 pA of noise and a spurious
   re-acquisition. Again solved by a lower transimpedance range.
3. An early version with a fast gain-schedule threshold (20 mV) erased the
   PPG (gain 0.23): the threshold must sit above the PPG amplitude; the error
   is now handled by the 2 s mean detector and the re-acquire threshold instead.

**Transistor-level check.** The Python DAC current waveform (sigma-delta
toggling included) was fed into the actual SPICE slow TIA (afe_direct.spice,
tt/27 °C, VCM 1.4 V) with the same 150 pA photocurrent: SPICE s_out is 269 mV
p-p versus 272 mV from the Python plant, rms difference 3.6 mV (≈ 3 % of the
PPG rms), DC offset difference ≈ 40 mV (≈ 40 pA, inside what the integrator
would remove). The behavioral plant is adequate for this sizing.

**Not done / assumed:** the DAC is behavioral (ideal steps, no INL, glitch,
output impedance or mismatch); its noise is taken equal to the single NMOS
sink used in §14–§20, which a segmented DAC of many unit cells may beat or
miss (unverified); the sigma-delta ripple at the TIA output (0.5 nA toggling
at up to 100 kHz) was only checked inside the SPICE comparison, not
spectrally; the digital block's power, ADC/DAC circuit design, the range
switch and its glitch, temperature/corner variation of the loop, and
reset/start-up sequencing are not designed.
