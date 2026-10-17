"""Validate the twin against the stand-alone SPICE-based studies (numbers quoted in docs/afe-architecture.md)."""
import time
import trustsense_twin as t

print("== fast path: twin vs detect_results.txt (m = 2 %, 48 chips, 480 kchip/s) ==")
ref_d = {"10n": 3.79, "30n": 11.31, "100n": 35.92, "300n": 96.42, "1u": 240.98}
for lab, i in t.LABEL_I.items():
    f = t.FastPath(i, seed=5)
    d = f.mu / f.s0
    print(f"I_DC={lab:4s} twin d={d:7.2f}  SPICE-MC d={ref_d[lab]:7.2f}  diff {100*(d/ref_d[lab]-1):+5.1f} %   min I_DC (Pd 99.9 %) {f.min_idc()*1e9:6.1f} nA")

print("\n== slow path: twin vs servo results (results_sdeg.txt, 2 % PPG, degenerated sink) ==")
ref = {"5n": ("1G", 0.7), "30n": ("100M", 1.4), "100n": ("100M", 1.8), "300n": ("10M", 4.2), "1u": ("10M", 10.5)}
sp = t.SlowPath()
for lab, (rg, noise) in ref.items():
    t0 = time.time()
    r = sp.run(t.SLOW_I[lab], 2.0, tstop=8.0)
    print(f"I_DC={lab:4s} range {r['range']:4s} (ref {rg:4s}) lock {r['lock_s']*1e3:5.1f} ms (ref 24.5) PPG gain {r['ppg_gain']:.4f} (ref ~0.999) "
          f"resid {r['resid_rms_pA']:5.1f} pA (ref {noise} pA RMS 0.5-100 Hz) reacq {r['reacq']}  [{time.time()-t0:.0f}s]", flush=True)
