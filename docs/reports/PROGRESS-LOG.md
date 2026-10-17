# Progress log (chronological)

Each line: commit, what was done, what we learned. Newest at the bottom. Technical section
numbers (§) refer to [`../afe-architecture.md`](../afe-architecture.md). Full history:
`git log`.

## Phase 0: background and first hand design (Sep 2026)

| Commit | Date | What | Learned |
|---|---|---|---|
| `cf9458b`, `251ba10` | 09-08 | research papers added | background reading |
| `64eb2cf` | 09-23 | first single-TIA netlist and design memo | the brief's numbers contradict each other (1 GΩ gain vs noise and speed targets) |
| `d360c35`, `4cfd20b` | 09-23, 09-28 | dual-path architecture, detection requirements (Pd/Pfa), hand noise budget | everything still hand-derived, unsimulated |

## Phase 1: first real simulation (15 Oct)

| Commit | What | Learned |
|---|---|---|
| `1f57601` | installed ngspice + sky130 models, ran the first TIA | the hand netlist had four real bugs; the transistor "resistor" was ~650 GΩ not 1 GΩ; bandwidth 2.3 kHz not 5 kHz |

## Phase 2: choosing the architecture (16 Oct)

| Commit | What | Learned |
|---|---|---|
| `126e071`, `254a55f` | schematic update; loop gain / phase margin of the first TIA | stable (81° / 67°) |
| `370b82b` | shared input through a regulated cascode + mirror (§12) | needs a fixed bias current to be fast; DC photocurrent saturates the 1 GΩ amplifier |
| `c984d58` | first DC-cancel servo (§13) | works from power-up with an acquisition boost; needs a startup transient |
| `63fc4f6` | slow-path noise with the mirror in the path (§14) | 50–325 pA: far too noisy (mirror flicker noise) |
| `64abd78` | slow path directly on the photodiode, fast path AC-coupled (§15) | 29x less slow-path noise; the chosen architecture |

## Phase 3: detection, robustness, and fixes (17 Oct)

| Commit | What | Learned |
|---|---|---|
| `1b44b8c` | coherent-detection Monte Carlo (§16) | needs ≥50 nA at 2 % (first estimate); ~5x worse than the hand budget |
| `c30cd9e` | wideband noise reduction (§17) | the "regulated" cascode was never regulating; mirror and bias tuned: 24 nA |
| `2776ce2` | real PMOS bias mirror replaces ideal sources (§18) | only ~0.1–0.2 dB penalty |
| `0ca0d48`, `cabfd27` | process/temperature corners (§19), poly T-network feedback (§20) | the transistor resistor spans 0.8 MΩ–120 GΩ; T-network gives 0.99 GΩ at every corner |
| `7715230` | chip-rate / code-length study (§21) | the 480 kHz bandwidth shortfall costs only ~1 dB; latency is the real lever |
| `7cc8a3a` | `docs/STATUS.md` created | one-page summary |
| `f24c7ae` | supply sensitivity (§22) | design broke at −10 % supply; fixed by mid-level 1.4 V |
| `a6669c4`, `b30b93c` | digital servo (§23) and 3-range auto-ranging (§24) | locks in ~90 ms; 1 GΩ clips pulses above ~250 pA so ranges were added |
| `b339583` | spoofing study (§25) | correlation-only detector is passable (16 % blind); relay attack ≤130 ns still works; LFSR predictable after 64 chips |
| `f85f11b`, `a1f7014` | architecture diagram | |
| `bce71d5` | mismatch sensitivity (§26) | ≤ 1 % effect |
| `8d9e7f7`–`81b7e1f` | supply rejection (§27–§29) | three wrong guesses, then found the transistor body effect; 24–13 000x better |
| `2664977` | detection re-run on the final front end (§30) | numbers unchanged (24 / 49 / 97 nA) |
| `1d96619` | real MOS range switches (§31) | 2–13 mV glitch, negligible leakage |
| `4c2608a`, `60f32a9`, `80525b0` | power, low-power bias, stability (§32) | 268 → 66 µW; phase margin 62–80° |
| `39e56ba`, `b1965e8`, `7fceb56`, `875a8d7` | audit (§33) and cancel-device degeneration (§34) | engine and units verified; docs errors fixed; degeneration cuts slow noise 4.7–8x |

## Phase 3b: after the audit (17 Oct)

| Work | What | Learned |
|---|---|---|
| integration-time study (§35) | min I_DC vs code length | ∝ 1/√T_int: 10 nA needs ~0.6 ms at 2 % |
| degenerated cancel device in the servo study (§36) | auto-range with the 0.3 V-drop sink noise | PPG SNR +13 dB at 100 nA, +17.5 dB at 1 µA |
| DAC cell sizing (§37) | noise vs area and degeneration | resistor matters most; noise ~ area^-0.4 |
| bandwidth correction (§38) | wideband band is 1.8–63 kHz, not ~280 kHz | status page was stale; detection unaffected |
| optimal-receiver bound (§38 addendum) | matched+whitened receiver vs rect correlator | only +0.5 dB; a formula error was caught |

## Phase 4: reports (from 17 Oct)

| Report | Date | Covers |
|---|---|---|
| [`2026-10-17-overview.md`](2026-10-17-overview.md) | 10-17 | whole project so far, in plain language |
| [`2026-10-17-02-audit-and-noise.md`](2026-10-17-02-audit-and-noise.md) | 10-17 | audit, cancel-device noise and degeneration, integration time |
| [`2026-10-17-03-dac-bandwidth-receiver.md`](2026-10-17-03-dac-bandwidth-receiver.md) | 10-17 | DAC sizing, bandwidth correction, receiver bound |
