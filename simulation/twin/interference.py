"""Ambient-light interference on the fast path (twin, I_DC = 100 nA total photocurrent of which the interferer is a sine of
amplitude A_int, m = 2 %, 6-bit/300 uV clipping included). Legitimate acceptance of the D1 detector and the correlator-only detector,
with the residual threshold calibrated WITHOUT interference (as it would be in the field)."""
import numpy as np
import trustsense_twin as t
from trustsense_twin import cm, L

f = t.FastPath(100e-9, seed=88)
fs = cm.FS
tt = np.arange(L) / fs
def sine(freq, amp):
    ph = f.rng.uniform(0, 2 * np.pi, size=(500, 1))
    return lambda c: f.m * f.i_dc * cm.upsample(c) + amp * np.sin(2 * np.pi * freq * tt[None, :] + ph)
print("interferer (peak, as fraction of I_DC=100 nA)  freq    | legit D1 accept  corr-only accept | peak output of interferer")
rows = []
for freq in (100.0, 1e3, 10e3, 100e3):
    h = np.abs(np.interp(freq, f.fg, np.abs(f.Hg)))
    for frac in (0.01, 0.1, 1.0, 10.0):
        amp = frac * f.i_dc
        z, r = f._collect(sine(freq, amp), 3000)
        a1 = np.mean(f.accept(z, r)); a0 = np.mean(z > f.eta)
        s = f"{frac*100:7.0f} % ({amp*1e9:6.1f} nA)  {freq/1e3:7.1f} kHz | {a1:9.3f}        {a0:9.3f}        | {amp*h*1e3:9.3f} mV"
        print(s, flush=True); rows.append(s)
open("interference_results.txt", "w").write("\n".join(rows) + "\n")
