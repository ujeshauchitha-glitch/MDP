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

> **Corrected in §25.** The claim below that a blind attacker succeeds with probability 2^-N "even with
> unlimited SNR" is false for a correlation-threshold detector (blind injection at the legitimate
> amplitude is accepted ≈ 16 % of the time); it holds only with an added residual/energy test, and
> not against a real-time relay or an attacker who has observed the chips.

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
  which was treated as an analysis artifact (its cause could not be reproduced in the §33
  audit; see there). This also means the earlier §19
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

## 24. Switchable slow-path transimpedance (3 ranges) and auto-ranging (2026-10-17)

§23 showed a fixed 1 GΩ clips PPG amplitudes above ≈ ±150–250 pA and is unusable
above ≈ 1 µA of I_DC. Fix: three transimpedance ranges.

**Implementation (SPICE, `rpar=` / `tcf=` options of `wide_noise_sweep.py`,
`corner_run.py`).** The T-network of §20 (R1 = R2 = 10 MΩ, R3 = 102 kΩ) stays as
the 1 GΩ range. Lower-gain ranges add a switched resistor **across the whole
network** (switch Ron neglected; leaks negligible against the MΩ values) and a
range-matched feedback capacitor:

| range | extra resistor | Cf | Z @10 Hz (tt/27) | −3 dB | noise 0.5–100 Hz (input-referred) | PPG headroom (±0.3 V) |
|---|---|---|---|---|---|---|
| 1 GΩ | none | 50 fF | 0.996 GΩ | 2.8 kHz | 1.6 pA @ 10 nA | ±0.3 nA |
| 100 MΩ | 111 MΩ | 100 fF | 99.9 MΩ | 9.5 kHz | 8.4 pA @ 100 nA | ±3 nA |
| 10 MΩ | 10.1 MΩ | 500 fF | 10.0 MΩ | 25 kHz | 78 pA @ 1 µA | ±30 nA |

Over PVT (raw data `simulation/spice/results/range_sweep.txt`): 100 MΩ range
at 100 nA, ss/125 °C and ff/−40 °C: Z = 99.9 MΩ, BW 8.9 / 10 kHz, noise 7.6 / 9.2 pA;
10 MΩ range at 1 µA: Z = 10.0 MΩ, BW 24 / 27 kHz, noise 70 / 86 pA; 1 GΩ range at
10 nA, tt/125 °C, ss/125 °C, tt/−40 °C: Z = 0.995 – 0.997 GΩ, 2.7 – 3.0 kHz, 1.6 pA.
Input-referred noise is range-independent (set by the cancel device, ∝ I_DC), so
SNR is unchanged by ranging; only the output swing changes. Lock windows exist
everywhere (the earlier "no lock" at 10 nA, ss/125 °C was my scan starting at
Vgs = 0.2 V; the window there is 0.1–0.2 V Vgs, and the cancel device's off
leakage at 125 °C is below 10 nA).

**Auto-range policy (digital, `servo_loop.py`).** Power up in the safest range
(10 MΩ). After the 12-bit SAR acquisition (≈ 24 ms) the DAC code *is* an
I_DC measurement. After a 100 ms hold choose the highest-gain range whose
headroom still fits a 2 % modulation with ~0.25 V swing:
I_DC ≤ 12.5 nA → 1 GΩ; ≤ 125 nA → 100 MΩ; otherwise 10 MΩ (good to
≈ 1.25 µA; a 1 MΩ range would be needed above that). Switching re-centres the
output and keeps the DAC code, so no new SAR pass is needed.

**Closed-loop results (fc = 0.05 Hz, 1.2 Hz PPG, `simulation/servo/results.txt`).**
Fixed-range: every (range, I_DC, modulation) inside its headroom gives PPG
gain 0.998–1.000, phase +2.3° and noise equal to the analog value (1G @ 10 nA
1.6 pA; 100M @ 100 nA 8.6 pA; 10M @ 300 nA 25.5 pA; 10M @ 1 µA 80 pA); the
10 MΩ range now handles 1 µA with a 20 nA (2 %) PPG at 204 mV swing and no
re-acquisition, where 1 GΩ failed (§23). From power-up with auto-ranging:

| I_DC | range chosen | PPG gain (last 3 s, 2 % mod.) | added noise | re-acq. |
|---|---|---|---|---|
| 5 nA | 1 GΩ | 0.9986 | 0.8 pA | 0 |
| 30 nA | 100 MΩ | 0.9988 | 2.9 pA | 0 |
| 100 nA | 100 MΩ | 0.9989 | 8.5 pA | 0 |
| 300 nA | 10 MΩ | 0.9987 | 24.5 pA | 0 |
| 1 µA | 10 MΩ | 0.9986 | 78.7 pA | 0 |

(Switch at 0.125 s from power-up, SAR lock at 24 ms in all cases.)

