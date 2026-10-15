# TrustSense Layer 1 — AFE Architecture Spec

Status: derived, unsimulated. Every number below is tagged **[DERIVED §n]**
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
