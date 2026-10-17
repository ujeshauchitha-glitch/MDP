"""How must the fast-path output be digitised? Sample rate and ADC resolution vs detection SNR (twin, 100 nA, m = 2 %).
The correlator multiplies the (sampled, quantised) output by the +/-1 code and sums over the 100 us window."""
import numpy as np, trustsense_twin as t
from trustsense_twin import cm, NS, N, OS

f = t.FastPath(100e-9, seed=9)
rng = np.random.default_rng(4)
codes = f.random_codes(1500)
cu = cm.upsample(codes)
y_sig = f.channel(f.legit()(codes))
nz = cm.noise_td(rng, f.S_out, codes.shape[0])
y = (y_sig + nz)[:, f.win]
yn = nz[:, f.win]
print(f"per-sample output noise (at {cm.FS/1e6:.2f} MS/s): {yn.std()*1e6:.0f} uV rms, signal peak {np.abs(y_sig[:, f.win]).max()*1e6:.0f} uV, correlator sigma0 {f.s0*1e6:.2f} uV")
cm_mid = cu[:, f.mid]

def d_of(yv, step, lsb):
    """detection SNR with sampling every `step` (OS/step samples per chip) and quantisation lsb [V] (0 = ideal)."""
    ys = yv[:, ::step]
    if lsb:
        ys = np.round(ys / lsb) * lsb
    cs = cm_mid[:, ::step]
    z = (ys * cs).sum(axis=1) / ys.shape[1]
    return z.mean() / z.std()          # signal present: quantiser acts on signal + noise


print("\nsamples/chip  lsb[uV]   d (m=2%)   loss vs ideal 16/chip")
base = d_of(y, 1, 0)   # note: z.std() with signal present includes the code-dependent ISI term (small)
for step, spc in ((1, 16), (2, 8), (4, 4), (8, 2), (16, 1)):
    for lsb in (0, 10e-6, 30e-6, 100e-6, 300e-6, 1e-3):
        d = d_of(y, step, lsb)
        print(f"{spc:8d}   {lsb*1e6:7.0f}   {d:8.2f}   {20*np.log10(d/base):+6.2f} dB")
