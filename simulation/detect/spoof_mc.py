"""Spoofing attack Monte Carlo against the wideband coherent detector.

Threat: an attacker injects light into the photodiode (same current->voltage
channel as the legitimate perturbation, including the front-end response and
noise) with the legitimate LED path absent, trying to make the detector accept.
The attacker knows the chip clock/timing. Attack modes:
  blind     : random +/-1 chips (never saw the code), amplitude A x legit I_pert
  partial f : fraction f of the chips correct, rest random
Detectors:
  D0  correlation threshold only (eta = 5.61 sigma, Pfa 1e-8 for AWGN)
  D1  D0 AND a residual (goodness-of-fit) test: after removing the LS-fitted
      amount of the *known* template (the front-end response to the true code,
      incl. ISI from neighbouring symbols), the leftover energy must be consistent
      with noise. Threshold = 99.9 % quantile of the legitimate distribution.

I_DC = 100 nA channel from results_real (real bias mirror), legit m = 2 %, 48 chips,
480 kchip/s. Acceptance counts of 0 mean "< 1/trials", NOT zero probability.
usage: python spoof_mc.py [trials]
"""
import sys, pathlib, math
import numpy as np
import coherent_mc as cm

RES = pathlib.Path(__file__).resolve().parent.parent / "spice" / "results_real"
IDC = 100e-9
M_LEG = 0.02
TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
BATCH = 500
rng = np.random.default_rng(11)

fg, Hg, Sg = cm.channel_on_grid("100n") if False else (None, None, None)
cm.RES = RES
fg, Hg, Sg = cm.channel_on_grid("100n")
S_out = Sg ** 2 + 2 * cm.Q_E * IDC * np.abs(Hg) ** 2
D = cm.best_delay(Hg)
MID = slice(2 * cm.NS, 3 * cm.NS)
WIN = slice(2 * cm.NS + D, 3 * cm.NS + D)


def channel(x):
    return np.fft.irfft(np.fft.rfft(x, axis=1) * Hg, n=cm.L, axis=1)


def trial_batch(m, att, A, f=0.0, legit=False, tau=0.0):
    """Return (corr z, residual energy) for a batch. att: 'blind'|'partial'|None."""
    c = cm.make_codes(rng, m); cu = cm.upsample(c)
    tmpl = channel(cu)[:, WIN]                          # unit-amplitude noiseless response to the TRUE code (known to the receiver)
    if legit:
        sig = channel(M_LEG * IDC * cu)
    else:
        a = cm.make_codes(rng, m)                       # attacker chips (all random by default)
        if att == "partial":
            keep = rng.random((m, cm.NSYM, cm.N)) < f
            a = np.where(keep, c, a)
        if att == "relay":                              # attacker observes each chip perfectly, re-emits it tau seconds late
            fr = np.fft.rfftfreq(cm.L, 1 / cm.FS)
            ph = np.exp(-2j * np.pi * fr * tau)
            sig = np.fft.irfft(np.fft.rfft(A * M_LEG * IDC * cu, axis=1) * Hg * ph, n=cm.L, axis=1)
        else:
            sig = channel(A * M_LEG * IDC * cm.upsample(a))
    y = (sig + cm.noise_td(rng, S_out, m))[:, WIN]
    z = (y * cu[:, MID]).sum(axis=1) / cm.NS
    mu = (y * tmpl).sum(axis=1) / (tmpl * tmpl).sum(axis=1)
    resid = ((y - mu[:, None] * tmpl) ** 2).sum(axis=1) / cm.NS
    return z, resid


def collect(**kw):   # kw passes through to trial_batch
    zs, rs = [], []
    for _ in range(TRIALS // BATCH):
        z, r = trial_batch(BATCH, **kw)
        zs.append(z); rs.append(r)
    return np.concatenate(zs), np.concatenate(rs)


if __name__ == "__main__":
    # --- calibrate on noise-only and on legit ---
    z0, r0 = collect(att=None, A=0, legit=False) if False else (None, None)
    zn = []; rn = []
    for _ in range(TRIALS // BATCH):               # noise only: attacker amplitude zero
        z, r = trial_batch(BATCH, att="blind", A=0.0)
        zn.append(z); rn.append(r)
    zn, rn = np.concatenate(zn), np.concatenate(rn)
    s0 = zn.std()
    eta = cm.ETA_SIGMAS * s0
    zl, rl = collect(att=None, A=0, legit=True)
    r_thr = np.quantile(rl, 0.999)
    print(f"trials/point {TRIALS}; sigma0 = {s0*1e6:.2f} uV, eta = {eta*1e6:.1f} uV, legit mean z/sigma = {zl.mean()/s0:.2f}")
    print(f"residual energy [V^2]: legit mean {rl.mean():.3e}, 99.9% quantile {r_thr:.3e} (threshold); noise-only mean {rn.mean():.3e}")
    d0 = np.mean(zl > eta); d1 = np.mean((zl > eta) & (rl < r_thr))
    print(f"LEGITIMATE detection: D0 Pd = {d0:.4f}, D1 Pd = {d1:.4f}  (D1 loss {100*(d0-d1):.2f} %-points)\n")
    print("attack                     D0 accepts   D1 accepts   median residual / threshold")
    cases = [("blind", A, 0.0) for A in (0.0, 1, 3, 10, 30, 100, 300)]
    cases += [("partial", 1.0, f) for f in (0.5, 0.75, 0.9, 0.95)]
    cases += [("partial", 10.0, f) for f in (0.75, 0.9, 0.95)]
    for att, A, f in cases:
        z, r = collect(att=att, A=A, f=f)
        a0 = np.mean(z > eta); a1 = np.mean((z > eta) & (r < r_thr))
        tag = f"blind A={A:g}x" if att == "blind" else f"partial f={f:g} A={A:g}x"
        print(f"{tag:26s} {a0:9.4f}   {a1:9.4f}      {np.median(r)/r_thr:8.2f}")
    print()
    print("real-time relay attacker (perfect chip observation, re-emits each chip tau late, same amplitude as legit):")
    for tau in (20e-9, 50e-9, 130e-9, 260e-9, 520e-9, 1040e-9):
        z, r = collect(att="relay", A=1.0, tau=tau)
        a0 = np.mean(z > eta); a1 = np.mean((z > eta) & (r < r_thr))
        print(f"  tau = {tau*1e9:6.0f} ns ({tau*cm.RCHIP*100:5.1f} % of a chip): mean z/sigma {z.mean()/s0:5.1f}  D0 accepts {a0:.4f}  D1 accepts {a1:.4f}  median resid/thr {np.median(r)/r_thr:6.2f}")