**Effect on the wideband path.** The extra range resistors and capacitors load
the shared photodiode node slightly: wide min I_DC (m = 2 %) at tt/27 °C is
24.1 nA (1 GΩ), 25.3 nA (100 MΩ range, I_DC = 100 nA) and 35.9–45 nA (10 MΩ
range, I_DC = 1 µA, where the cancel device's noise at `x` also grows ∝ I_DC).
These are *noise-limited minimum photocurrents at that I_DC*; at 1 µA the
actual photocurrent is 20–40x above the minimum, so detection is unaffected.

**Caveats.** Switches are ideal (Ron, charge injection, leakage, and the
transient when a range changes are not simulated); the 1 MΩ range for
> 1.25 µA is not built; Cf sizing is by peaking only (no loop-gain check
per range); policy thresholds assume ≤ 2 % PPG modulation; the DAC full scale
(2.05 µA) limits I_DC to ~2 µA.

## 25. Spoofing resistance: detector hardening, relay attacks, code generator (2026-10-17)

Tools: `simulation/detect/spoof_mc.py` (output `spoof_results.txt`),
`simulation/detect/codegen_security.py` (output `codegen_results.txt`). Setup: the
simulated I_DC = 100 nA channel (real bias mirror), legitimate m = 2 % (the
detector sees d ≈ 35σ), 48 chips at 480 kchip/s, 6000 trials per point. The
attacker injects light into the photodiode (same channel and noise as the
legitimate signal, the LED path absent) and knows the chip clock. An
acceptance count of 0 means < 1/6000, not zero probability.

**This section corrects §1a.** There I wrote that a blind attacker succeeds with
probability 2^-N "even with unlimited SNR". That holds only if the detector
bounds the received energy. For the correlation-threshold detector (D0) used
everywhere above, it is false.

**Detectors.** D0: correlation z > 5.61σ (Pfa 1e-8 for noise alone). D1: D0
**and** a residual (goodness-of-fit) test: subtract the least-squares fit of the
known template (the front end's response to the true code, including
neighbouring-symbol ISI) and require the leftover energy to be consistent with
noise (threshold = 99.9 % quantile of the legitimate distribution). D1 costs
0.10 percentage points of legitimate Pd (1.0000 → 0.9990 at I_DC = 100 nA).

| attacker (same amplitude as legit unless noted) | D0 accepts | D1 accepts |
|---|---|---|
| blind random chips, 1x | **16.2 %** | 0 |
| blind, 3x / 10x / 100x / 300x | 37 % / 47 % / 50 % / 51 % | 0 |
| knows 50 % of the chips | **99.1 %** | 0 |
| knows 75 % | 100 % | 0.08 % |
| knows 90 % | 100 % | **8.4 %** |
| knows 95 % | 100 % | **28.6 %** |
| knows 90 % / 95 %, amplitude 10x | 100 % | 1.2 % / 7.9 % |

So with D0 a blind attacker already wins 1 in 6 at the legitimate amplitude, and
half the time when loud, because the AWGN-derived threshold is far below the
attacker-correlation spread when the legitimate signal sits at 35σ. **D1
removes the blind case entirely** but not an attacker who has most of the chips.

**Real-time relay attacker** (observes every chip perfectly, re-emits it τ late,
same amplitude): D1 accepts **99.9 % at τ = 20 ns, 99.6 % at 50 ns, 97.0 % at
130 ns**, 33.5 % at 260 ns, 0 % at 520 ns and above (1 chip = 2083 ns). The
front end's ~300 kHz bandwidth smooths the chip edges more than a 50–130 ns
delay moves them, so the receiver cannot see the delay. A relay built from a
fast photodiode, comparator and LED driver can have tens of nanoseconds of
latency. **The chip code does not defend against a real-time optical relay at
this bandwidth and SNR**, however random it is; D1 only forces the relay under
~200 ns. Possible but unevaluated mitigations: more per-sample SNR (makes
smaller delays visible), a second unobservable dimension per chip (e.g.
per-chip wavelength or intensity ratios that the relay cannot sense), or limiting
the claim to replay and blind injection.

**Code generator.** Berlekamp–Massey on a 32-bit maximal LFSR: after 40 chips
51.6 % prediction (no better than guessing), after **64 chips (133 µs, less than
two symbols) it predicts the next 5000 chips with 100.00 % accuracy** and keeps
doing so (linear complexity 32). A keyed hash-counter stream (ideal-CSPRNG
stand-in, not a hardware proposal) stays at 50 % with linear complexity
growing as n/2 (500 at 1000 chips). So a plain LFSR (or any linear-feedback or
Gold-code generator) is **unacceptable** whenever an attacker can see even 64
consecutive chips, which the relay scenario above gives them. A nonlinear
keyed stream cipher with a per-session/per-frame reseed from a hardware TRNG
is required; the choice (Trivium/Grain/ASCON-class vs AES-CTR), key
storage (the repository's PUF/DICE paper is relevant) and area/power need a
cryptographer and are **not** evaluated here.

**Recommended detector rule (simulated here only as D1):** accept a decision
only if (a) correlation exceeds the AWGN threshold, (b) the fitted amplitude is
within a window around the *known* expected amplitude (the device knows
m·I_DC), and (c) the residual energy fits noise. (b) was not simulated
separately; (a)+(c) already reject all blind injection.

**Caveats.** One operating point (I_DC = 100 nA, m = 2 %); the residual
threshold was set from 6000 legitimate trials (99.9 % quantile), so the
legitimate false-reject rate (1e-3) is empirical and the corresponding
attacker acceptance at the 1e-6…1e-8 level is not measurable by Monte Carlo
(Gaussian-tail extrapolation would be needed); attackers were given perfect
timing and, for the relay, perfect chip observation; no analog attacker
bandwidth limits.

## 26. Mismatch: worst-case sensitivity of the wideband stage (2026-10-17)

Tool: `simulation/spice/tools/mismatch_sens.py`; data
`simulation/spice/results/mismatch_sens.txt`.

**Why not a Monte Carlo.** The sky130 5 V device models used here have no
usable random-mismatch parameters (`vth0_slope = 0.000` for the thick-oxide
NMOS/PMOS), so a model-driven Monte Carlo would silently show no mismatch. Instead
gate-referred threshold offsets are injected by hand, one block at a time, at about
±3σ for these areas (Pelgrom with an *assumed* A_VT of 5–10 mV·µm: σ ≈ 0.8 mV for
the 160 µm² mirror devices, ≈ 1.1 mV for the bias mirror, ≈ 3 mV for the wideband
op-amp input pair plus load): ±5 mV on the mirror and bias legs, ±10 mV on the op-amp.

| injected offset | Ixc / Iw | w_in | w_out − VCM | \|H\|@100 kHz | min I_DC (m = 2 %) |
|---|---|---|---|---|---|
| none (reference) | 298 / 298 nA | 1.4005 V | +1.0 mV | 2.14e5 | 22.5 nA |
| mirror Mo1 vs Mm, +5 / −5 mV | 298 / 298 | 1.4005 | +4.3 / −2.3 mV | 2.17e5 / 2.11e5 | 22.4 / 22.7 |
| bias leg Mpw vs ref, +5 / −5 mV | 298 / 297, 300 | 1.4005 | +1.4 / +0.8 mV | 2.14e5 | 22.5 |
| bias leg Mpx vs ref, +5 / −5 mV | 297, 300 / 298 | 1.4005 | +0.6 / +1.4 mV | 2.14e5 / 2.15e5 | 22.5 |
| wide TIA op-amp Vos, +10 / −10 mV | 298 / 298 | 1.3906 / 1.4107 | −8.9 / +11.2 mV | 2.14e5 | 22.5 |
| combined worst case | 300 / 297 | 1.3905 | −4.9 mV | 2.18e5 | 22.4 |

**Result: benign.** Bias currents move ≤ 1 % (the 3 MΩ / 200 kΩ source
degeneration turns a 5 mV offset into only 1.7 nA / 0.6 %), the wideband output
DC shifts ≤ ±11 mV, gain ≤ ±1.5 % and the detection reach ≤ ±1 %. The cancel-current
mismatch only changes the DC current into the 314 kΩ TIA (3 nA → 1 mV). The slow
path is not injected: its offsets only move the bisected Msv gate voltage,
which the digital servo removes.

**Caveats.** Only systematic offsets of assumed magnitude; no random
Monte Carlo, no resistor mismatch (poly R1/R2/R3 ratio errors move the slow
gain ≈ 1 % per 1 % R3 mismatch, §20), no capacitor mismatch, no W/L (geometry)
mismatch, and the A_VT values are assumptions not taken from the PDK.

## 27. Supply rejection (PSRR): poor, and it sets a supply-noise budget (2026-10-17)

> **Superseded by §28.** The diagnosis below ("inside the op-amps") was wrong: the coupling came
> from Mc's body effect, now fixed; the supply-noise budget below is the *pre-fix* one.

Tool: `simulation/spice/tools/psrr.py`; raw data `simulation/spice/results/psrr.txt`.
Full chain (T-network, real bias mirror, VCM 1.4 V, tt/27 °C, VDD 3.3 V,
I_DC = 100 nA): AC on VDD → each output, divided by the measured signal gain, gives
the input current that would produce the same output (i_eq, per 1 V/√Hz of supply noise).

| slow path, 1 GΩ range | PSRR | i_eq per V/√Hz |
|---|---|---|
| 0.5 Hz | 30.5 dB | 30 pA |
| 1 Hz | 24.8 dB | 58 pA |
| 10 Hz | 4.8 dB | 575 pA |
| 100 Hz | **−15.2 dB** | 5.75 nA |
| 1 kHz | **−36.4 dB** | 57 nA |

| wideband path | PSRR | i_eq per V/√Hz |
|---|---|---|
| 10 kHz | 29.5 dB | 131 nA |
| 100 kHz | 13.2 dB | 1.06 µA |
| 300 kHz | 11.3 dB | 3.3 µA |
| 1 MHz | 22.8 dB | 8.0 µA |

i_eq is the same for all three slow ranges (PSRR in V/V improves by 20 dB per
decade of lower gain, the signal gain falls by the same amount). It does not change
with the bias network (ideal sources instead of the real mirror, Cref 20 → 200 pF,
wideband-TIA bias resistor 0.6 → 2 MΩ all give the same numbers), so the coupling is
inside the op-amps.

**Likely mechanism (inferred, not confirmed at node level).** The slow-path
response rises ∝ f and matches ε·|1 + jωRf·Cj| (the TIA noise gain acting on a
supply-induced input-referred voltage), with ε ≈ 0.5 at 10 Hz and ≈ 1 at 1 kHz
(measured out/VDD = 66 vs 62.8 V/V predicted at 1 kHz). A two-stage op-amp with a PMOS
current-source load (M7 ro against M6 ro) passes a large fraction of VDD to its
output, and Miller coupling returns it to the input.

**Supply-noise budget this implies** (noise from the supply must stay ≲ 20 % of the
analog floor in each band):

| band | analog floor (input-referred) | max supply noise density |
|---|---|---|
| slow, 10 Hz | 1.1 pA/√Hz | ≈ 0.4 µV/√Hz |
| slow, 100 Hz | 0.44 pA/√Hz | **≈ 15 nV/√Hz** |
| wide, 100 kHz | 0.6 pA/√Hz | ≈ 110 nV/√Hz |
| wide, 300 kHz | 0.6 pA/√Hz | ≈ 36 nV/√Hz |

Tones: a 1 mV supply ripple near 300 kHz looks like a 3.3 nA input signal (larger
than the 2 nA legitimate perturbation at I_DC = 100 nA, m = 2 %), and tones matter
as interference even though they are not correlated with the code. To stay below
10 % of I_pert the ripple at ≈ 300 kHz must be < ≈ 60 µV. Typical LDO output noise
(tens to hundreds of nV/√Hz) and any switching regulator ripple would therefore
degrade both paths; a quiet LDO with heavy off-chip decoupling is a requirement
unless the op-amp PSRR is improved (cascode or replica-biased second stage,
isolated analog supply, which was not designed here).

**Caveats.** PSRR measured only at tt/27 °C and I_DC = 100 nA; the effect on the
Monte Carlo detection numbers of §16–§21 (which assume a noiseless supply) is not
quantified beyond the budget above; the mechanism is not confirmed; supply-to-PPG
cross-talk through the digital servo (ADC/DAC reference) is not included.

**§27 addendum: why the obvious op-amp fix does not fit (headroom check, 2026-10-17).**
The natural fix for a PMOS-load second stage that passes VDD ripple to its output
is to cascode the load. In the simulated op-amps `amp_out` sits at **2.67 V (slow) and
2.68 V (wide) with VDD = 3.3 V, VCM = 1.4 V** (the output NMOS source follower
needs Vgs ≈ 1.3 V above its 1.4 V output), so only ≈ 0.62 V is left across the
PMOS load. A cascoded load needs about 2 × Vdsat ≈ 0.7 V or more, so it does not fit.
Realistic routes, none simulated: (a) lower VCM to ≈ 1.2 V (frees ≈ 0.2 V but moves the
input pair, Mc and mirror headroom), (b) replace the NMOS source-follower output
by a lower-Vgs buffer, or (c) take the supply requirement to the board: an
ultra-low-noise LDO (single-digit nV/√Hz class, > 80 dB PSRR) with heavy
decoupling meets the budget above without touching the op-amp.

## 28. Supply-rejection fix: the cause was Mc's body, not the op-amps (2026-10-17)

**This corrects §27's "inside the op-amps" diagnosis.** Tracing the VDD → node
transfer at 100 Hz (tool: node-by-node AC dump in `simulation/spice/build`, summarised
here; code: `tools/psrr.py`, `wide_noise_sweep.py` options `mcbulk`, `iref`):

* the slow output current was `5.7 nA per V` of ripple through the T-network
  midpoint `tn`, but the real source is **node `xc` (Mc's source) moving 0.18 V per
  V of VDD ripple**; the 50 pF coupling capacitor Cc converts that to a current
  `ω·Cc·0.18 ≈ ω·9.1 pF` into node `x` (matching the measured i_eq ∝ f at an
  equivalent 9.15 pF);
* the cause is the **body effect**: Mc is a PMOS in an n-well tied to VDD, so VDD
  ripple modulates its threshold and therefore `xc`.

Replacing the op-amp output stage with a follower-free stage and a cascoded PMOS
load (`opamp2=1`, 0.62 V → ~1.9 V headroom) changed nothing at all
(bit-identical to 3 digits for any cascode bias), confirming the op-amps were not
the path; it improved the slow path only ≈ 1.5x at low frequency once the real
cause was fixed and is **not adopted**.

**Fix (two parts):**
1. **Mc's n-well on the quiet VCM node** (`mcbulk=vcm`) instead of VDD. Tying it to
   its own source also removes the VDD path but costs 13 % of wideband reach (the
   isolated well's capacitance sits on the signal node): min I_DC 27.1 nA versus
   24.2 nA with the bulk on VCM. Needs a separate n-well for Mc and a low-impedance
   1.4 V node (already present as the TIA common-mode reference).
2. **Supply-independent bias reference** (`iref=300n`): the mirror reference was a
   resistor to ground (reference current ∝ VDD, gate ripple 0.48 V/V). It is now a
   constant current to ground (ideal here; bandgap-derived in silicon), so the
   mirror gate tracks VDD and the bias legs stay at 300 nA at every corner and supply.

**Supply-induced input-equivalent current (per 1 V/√Hz of supply noise), 1 GΩ range,
I_DC = 100 nA, tt/27 °C** (raw `results/psrr_fix.txt`):

| frequency | before (§27) | after (bulk = VCM + Iref) | gain |
|---|---|---|---|
| slow 0.5 Hz | 30 pA | 8.0 pA | 3.7x |
| slow 10 Hz | 575 pA | 8.4 pA | 68x |
| slow 100 Hz | 5.75 nA | 26.9 pA | 214x |
| slow 1 kHz | 57 nA | 257 pA | 223x |
| wide 10 kHz | 131 nA | 0.63 nA | 210x |
| wide 100 kHz | 1.06 µA | 27 nA | 39x |
| wide 300 kHz | 3.3 µA | 275 nA | 12x |
| wide 1 MHz | 8.0 µA | 3.7 µA | 2.2x |

**New supply-noise budget** (≤ 20 % of the analog floor; **corrected in the §33 audit**: the
first version used a 0.5 pA floor at 1 MHz where the input-referred floor is ≈ 5.5 pA):
slow 10 Hz ≲ 26 mV/√Hz, 100 Hz ≲ 3 mV/√Hz; wide 100 kHz ≲ 4.7 µV/√Hz, 300 kHz ≲ 0.9 µV/√Hz,
1 MHz ≲ 0.3 µV/√Hz. Tolerable tone amplitude for ≤ 10 % of I_pert (200 pA at I_DC = 100 nA,
m = 2 %): ≈ 7 mV at 100 kHz, ≈ 0.7 mV at 300 kHz, ≈ 54 µV at 1 MHz. §29 improves all of this
by a further 7–700x. The residual coupling at 300 kHz – 1 MHz was not traced.

**PVT × supply with the fix** (corner_run, I_DC = 100 nA, VCM 1.4 V, T-network,
Mc bulk = VCM, Iref; `psrr_fix.txt`): slow Z 0.990 – 0.997 GΩ, −3 dB 2.4 – 3.2 kHz,
slow noise 7.4 – 9.5 pA, **bias current exactly 300 / 300 nA at all 11 points**
(it varied 241 – 363 nA with a resistor reference), wideband min I_DC
**21.0 – 29.0 nA** (m = 2 %; ss/125 °C 28.7 – 29.0 nA, ff/−40 °C 21.0 – 21.2 nA),
i.e. unchanged from §22.

**Caveats.** PSRR measured only at tt/27 °C, I_DC = 100 nA, 1 GΩ range (§27 showed
the equivalent input current is range-independent); the adopted Mc well must be
isolated in layout and its bulk node must be quiet over the whole band; the
reference current is an ideal source (its noise, supply rejection and
temperature behaviour in silicon are not modelled); the remaining
300 kHz – 1 MHz coupling is untraced; the correlator Monte Carlo (§16–§21) was
not re-run (it assumes a noiseless supply and the min-I_DC figure is unchanged).

## 29. Supply rejection, second round: op-amp input-pair body effect (2026-10-17)

After §28 the residual supply coupling at 100 Hz – 1 MHz was traced by **bisecting
the circuit**: giving each block its own DC-only copy of VDD so the AC ripple
reaches only the rest. Isolating the slow TIA's supply cut the slow-path ripple
14–15x; isolating the wideband TIA's supply cut the 1 MHz wideband ripple 7x.
(Three earlier guesses were falsified first: a cascode on the PMOS cancel leg, an
AC capacitor on the op-amp's PMOS bias node, and the cascoded op-amp load of §28:
none changed the numbers.)

**Mechanism.** The slow-path coupling is `ω·C_eff` with C_eff ≈ 41 fF at 1 kHz,
the gate-source capacitance of the op-amp's input PMOS times the **tail-node
ripple of 0.23 V/V**, and the tail ripple is constant from 100 Hz to 1 MHz,
i.e. resistive: both input devices sit in n-wells tied to VDD, so VDD ripple shifts
their thresholds (body effect, the same mechanism as §28's Mc) and the
common source node follows. The ripple on that node then couples through the input
device's Cgs into the virtual-ground node `x`/`w_in` (asymmetrically, because the
other input is the ideal VCM reference).

**Fixes (all in the netlist builder, `inbulk=src`, `ibias=2u,4u`, plus §28's
`mcbulk=vcm iref=300n`):**
1. **Op-amp input pairs in their own n-wells tied to the tail node** (both TIAs).
   By itself: slow 100 Hz 26.9 → 5.5 pA per V/√Hz, 1 kHz 257 → 26 pA; wide
   100 kHz 27 → 3.7 nA, 1 MHz 3.7 µA → 0.68 µA, with **no** change in gain,
   bandwidth or detection reach (min I_DC 24.2 nA).
2. **Supply-independent op-amp bias currents** (ideal 2 µA / 4 µA sources into
   the reference diodes instead of resistors from VDD, whose current is ∝ VDD).

**Supply-induced input-equivalent current, per 1 V/√Hz** (1 GΩ range, I_DC =
100 nA, tt/27 °C; raw data `results/psrr_final.txt`):

| frequency | original (§27) | §28 fix | all four fixes (§29) | total gain |
|---|---|---|---|---|
| slow 10 Hz | 575 pA | 8.4 pA | **1.09 pA** | 527x |
| slow 100 Hz | 5.75 nA | 26.9 pA | **2.06 pA** | 2800x |
| slow 1 kHz | 57 nA | 257 pA | **17.9 pA** | 3200x |
| wide 10 kHz | 131 nA | 0.63 nA | **10 pA** | 13000x |
| wide 100 kHz | 1.06 µA | 27 nA | **1.8 nA** | 580x |
| wide 300 kHz | 3.3 µA | 275 nA | **19.7 nA** | 167x |
| wide 1 MHz | 8.0 µA | 3.7 µA | **330 nA** | 24x |

Supply-noise limits for ≤ 20 % of the analog floor (**recomputed in the §33 audit** from the
table above and the measured input-referred floors; the first version of this paragraph had
arithmetic errors): slow 10 Hz ≲ 210 mV/√Hz, 100 Hz ≲ 42 mV/√Hz, 1 kHz ≲ 2.5 mV/√Hz; wide
10 kHz ≲ 11 mV/√Hz, 100 kHz ≲ 69 µV/√Hz, 300 kHz ≲ 12 µV/√Hz, **1 MHz ≲ 3.3 µV/√Hz**.
A tone ≤ 10 % of I_pert (200 pA at I_DC = 100 nA, m = 2 %) is tolerated up to ≈ 110 mV at
100 kHz, ≈ 10 mV at 300 kHz and **≈ 0.6 mV at 1 MHz**. In practice any normal low-noise
supply now meets the budget; a switching regulator with more than a few hundred µV of ripple
at ≥ 1 MHz would still need a filter.

**PVT × supply with all four fixes** (11 points: tt 2.97/3.3/3.63 V, ss/125 °C and
ff/−40 °C at ±10 % supply, sf and fs, tt/125 °C, tt/−40 °C): slow Z
0.989 – 0.998 GΩ, −3 dB 2.5 – 3.0 kHz, slow noise 7.4 – 9.5 pA, bias current exactly
300/300 nA everywhere, wideband **min I_DC 21.1 – 28.8 nA (m = 2 %)**: the same
as before the supply fixes. The cascoded, follower-free op-amp (`opamp2`) was
re-tested on top and is *worse* (slow 2.0 vs 1.1 pA at 10 Hz): not adopted.

**Caveats.** Ideal current sources stand in for the bias references (their own
supply rejection and noise are unmodelled); each fix needs isolated n-wells
(Mc, and four input PMOS) and a quiet 1.4 V well bias for Mc; PSRR measured at tt/27 °C,
I_DC = 100 nA, 1 GΩ range only; the isolated input-pair wells add well
capacitance to the tail node, which had no visible effect on gain or noise here.

## 30. Detection numbers re-verified on the final front end (2026-10-17)

The coherent-detection Monte Carlo (§16, §18) was re-run on a channel extracted from the
**final** circuit: T-network slow TIA, VCM = 1.4 V, real PMOS bias mirror with a
supply-independent reference, Mc well on VCM, op-amp input pairs in their own wells,
constant op-amp bias currents (`FINAL=1 make_chan_opt.py`; data
`simulation/spice/results_final/`, 20 000 trials per point, 48 chips, 480 kchip/s,
100 µs, Pfa 1e-8; noise-only correlator kurtosis 3.01–3.04).

| I_DC | m = 2 % | m = 1 % | m = 0.5 % |
|---|---|---|---|
| 10 nA | 11.6 dB, Pd 0.040 | 5.5 dB | −0.6 dB |
| 30 nA | 21.1 dB, Pd 1 | 15.1 dB, Pd 0.52 | 9.0 dB |
| 100 nA | 31.1 dB | 25.1 dB | 19.1 dB, Pd 0.997 |
| 300 nA | 39.7 dB | 33.7 dB | 27.6 dB |
| 1 µA | 47.6 dB | 41.6 dB | 35.6 dB |

**Minimum I_DC for Pd ≥ 99.9 % at Pfa = 1e-8: ≈ 24.2 nA (m = 2 %), ≈ 48.5 nA
(m = 1 %), ≈ 97 nA (m = 0.5 %)**, identical (within 0.5 %) to §18, i.e. the slow-path,
op-amp and supply-rejection changes did not move the detection reach.

**Process note.** The first extraction used tight solver tolerances and gave a
30 nA noise 30 % too low (σ₀ = 5.9 µV against 8.5 µV), the same artifact documented
in §9/§14 (not reproducible in the §33 audit, where every tolerance setting gave identical
results; the low values were also below the circuit's own noise floor); with default tolerances (the gate voltage is fixed, so no lock is needed)
the numbers above are monotonic in I_DC. Slow-path gate voltages must be given with
six digits (a 5e-5 V rounding error at 1 µA is ≈ 1.5 V of output).

## 31. Range switches as real MOS devices: glitch, leakage, settling (2026-10-17)

Tool: `simulation/spice/tools/range_switch_tran.py`; data
`simulation/spice/results/range_switch.txt`. §24 used ideal switches. Here the
lower-gain resistor (111 MΩ or 10.1 MΩ) is in series with a thick-oxide NMOS
(`g5v0d10v5`, W = 2 µm, L = 0.5 µm; gate 0 ↔ 3.3 V in 10 ns) between the photodiode
node `x` and `s_out`; I_DC = 100 nA with the cancel device held at its locked gate
voltage (6-digit value per corner), Cf = 100 fF, final front end.

| case | switch | corner | peak glitch on s_out | DC shift after | settles to ±20 mV |
|---|---|---|---|---|---|
| 100 MΩ range ON | W 2 µm | tt/27 °C | +3 mV | −0.8 mV | immediately |
| 100 MΩ range OFF | W 2 µm | tt/27 °C | +7 mV (at +90 µs) | +0.8 mV | immediately |
| 10 MΩ range ON / OFF | W 2 µm | tt/27 °C | +2 / +7 mV | −0.9 / +0.9 mV | immediately |
| 100 MΩ range ON | W 10 µm | tt/27 °C | +13 mV | −0.8 mV | immediately |
| 100 MΩ range ON / OFF | W 2 µm | tt/125 °C | +3 / +5 mV | +0.1 / −0.1 mV | immediately |
| 100 MΩ range ON / OFF | W 2 µm | ss/125 °C | +3 / +6 mV | +0.5 / −0.5 mV | immediately |
| 10 MΩ range OFF | W 2 µm | tt/125 °C | +5 mV | −0.1 mV | immediately |

**Result: benign.** The switch's Ron (a few tens of kΩ) is negligible against 10–111 MΩ;
charge injection produces a 2–13 mV output glitch (smaller with the narrow switch:
width trades Ron against injection) and the output returns inside ±20 mV with no
measurable settling time, because with the DAC cancel locked the node has no
imbalance to redistribute. **Off-state leakage is negligible even at 125 °C: the
DC shift between the switch-on and switch-off states is ≤ 1 mV on the 1 GΩ
range (≈ 1 pA).** (A first 125 °C run with the 27 °C gate voltage showed `s_out`
railed at 2.02 V: that was an unlocked cancel device, not the switch.)

**Caveats.** One I_DC (100 nA) and PPG-free input; a range change while a large
residual DC error or a PPG peak is present was not simulated (the digital policy in §24
re-centres the output after the switch); the 1 GΩ range at very low I_DC (≤ 10 nA)
where 1 pA is 1 mV of a 10 pA signal was not simulated; the switch's gate drive
(0/3.3 V) and its driver are ideal.

## 32. Power budget and a 4x lower-power op-amp bias (2026-10-17)

Tools: `simulation/spice/build/power.py`-style supply-current measurement of the final
analog design (digital ADC/DAC/controller logic not included); bias and Cf sweeps with an
AC peaking check (`lowpower.py` family); data `simulation/spice/results/lowpower.txt`.

**Baseline power (op-amp bias 2 µA slow / 4 µA wide):** 81 µA total, **268 µW at tt/27 °C,
3.3 V; 241 – 299 µW over corners, ±10 % supply** (wideband path 181 µW, slow path
87 µW). About 3x the original 87 µW target.

**Bias can be reduced 4x without changing detection reach.** Sweeping the op-amp
reference currents with the rest fixed (tt/27 °C, I_DC = 100 nA, m = 2 %):

| bias slow / wide | wideband min I_DC | slow Z | slow noise | analog power |
|---|---|---|---|---|
| 2 / 4 µA (baseline) | 24.3 nA | 0.996 GΩ | 8.4 pA | 268 µW |
| 1 / 4 µA | 23.7 nA | 0.997 GΩ | 8.4 pA | |
| 2 / 2 µA | 24.5 nA | 0.996 GΩ | 8.4 pA | |
| 1 / 2 µA | 23.9 nA | 0.997 GΩ | 8.4 pA | 133 µW |
| **0.5 / 1 µA** | **24.2 nA** | 0.996 GΩ | 8.4 pA | **66 µW** |
| 0.25 / 0.5 µA (AC check only) | | | | 34 µW |

(Power scales linearly with the bias.) The wideband response has no secondary
resonance at any bias or corner. The cost is lower slow-op-amp GBW, which raised
slow-path response peaking from 2.3 dB (2 µA) to 4.4 dB (0.5 µA) at 50 fF; it is
removed by a larger feedback capacitor, scaling as Cf ∝ 1/√Rf:

| range | Cf at 2 µA bias (§24) | Cf for 0.5 µA bias | peaking, 3 corners | −3 dB |
|---|---|---|---|---|
| 1 GΩ | 50 fF | **150 fF** | 0.03 – 0.28 dB | 1.1 – 1.3 kHz |
| 100 MΩ | 100 fF | **500 fF** | 0.16 – 0.67 dB | 3.6 – 4.0 kHz |
| 10 MΩ | 500 fF | **1.5 pF** | 0.29 – 0.68 dB | 10.6 – 11.9 kHz |

**Low-power configuration (adopted as the option, not yet the default in every earlier
table): op-amp bias 0.5 µA (slow) / 1 µA (wide), Cf 150 fF / 500 fF / 1.5 pF.**
Analog power **61 – 74 µW over corners and ±10 % supply** (tt/27 3.3 V 66 µW: wideband
path 46 µW, slow path 21 µW; ss/125 °C 2.97 V 61 µW; ff/−40 °C 3.63 V 72 µW), i.e.
under the 87 µW target, analog only. Detection reach at I_DC = 100 nA, m = 2 %
(5 corner/temperature points): 21.5 – 30.1 nA against 21.1 – 28.8 nA at the baseline
bias, **2 – 4 % worse** (wideband input noise 646 fA/√Hz vs 628 at tt/27 °C); slow Z
0.994 – 0.997 GΩ, slow noise unchanged, slow −3 dB 1.1 – 1.3 kHz (still ≫ the PPG band).

**Caveats.** Digital power (ADC 10 bit / 2 kS/s, 12-bit DAC with a 100 kHz
sigma-delta, controller) and the references' own current are not included: Iref
and the bias references are ideal sources here; the lower GBW was checked by AC
peaking, not by a loop-gain/phase-margin measurement or transient; the supply
rejection (§28–§29) and the servo/ranging results (§23–§24) were not re-run at the
low bias (the slow plant bandwidth is ~1.2 kHz instead of 2.8 kHz, well above the
servo's 0.05 Hz corner, but this was not simulated); PVT checked at
tt/27, ss/125, ff/−40, tt/125, tt/−40 only.

**§32 addendum: caveats closed (low-power configuration re-checks, 2026-10-17).**
* **Supply rejection (§28–§29) at the 0.5 / 1 µA bias** (`results_lowpower.txt` in
  `simulation/servo/`): supply-equivalent input current per V/√Hz, 1 GΩ range: slow
  0.24 pA (0.5–1 Hz), 0.31 pA (10 Hz), 1.96 pA (100 Hz), 20 pA (1 kHz); wideband
  0.13 nA (10 kHz), 1.2 nA (100 kHz), 14 nA (300 kHz), **619 nA (1 MHz)**. The slow path
  and the wideband path up to 300 kHz are as good as or better than at the higher
  bias (the 1 MHz wideband figure is 1.9x worse than 330 nA); the 100 MΩ range gives
  the same values (0.30 / 1.95 / 20.2 pA at 10 / 100 / 1000 Hz).
* **Servo and auto-ranging on the low-power plants** (plant fits: 1 GΩ
  f0 = 1.26 kHz, Q = 0.57; 100 MΩ 4.1 kHz, Q = 0.54; 10 MΩ 14 kHz, Q = 0.51: overdamped,
  no peaking): power-up lock 24 ms, range switch at 125 ms, PPG gain 0.9986 –
  0.9988, added noise equal to the analog values (0.8 / 2.9 / 8.4 / 24.5 / 78.7 pA at
  5 / 30 / 100 / 300 nA / 1 µA), 0 re-acquisitions, i.e. identical to §24 within
  rounding. Select the plants with `SERVO_DATA_PREFIX=data_lp_` (data dumped by
  `corner_run.py` with `DUMP=`).

**§32 addendum 2: loop gain and phase margin (measured, replacing the peaking proxy).**
Tool `simulation/spice/tools/loopgain_final.py`, data
`simulation/spice/results/loopgain_final.txt`: AC voltage injected in series with each TIA's
feedback path in the final netlist (single-injection; the feedback network is
high-impedance against a low-impedance output, so the Middlebrook correction is small;
the same method as `loopgain_pm.py` for the first-pass TIA gave 81° / 67°).

| configuration | slow loop: DC gain, unity-gain f, PM | wide loop: DC gain, unity-gain f, PM, GM |
|---|---|---|
| baseline bias 2 / 4 µA, Cf 50 fF, 1 GΩ, tt/27 °C | 47.6 dB, 2.2 kHz, **47.6°** | 85.3 dB, 5.3 MHz, 90.2°, 42.2 dB |
| **low power** 0.5 / 1 µA, Cf 150 fF, 1 GΩ, tt/27 °C | 47.4 dB, 1.4 kHz, **66.6°** | 88.2 dB, 1.64 MHz, 66.4°, 15.9 dB |
| low power, ss/125 °C, 2.97 V | 43.5 dB, 1.18 kHz, 64.5° | 82.8 dB, 1.33 MHz, 61.7°, 12.9 dB |
| low power, ff/−40 °C, 3.63 V | 49.2 dB, 1.57 kHz, 68.4° | 90.5 dB, 1.93 MHz, 71.2°, 20.9 dB |
| low power, 100 MΩ range (Cf 500 fF) | 66.6 dB, 4.5 kHz, 66.7° | 88.2 dB, 1.63 MHz, 66.5°, 15.9 dB |
| low power, 10 MΩ range (Cf 1.5 pF) | 81.4 dB, 15 kHz, 79.7°, GM 43.5 dB | 88.2 dB, 1.63 MHz, 66.5°, 15.9 dB |

**Result.** The low-power configuration is stable with margin everywhere checked: slow-loop
PM 64.5 – 79.7°, wideband-loop PM 61.7 – 71.2° with 12.9 – 20.9 dB gain margin. The
**baseline slow loop was the weakest case** (PM 47.6°, consistent with its 2.3 dB peaking),
so the larger feedback capacitors adopted for the low-power bias also improve damping. The
slow loop's DC gain is only 43 – 49 dB at the 1 GΩ range (the T-network divides the
feedback), so its closed-loop transimpedance error is ≈ 0.3 – 0.7 %, consistent
with the measured 0.986 – 0.998 GΩ.

**Caveats.** tt/27, ss/125, ff/−40 corners only; I_DC = 100 nA; Cj = 10 pF assumed (a larger
photodiode capacitance lowers the margin); the injection method is approximate for the
slow loop at its crossover (1 – 4 kHz), where the T-network impedance is highest.

## 33. Audit of the work so far (2026-10-17)

A review pass over the whole record: re-running checks independently, recomputing derived
numbers from the raw files, and hunting for stale statements. Tools:
`simulation/detect/test_mc_analytic.py`, and the scratch checks summarised below.

**Confirmed (independent checks that passed):**
* **Detection Monte Carlo vs closed form.** For a flat channel with white noise the analytic
  answer is `d = (m·I_DC/√S_in)·√(2·T_int)`. The Monte Carlo gave d = 53.32 against 53.26
  (0.11 %), σ₀ = 3.751 vs 3.755 µV, and a Gaussian noise-only correlator (kurtosis 3.015).
  Together with the earlier analytic-vs-Monte-Carlo agreement on the real channel (σ₀ 24.30 vs
  24.13 µV), the detection numbers (§16–§21, §30) rest on a validated engine.
* **Original runner.** `run-tia-sim.sh` still reproduces the `TIA-DESIGN.md` §9 numbers exactly
  (0.997 GΩ, 2.33 kHz, 136 µs rise, 85.3 µW, 1.56 mV).
* **The slow-path noise is dominated by the cancel device.** Replacing the NMOS sink by an
  ideal noiseless sink of the same DC current removes most of it: input-referred 3.2 / 1.16 /
  0.44 / 0.22 pA/√Hz at 1 / 10 / 100 / 1000 Hz (I_DC = 100 nA) becomes 0.47 / 0.17 / 0.08 /
  0.10 pA/√Hz, independent of I_DC (the 1 µA case with the real device is 30 / 10.8 / 3.9 /
  1.5 pA/√Hz). So 85 – 95 % of the slow-path noise at 100 nA comes from the cancel device
  (6.7x at 10 Hz), and the real DAC's noise sets the slow path's performance; what the sky130
  HV flicker model gives is unverified against silicon.
* **Slow-path results are tolerance independent** (Z = 0.9962 GΩ and identical noise at 1, 10,
  100, 1000 Hz with default and tight solver settings).

**Corrected:**
* **Supply-noise budgets in §28 and §29** (arithmetic errors; the 1 MHz limit used a 0.5 pA
  noise floor where the input-referred floor is ≈ 5.5 pA because the channel gain has rolled
  off). Now: §28 (before the §29 fixes) 1 MHz ≲ 0.3 µV/√Hz, tone ≲ 54 µV; §29 (final)
  100 kHz ≲ 69 µV/√Hz, 300 kHz ≲ 12 µV/√Hz, **1 MHz ≲ 3.3 µV/√Hz**, tones ≲ 110 mV / 10 mV /
  **0.6 mV** at 100 kHz / 300 kHz / 1 MHz; slow ≲ 210 mV/√Hz at 10 Hz, 42 mV/√Hz at 100 Hz,
  2.5 mV/√Hz at 1 kHz. (The §27 budget is the superseded pre-fix one.)
* **Tight solver tolerances DO corrupt `.noise` for some circuits (§9, §14, §20, §30): now
  demonstrated, with the cause still unknown.** For the nominal circuit the result is identical
  under every tolerance setting (wideband 574.6 / 587.9 / 5523 fA/√Hz at 10 kHz / 100 kHz /
  1 MHz with the slow path removed; slow-path 3199 / 1156 / 436 / 222 fA/√Hz at 1 / 10 / 100 /
  1000 Hz for tight 0 and 1), so the earlier 391 fA/√Hz wideband outliers could not be
  reproduced. But for the source-degenerated cancel device (§34) the tight-tolerance analysis
  returned **5.8 / 2.1 / 0.7 / 0.2 fA/√Hz** (below the 4 fA/√Hz 1 GΩ thermal floor, i.e. impossible)
  for every Rsd ≥ 1 MΩ at 100 nA and ≥ 100 kΩ at 1 µA, where default tolerances gave smooth,
  monotonic values (e.g. 380, 231 fA/√Hz at 10 Hz for 1 MΩ, 3 MΩ). The same symptom (0.0 pA)
  had appeared once in the §20 ff/−40 °C slow-noise column. The earlier wideband outliers were
  also below that chain's own floor (391 vs 588 fA/√Hz with the slow path removed). **Rule:
  noise is always analysed with default tolerances; tight tolerances are used only to bisect the
  DC lock.** `corner_run.py` now follows it, and the 11-point PVT × supply matrix was re-run
  with the corrected slow-noise analysis: every number reproduced to the digit (slow Z
  0.989 – 0.998 GΩ, slow noise 7.4 – 9.5 pA, wideband min I_DC 21.1 – 28.8 nA), so the
  matrix of §29 stands. §19's wideband columns (obtained in the first, tight-tolerance flow)
  remain superseded by §20.
* **`STATUS.md` stale entries** (still listing already-finished work as open, an outdated bias
  spread, and an out-of-date reproduce block): fixed in the same commit.

**Known weak points that the audit could not remove (unchanged, restated):**
* the noise *magnitudes* depend on the sky130 HV device flicker model (no silicon data);
* the DAC is behavioral and its noise is *assumed* to equal one NMOS sink (the dominant
  slow-path noise source, see above);
* all bias references, the poly resistors and the supply are ideal elements;
* the relay-attack and cryptography items (§25) are unresolved design questions;
* digital power, layout, and area (Cc ≈ 50 pF ≈ 25 000 µm²) have not been addressed.

## 34. Source degeneration of the cancel device cuts the slow-path noise 3–8x (2026-10-17)

Found as a follow-up to §33's result that the cancel (sink) device supplies 85–95 % of the
slow-path noise. A resistor between its source and ground (`sdeg=` option of
`wide_noise_sweep.py`; the gate voltage is re-bisected for each value) reduces its
gate-referred flicker current by ≈ 1/(1 + gm·R). Default solver tolerances (see §33);
raw data `simulation/spice/results/sdeg_and_matrix_audit.txt`. T-network 1 GΩ range, tt/27 °C.

| I_DC | Rsd | DC drop | slow noise RMS 0.5–100 Hz | @10 Hz | wideband min I_DC (m = 2 %) |
|---|---|---|---|---|---|
| 10 nA | none | 0 | 1.6 pA | 212 fA/√Hz | 23.1 nA |
| 10 nA | 3 MΩ / 10 MΩ | 30 / 100 mV | 1.4 / 1.4 pA | 190 / 179 | 23.0 / 23.0 |
| 100 nA | none | 0 | 8.4 pA | 1156 | 24.3 nA |
| 100 nA | 300 kΩ | 30 mV | 5.0 pA | 679 | 24.2 |
| 100 nA | 1 MΩ | 100 mV | 2.8 pA | 380 | 24.0 |
| 100 nA | **3 MΩ** | 300 mV | **1.8 pA** | 231 | 23.9 |
| 1 µA | none | 0 | 78 pA | 10844 | 36.1 nA |
| 1 µA | 100 kΩ | 100 mV | 22 pA | 3047 | 32.4 |
| 1 µA | **300 kΩ** | 300 mV | **9.5 pA** | 1301 | 31.2 |

**Result.** At a ≈ 0.3 V drop the slow-path noise falls **4.7x at 100 nA and 8.2x at 1 µA**
(floor at 10 nA: 1.4 pA, the op-amp/Rf level; the ideal-noiseless-sink floor at 10 Hz is
0.17 pA/√Hz ≈ 1.3 pA RMS). The 1 MΩ and 3 MΩ cases at 1 µA cannot lock (the drop approaches the
1.4 V node voltage). The wideband path also benefits at high photocurrent (1 µA: 36.1 → 31.2 nA)
and is unchanged below 100 nA.

**Design rule.** Degenerate the DAC output devices so that I·R ≈ 0.3 V *at the I_DC being
cancelled*, i.e. R ∝ 1/I_DC (≈ 3 MΩ at 100 nA, 300 kΩ at 1 µA): a switched or trimmed
resistor per DAC range. In PPG terms the SNR for a 2 % modulation improves from 8.4 pA to 1.8 pA
of noise at 100 nA (+13 dB). The headroom limit is I·R < ≈ 0.5 V at the 1.4 V `x` node.

**Caveats.** Applies to the single behavioral NMOS sink used throughout; a real segmented
DAC's noise and the resistor's own noise/mismatch (included in SPICE as thermal noise only) were
not designed; the flicker magnitude depends on the sky130 HV model (no silicon data); only
tt/27 °C and the 1 GΩ range were run.

**§33 addendum (further audit results, same day).**
* **ngspice noise normalisation verified.** A 1 kΩ resistor gives `onoise_spectrum` =
  4.0714 nV/√Hz, exactly √(4kT·R) at 27 °C (4.0714): the spectrum is a one-sided density in
  V/√Hz, as the Monte Carlo assumes. (Had it been two-sided every noise figure and minimum
  photocurrent would have been 3 dB off.)
* **Generated files match their generators.** Re-running `gen_afe.py` and `gen_afe_direct.py`
  leaves the working tree unchanged.
* **Servo plant fit quality** (2nd-order fit to the SPICE plants): worst-case |ln(fit/data)|
  is 1.8 – 3.4 % over 1 – 100 Hz (the PPG and servo band), 3 – 7 % to 1 kHz, 13 – 34 % at
  1 – 10 kHz and up to 79 % at 10 – 100 kHz. The servo and PPG results only depend on the
  low-frequency region; the high-frequency fit error is irrelevant to them, and the
  transistor-level cross-check of §23 (3.6 mV rms vs a 150 mV PPG) is the real validation.
* **Spoofing study re-run on the final channel** (`SPOOF_RES=…/results_final`,
  `spoof_results_final.txt`): blind injection at the legitimate amplitude 16.3 % (D0) / 0 %
  (D1), amplitude 100x 49.6 % / 0 %, 90 %- / 95 %-known chips 8.3 % / 28.5 % (D1), relay
  at 50 / 130 / 260 / 520 ns: 99.6 / 97.3 / 35.4 / 0 % (D1); legitimate Pd 0.9990 with D1.
  Identical (within trial statistics) to §25, so the §25 conclusions do not depend on the
  channel version.
* **Results taken with tight solver tolerances that were checked**: the §20 slow-noise column, the
  servo plant/PSD dumps and the range tables use values that match the default-tolerance numbers
  (e.g. 1156 fA/√Hz at 10 Hz, 8.4 pA RMS, Z = 0.996 GΩ); no corrupted values (sub-floor noise)
  appear in them.

## 35. How long must the code integrate to reach low photocurrents? (2026-10-17)

The pattern check misses the original 10 nA goal (needs ≈ 24 nA at m = 2 % for a 100 µs
decision). The one purely electronic mitigation is a longer integration window.
`chip_rate_sweep.py` with `LONG=1` on the final channel (I_DC = 100 nA channel,
`results_final/long_integration.txt`), 480 kchip/s, code length N growing with T_int,
m = 2 %, Pd 99.9 % at Pfa 1e-8:

| N (chips) | T_int | min I_DC (m = 2 %) |
|---|---|---|
| 48 | 100 µs | 24.3 nA |
| 96 | 200 µs | 17.2 nA |
| 144 | 300 µs | 14.0 nA |
| 192 | 400 µs | 12.1 nA |
| 288 | 600 µs | 9.9 nA |
| 480 | 1.0 ms | 7.7 nA |
| 720 | 1.5 ms | 6.2 nA |
| 960 | 2.0 ms | 5.4 nA |
| 1440 | 3.0 ms | 4.4 nA |

It follows min I_DC ∝ 1/(m·√T_int). **T_int needed to reach I_DC = 10 nA: ≈ 0.6 ms at m = 2 %,
≈ 2.4 ms at m = 1 %, ≈ 9.4 ms at m = 0.5 %; to reach 5 nA: ≈ 2.4 ms / 9.5 ms / 38 ms.** The
longer code also raises the guess-resistance (2^-N), but it multiplies the decision latency
and the verification can no longer be per 100 µs sample.

**Caveats.** The noise below 1 kHz was set equal to its 1 kHz value (the channel files start at
1 kHz), so long windows (> 1 ms) ignore any 1/f, mains or ambient-light interference that a real
sensor will have; the channel and the legitimate amplitude must stay stationary over the window;
slow ambient flicker (100/120 Hz lighting) is not modelled. Treat the table as the white-noise
limit, i.e. optimistic for T_int ≳ 1 ms.
