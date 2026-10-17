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

STEP, LSB = 4, 100e-6
def q(y): return np.round(y / LSB) * LSB
def stats(light, K, trials=6000, nuis=False):
    Z, R = [], []
    for _ in range(trials // 500):
        codes = f.random_codes(500); cu = cm.upsample(codes)
        sig = f.channel(light(codes)) if light else 0.0
        y = q((sig + cm.noise_td(f.rng, f.S_out, 500))[:, f.win][:, ::STEP])
        tm = fir_template(cu, K)[:, f.win][:, ::STEP]
        c = cu[:, f.mid][:, ::STEP]
        zc = (y * c).sum(axis=1)
        if nuis:   # least squares on [template, 1]: offset removed
            n = y.shape[1]; G = np.stack([tm, np.ones_like(tm)], axis=2)
            A = np.einsum("bni,bnj->bij", G, G); b = np.einsum("bni,bn->bi", G, y)
            sol = np.linalg.solve(A, b[..., None])[..., 0]
            res = y - np.einsum("bni,bi->bn", G, sol)
        else:
            mu = (y * tm).sum(axis=1) / (tm * tm).sum(axis=1); res = y - mu[:, None] * tm
        Z.append(zc); R.append((res ** 2).sum(axis=1))
    return np.concatenate(Z), np.concatenate(R)
for K, nu in ((16, True), (48, False), (96, False), (96, True)):
    zn, _ = stats(None, K, nuis=nu); eta = cm.ETA_SIGMAS * zn.std()
    zl, rl = stats(f.legit(), K, nuis=nu); thr = np.quantile(rl, 0.999)
    out = [np.mean((zl > eta) & (rl < thr))]
    for lt in (f.partial(1, .75), f.partial(1, .9), f.relay(1, 260e-9)):
        z, r = stats(lt, K, nuis=nu); out.append(np.mean((z > eta) & (r < thr)))
    print(f"K {K:3d} offset-fit {nu!s:5s}: legit {out[0]:.4f} p.75 {out[1]:.4f} p.9 {out[2]:.4f} relay260 {out[3]:.4f}", flush=True)
