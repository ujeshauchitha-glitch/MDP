"""Cheaper template: LP biquad (fit section 1) + two cascaded first-order high-pass stages built from shifts."""
import sys, numpy as np
from scipy.signal import sosfilt, tf2sos, lfilter
import hw_model as hm
from trustsense_twin import cm
f = hm.f
sos = tf2sos(hm.fit.b, hm.fit.a)
lp = sos[0].copy()
def make(k, nstage, fl):
    a = 2.0 ** -k
    def tmpl(c4):
        x = sosfilt(lp[None, :], c4, axis=1)
        for _ in range(nstage):
            x = lfilter([1 - a / 2 * 0 , -(1 - a)], [1, -(1 - a)], x, axis=1) if False else lfilter([1.0, -1.0], [1.0, -(1 - a)], x, axis=1)
        return x
    return tmpl
rng = np.random.default_rng(5); c = rng.choice([-1., 1.], size=(50, 1000))
for k, ns in ((8, 1), (8, 2), (7, 2), (9, 2), (7, 1)):
    tm = make(k, ns, None)
    pk = np.abs(tm(c))[:, 300:].max(); sc = 100.0 / pk
    def tf(c4, tm=tm, sc=sc): return np.round(tm(c4) * sc)
    hm.template = tf
    zn, _ = hm.hw_stats(None); eta = cm.ETA_SIGMAS * zn.std()
    zl, rl = hm.hw_stats(f.legit()); thr = np.quantile(rl, 0.999)
    out = [np.mean((zl > eta) & (rl < thr))]
    for lt in (f.partial(1, .75), f.partial(1, .9), f.blind(3)):
        z, r = hm.hw_stats(lt); out.append(np.mean((z > eta) & (r < thr)))
    print(f"HP shift {k} x{ns}: legit {out[0]:.4f} partial.75 {out[1]:.4f} .9 {out[2]:.4f} blind3x {out[3]:.4f}", flush=True)
