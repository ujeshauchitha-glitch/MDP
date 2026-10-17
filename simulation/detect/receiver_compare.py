"""Optimal (matched + whitened) receiver bound versus the rectangular-chip correlator on a simulated channel.

d_opt^2 = 4 * int_0^{fs/2} |X(f)|^2 / S(f) df   (= 2E/N0 for a real signal)  with X = FT of the noise-free output for ONE symbol of unit modulation,
S = output noise PSD (SPICE noise + photodiode shot noise). Neighbouring symbols are assumed known and subtracted.
Reported as the minimum I_DC for Pd 99.9 % at Pfa 1e-8 (d = 8.70), m = 2 %, next to the rectangular correlator
(same analytic figure of merit as spice/tools/wide_noise_sweep.py).
usage: python receiver_compare.py [results_dir] [idc_label]
"""
import sys, pathlib, math
import numpy as np
import coherent_mc as cm

RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "spice" / "results_final"
LAB = sys.argv[2] if len(sys.argv) > 2 else "100n"
IDC = {"n": 1e-9, "u": 1e-6}[LAB[-1]] * float(LAB[:-1])
cm.RES = RES
fg, Hg, Sg = cm.channel_on_grid(LAB)
S_out = Sg ** 2 + 2 * cm.Q_E * IDC * np.abs(Hg) ** 2
rng = np.random.default_rng(3)
# one isolated symbol in the middle of the record, unit modulation m = 1 (A = I_DC)
c = cm.make_codes(rng, 300)
mid = np.zeros_like(c); mid[:, 2, :] = c[:, 2, :]
x = np.fft.irfft(np.fft.rfft(cm.upsample(mid) * IDC, axis=1) * Hg, n=cm.L, axis=1)
X = np.fft.rfft(x, axis=1)
w = np.ones(len(fg)); w[0] = 0
d2 = 4 * np.sum((np.abs(X) ** 2) / (S_out * cm.FS * cm.L) * w, axis=1)         # per code (2E/N0)
d_opt = float(np.sqrt(d2).mean())                                                # amplitude SNR for m = 1
# rectangular correlator with the best delay (analytic sigma0, noise-free mean)
D = cm.best_delay(Hg)
cu = cm.upsample(c)
y = np.fft.irfft(np.fft.rfft(cu * IDC, axis=1) * Hg, n=cm.L, axis=1)
z = (y[:, 2 * cm.NS + D: 3 * cm.NS + D] * cu[:, 2 * cm.NS: 3 * cm.NS]).sum(axis=1) / cm.NS
ff = fg[fg <= cm.FS / 2]
Dk = np.sin(np.pi * ff * cm.OS / cm.FS) ** 2 / np.maximum(np.sin(np.pi * ff / cm.FS) ** 2, 1e-30)
Dk[0] = cm.OS ** 2
sigma = math.sqrt((cm.N / cm.NS ** 2) * np.trapezoid(S_out[:len(ff)] * Dk, ff))
d_rect = abs(float(z.mean())) / sigma
print(f"channel {RES.name}/chan_{LAB}, I_DC={IDC*1e9:.0f} nA, N={cm.N} chips @ {cm.RCHIP/1e3:.0f} kchip/s")
print(f"  rectangular correlator : d(m=1) = {d_rect:7.2f}  -> min I_DC (m=2%) = {cm.D_REQ*IDC*1e9/(0.02*d_rect):6.1f} nA")
print(f"  optimal matched+whitened: d(m=1) = {d_opt:7.2f}  -> min I_DC (m=2%) = {cm.D_REQ*IDC*1e9/(0.02*d_opt):6.1f} nA   ({20*math.log10(d_opt/d_rect):+.1f} dB)")
