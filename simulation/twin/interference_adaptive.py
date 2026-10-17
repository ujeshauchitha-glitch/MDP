"""Adaptive thresholds from dark (LED-off) frames: eta = 5.61 sigma(z_dark), residual threshold = 99.9 % quantile of the dark-frame residual.
Compares legit acceptance and attack acceptance with an ambient interferer present."""
import numpy as np
import trustsense_twin as t
from trustsense_twin import cm, L

f = t.FastPath(100e-9, seed=99)
tt = np.arange(L) / cm.FS
def with_int(base_light, freq, amp):
    def g(c):
        ph = f.rng.uniform(0, 2 * np.pi, size=(c.shape[0], 1))
        return (base_light(c) if base_light else 0.0) + amp * np.sin(2 * np.pi * freq * tt[None, :] + ph)
    return g
out = []
print("interferer           |  legit D1  | blind 1x  blind 3x  partial.9 | corr-only blind 1x   (adaptive thresholds from dark frames)")
for freq in (100.0, 1e3, 10e3):
    for frac in (0.0, 0.01, 0.1, 1.0):
        amp = frac * f.i_dc
        dark = with_int(None, freq, amp) if amp else (lambda c: np.zeros((c.shape[0], L)))
        zd, rd = f._collect(dark, 6000)
        eta = cm.ETA_SIGMAS * zd.std(); thr = np.quantile(rd, 0.999)
        def acc(light):
            z, r = f._collect(light, 6000)
            return np.mean((z > eta) & (r < thr)), np.mean(z > eta)
        leg = acc(with_int(f.legit(), freq, amp))[0]
        b1, b1c = acc(with_int(f.blind(1), freq, amp)); b3, _ = acc(with_int(f.blind(3), freq, amp)); p9, _ = acc(with_int(f.partial(1, .9), freq, amp))
        s = f"{freq/1e3:6.1f} kHz {frac*100:5.0f} % | {leg:9.3f}  | {b1:8.4f} {b3:8.4f} {p9:9.4f} | {b1c:9.4f}"
        print(s, flush=True); out.append(s)
open("interference_adaptive_results.txt", "w").write("\n".join(out) + "\n")
