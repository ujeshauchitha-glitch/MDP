"""Residual test with a truncated channel FIR as template (hardware-friendly: +/-1 code, K-chip memory, 8-bit coefficients)."""
import sys, numpy as np, trustsense_twin as t
from trustsense_twin import cm, NS, N, L

f = t.FastPath(100e-9, seed=33)
STEP, LSB = 4, 100e-6
h = np.fft.irfft(f.Hg, n=L)            # circular impulse response of the channel on the 16x grid
def fir_template(cu, K):
    hk = np.zeros(L); hk[:K * 16] = h[:K * 16]
    q = np.abs(hk).max() / 127; hk = np.round(hk / q) * q          # 8-bit coefficients
    return np.fft.irfft(np.fft.rfft(cu, axis=1) * np.fft.rfft(hk), n=L, axis=1)
def stats(light, K, trials=6000):
    Z, R = [], []
    for _ in range(trials // 500):
        codes = f.random_codes(500); cu = cm.upsample(codes)
        sig = f.channel(light(codes)) if light else 0.0
        y = (sig + cm.noise_td(f.rng, f.S_out, 500))[:, f.win][:, ::STEP]
        y = np.round(y / LSB) * LSB
        tm = fir_template(cu, K)[:, f.win][:, ::STEP]
        c = cu[:, f.mid][:, ::STEP]
        zc = (y * c).sum(axis=1)
        mu = (y * tm).sum(axis=1) / (tm * tm).sum(axis=1)
        Z.append(zc); R.append(((y - mu[:, None] * tm) ** 2).sum(axis=1))
    return np.concatenate(Z), np.concatenate(R)
zn, _ = stats(None, 8); eta = cm.ETA_SIGMAS * zn.std()
cases = [("partial f=0.75", f.partial(1, .75)), ("partial f=0.9", f.partial(1, .9)), ("relay 260ns", f.relay(1, 260e-9)), ("blind 3x", f.blind(3))]
print("K chips  legit Pd | " + " | ".join(n for n, _ in cases))
for K in (2, 4, 8, 12, 16):
    zl, rl = stats(f.legit(), K); thr = np.quantile(rl, 0.999)
    row = [np.mean((zl > eta) & (rl < thr))]
    for n, lt in cases:
        z, r = stats(lt, K); row.append(np.mean((z > eta) & (r < thr)))
    print(f"{K:5d}   " + "  ".join(f"{v:7.4f}" for v in row), flush=True)
