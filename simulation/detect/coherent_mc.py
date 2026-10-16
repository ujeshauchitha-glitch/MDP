"""Coherent-detection Monte Carlo for the TrustSense wideband path.

Pushes random N-chip bipolar codes through the *simulated* option-1 front-end
channel (complex H(f) and output noise PSD from ngspice, see
spice/tools/afe_wide_channel.py) with matching Gaussian noise, and correlates
with the known code.

  chip rate 480 kchip/s, N = 48  ->  T_int = 100 us (one decision per sample)
  perturbation: I_pert(t) = +/- m * I_DC  (peak), bipolar chips
  output noise = SPICE device noise  +  photodiode shot noise 2 q I_DC |H|^2

Noise is Gaussian and stationary by construction; the code checks the
*correlator output* tail against a Gaussian but cannot verify 1e-8 tails
empirically (that would need ~1e9 trials).

usage: python coherent_mc.py [results_dir]
"""
import sys, pathlib, math
import numpy as np
from math import erfc, sqrt

Q_E = 1.602176634e-19
RCHIP = 480e3
N = 48
OS = 16                       # samples per chip
FS = RCHIP * OS
NS = N * OS                   # samples per symbol (100 us)
NSYM = 5                      # 5 consecutive random symbols, middle one scored
L = NSYM * NS
RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "spice" / "results"
PFA, PMD = 1e-8, 1e-3


def Q(x):
    return 0.5 * erfc(x / sqrt(2))


def Qinv(p):
    lo, hi = -10.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if Q(mid) > p else (lo, mid)
    return (lo + hi) / 2


ETA_SIGMAS = Qinv(PFA)                    # 5.61
D_REQ = ETA_SIGMAS + Qinv(PMD)            # 8.70 (18.8 dB)


def load(idc):
    a = np.loadtxt(RES / f"chan_{idc}.txt")
    return a[:, 0], a[:, 1] + 1j * a[:, 2], a[:, 3]


def channel_on_grid(idc):
    f, H, Sn = load(idc)
    fg = np.fft.rfftfreq(L, 1 / FS)
    lf, lfg = np.log(f), np.log(np.maximum(fg, f[0]))
    Hg = np.interp(lfg, lf, H.real) + 1j * np.interp(lfg, lf, H.imag)
    Sg = np.interp(lfg, lf, np.log(Sn)); Sg = np.exp(Sg)
    Hg[fg < f[0]] = 0.0                    # AC-coupled: nothing below 1 kHz
    Hg[fg > f[-1]] = 0.0
    Sg[fg > f[-1]] = Sn[-1]                # (HF beyond sampling band is negligible)
    return fg, Hg, Sg


def make_codes(rng, m):
    return rng.choice([-1.0, 1.0], size=(m, NSYM, N))


def upsample(c):
    return np.repeat(c, OS, axis=-1).reshape(c.shape[0], -1)


def noise_td(rng, S_out, m):
    """Gaussian noise with one-sided output PSD S_out [V^2/Hz] on the rfft grid."""
    k = S_out.shape[0]
    X = np.sqrt(S_out * FS * L / 4.0) * (rng.standard_normal((m, k)) + 1j * rng.standard_normal((m, k)))
    X[:, 0] = 0.0
    X[:, -1] = 0.0
    return np.fft.irfft(X, n=L, axis=1)


def best_delay(Hg):
    rng = np.random.default_rng(1)
    c = make_codes(rng, 200)
    cu = upsample(c)
    y = np.fft.irfft(np.fft.rfft(cu, axis=1) * Hg, n=L, axis=1)
    mid = slice(2 * NS, 3 * NS)
    best, bd = -1, 0
    for d in range(0, 4 * OS):
        z = (y[:, 2 * NS + d: 3 * NS + d] * cu[:, mid]).sum(axis=1).mean()
        if abs(z) > best:
            best, bd = abs(z), d
    return bd


def run(idc_label, idc_amp, ms, trials, rng):
    fg, Hg, Sn = channel_on_grid(idc_label)
    d = best_delay(Hg)
    S_out = Sn ** 2 + 2 * Q_E * idc_amp * np.abs(Hg) ** 2        # SPICE + photodiode shot noise
    rows = []
    # --- noise-only statistics (independent of m) ---
    z0 = []
    for _ in range(trials // 500):
        c = make_codes(rng, 500); cu = upsample(c)
        y = noise_td(rng, S_out, 500)
        z0.append((y[:, 2 * NS + d: 3 * NS + d] * cu[:, 2 * NS: 3 * NS]).sum(axis=1) / NS)
    z0 = np.concatenate(z0)
    s0 = z0.std()
    zz = (z0 - z0.mean()) / s0
    gauss = dict(skew=float(np.mean(zz ** 3)), kurt=float(np.mean(zz ** 4)),
                 f3=float(np.mean(np.abs(zz) > 3)), f4=float(np.mean(np.abs(zz) > 4)))
    # --- signal + noise ---
    for m in ms:
        zs = []
        for _ in range(trials // 500):
            c = make_codes(rng, 500); cu = upsample(c)
            i_t = m * idc_amp * cu
            y = np.fft.irfft(np.fft.rfft(i_t, axis=1) * Hg, n=L, axis=1) + noise_td(rng, S_out, 500)
            zs.append((y[:, 2 * NS + d: 3 * NS + d] * cu[:, 2 * NS: 3 * NS]).sum(axis=1) / NS)
        zs = np.concatenate(zs)
        mu, s1 = zs.mean(), zs.std()
        dd = mu / s0                                   # detection SNR (amplitude)
        eta = ETA_SIGMAS * s0
        pd = Q((eta - mu) / s1)                        # Gaussian-tail Pd at Pfa = 1e-8
        pd_emp = float(np.mean(zs > eta))
        rows.append((m, dd, 20 * math.log10(dd), pd, pd_emp))
    return d, s0, gauss, rows


if __name__ == "__main__":
    rng = np.random.default_rng(2026)
    print(f"N={N} chips @ {RCHIP/1e3:.0f} kchip/s, T_int={N/RCHIP*1e6:.0f} us, Pfa={PFA:g}, eta={ETA_SIGMAS:.2f} sigma")
    print(f"required d = {D_REQ:.2f} ({20*math.log10(D_REQ):.1f} dB) for Pd = {1-PMD:.3f}\n")
    files = sorted(RES.glob("chan_*.txt"), key=lambda p: ({"n": 1e-9, "u": 1e-6}[p.stem.split("_")[1][-1]] * float(p.stem.split("_")[1][:-1])))
    for p in files:
        lab = p.stem.split("_")[1]
        amp = {"n": 1e-9, "u": 1e-6}[lab[-1]] * float(lab[:-1])
        dly, s0, g, rows = run(lab, amp, [0.02, 0.01, 0.005], 20000, rng)
        print(f"I_DC={lab}: rx delay {dly/FS*1e6:.2f} us, sigma0={s0*1e6:.3f} uV, noise-only skew={g['skew']:+.3f} kurt={g['kurt']:.3f} "
              f"P(|z|>3s)={g['f3']:.4f} (Gauss 0.0027) P(|z|>4s)={g['f4']:.5f} (Gauss 6.3e-5)")
        for m, dd, ddb, pd, pe in rows:
            print(f"   m={m*100:4.1f}%  d={dd:6.2f}  SNR={ddb:5.1f} dB  Pd@Pfa1e-8={pd:.4g} (empirical {pe:.4f})")
        print()
