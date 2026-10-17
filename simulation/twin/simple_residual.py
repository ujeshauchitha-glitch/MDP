"""Can the residual test be done cheaply in hardware?  D1' uses the code itself (not the channel-filtered code) as template,
4 samples/chip, 8-bit-equivalent quantisation (LSB 100 uV).  Compare with the full D1 of the twin."""
import numpy as np, trustsense_twin as t
from trustsense_twin import cm, NS, N

f = t.FastPath(100e-9, seed=21)
STEP, LSB = 4, 100e-6                      # 4 samples per chip
def stats(light, trials=6000):
    Z, R1, R2 = [], [], []
    for _ in range(trials // 500):
        codes = f.random_codes(500); cu = cm.upsample(codes)
        z, r = f.frames(codes, light)      # full D1 numbers (own noise draw)
        # same trial re-run to get y for the cheap test
        sig = f.channel(light(codes)) if light else 0.0
        y = (sig + cm.noise_td(f.rng, f.S_out, 500))[:, f.win][:, ::STEP]
        y = np.round(y / LSB) * LSB
        c = cu[:, f.mid][:, ::STEP]
        zc = (y * c).sum(axis=1)                       # correlator
        r_cheap = (y * y).sum(axis=1) - zc ** 2 / c.shape[1]    # energy left after removing the best-fit code amplitude
        Z.append(zc); R1.append(r); R2.append(r_cheap)
    return np.concatenate(Z), np.concatenate(R1), np.concatenate(R2)

zn, _, _ = stats(None); s0 = zn.std(); eta = cm.ETA_SIGMAS * s0
zl, rl, rcl = stats(f.legit())
thr_full, thr_cheap = np.quantile(rl, 0.999), np.quantile(rcl, 0.999)
print(f"legit: correlator-only Pd {np.mean(zl>eta):.4f}; full D1 Pd {np.mean((zl>eta)&(rl<thr_full)):.4f}; cheap D1' Pd {np.mean((zl>eta)&(rcl<thr_cheap)):.4f}")
cases = [("blind 1x", f.blind(1)), ("blind 3x", f.blind(3)), ("blind 30x", f.blind(30)), ("partial f=0.75", f.partial(1, .75)), ("partial f=0.9", f.partial(1, .9)),
         ("relay 130ns", f.relay(1, 130e-9)), ("relay 260ns", f.relay(1, 260e-9))]
print(f"{'attack':16s} corr-only  full D1   cheap D1'")
for name, lt in cases:
    z, r, rc = stats(lt)
    print(f"{name:16s} {np.mean(z>eta):9.4f} {np.mean((z>eta)&(r<thr_full)):9.4f} {np.mean((z>eta)&(rc<thr_cheap)):9.4f}")
