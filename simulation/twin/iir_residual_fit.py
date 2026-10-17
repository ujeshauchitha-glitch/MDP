"""Residual template from a low-order IIR fit of the channel (hardware: one small filter on the +/-1 code)."""
import numpy as np, trustsense_twin as t
from scipy.signal import lfilter, freqz
from trustsense_twin import cm, NS, N, L

f = t.FastPath(100e-9, seed=44)
STEP, LSB = 4, 100e-6
FS4 = cm.FS / STEP
fr = np.fft.rfftfreq(L, 1 / cm.FS)
m = fr < FS4 / 2
# zero-order-hold code upsampled by 4 per chip then through channel: fit H on the 4/chip grid (include the 16x-grid sinc of the hold)
w = 2 * np.pi * fr[m] / FS4
Hd = f.Hg[m]
def stmcb(h, nb, na, iters=40):
    """Steiglitz-McBride IIR fit of impulse response h (numerator order nb, denominator order na)."""
    n = len(h)
    u = np.zeros(n); u[0] = 1.0
    a = np.r_[1.0, np.zeros(na)]
    for _ in range(iters):
        hf = lfilter([1.0], a, h); uf = lfilter([1.0], a, u)
        # solve  hf*[1,a1..] ~ uf*b   (LS)
        A = np.zeros((n, nb + 1 + na))
        for k in range(nb + 1):
            A[k:, k] = uf[:n - k]
        for k in range(1, na + 1):
            A[k:, nb + k] = -hf[:n - k]
        sol, *_ = np.linalg.lstsq(A, hf, rcond=None)
        bb = sol[:nb + 1]; a = np.r_[1.0, sol[nb + 1:]]
    return bb, a
H4 = np.zeros(L // STEP // 2 + 1, dtype=complex)
n4 = L // STEP
Hfull = f.Hg
H4[:len(fr[m])] = Hfull[m][:len(H4)]
h4 = np.fft.irfft(H4, n=n4)[:600]
def fit(nb, na):
    return stmcb(h4, nb, na)
print("order(b,a)  relative impulse-response error")
best = None
for nb, na in ((2, 2), (3, 3), (4, 4)):
    b, a = fit(nb, na)
    imp = np.zeros(len(h4)); imp[0] = 1.0
    err = np.linalg.norm(lfilter(b, a, imp) - h4) / np.linalg.norm(h4)
    stable = np.all(np.abs(np.roots(a)) < 1)
    print(f"  ({nb},{na})  {err:.3f}  stable={stable}")
    if stable and (best is None or err < best[0]): best = (err, b, a, nb)
err, b, a, nb = best
print("using order", nb, "err", round(err, 3))

