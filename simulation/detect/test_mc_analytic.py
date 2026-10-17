"""Independent check of coherent_mc.py: flat channel + white noise has a closed-form answer.
For a flat H (V/A) and one-sided input-referred noise density S_in [A^2/Hz], the rect-chip correlator over
T_int gives  d = mu/sigma0 = (A/sqrt(S_in)) * sqrt(2*T_int),  A = m*I_DC (peak).
(Also the noise-only correlator must be Gaussian.)"""
import math, numpy as np
import coherent_mc as cm

H0 = 1e5                                  # V/A, flat
IDC = 100e-9; M = 0.02
S_chan = (500e-15 * H0) ** 2              # SPICE-style channel noise: 500 fA/rtHz input-referred, as V^2/Hz
S_in_total = (500e-15) ** 2 + 2 * cm.Q_E * IDC   # adds the photodiode shot noise that run() injects
fg = np.fft.rfftfreq(cm.L, 1 / cm.FS)
cm.channel_on_grid = lambda lab: (fg, np.full(len(fg), H0 + 0j), np.full(len(fg), math.sqrt(S_chan)))
rng = np.random.default_rng(5)
d, s0, g, rows = cm.run("flat", IDC, [M], 20000, rng)
T_int = cm.N / cm.RCHIP
expect = (M * IDC / math.sqrt(S_in_total)) * math.sqrt(2 * T_int)
print(f"MC d = {rows[0][1]:.3f}   analytic d = {expect:.3f}   ratio {rows[0][1]/expect:.4f}   (rx delay {d} samples)")
print(f"sigma0 MC = {s0*1e6:.3f} uV; analytic = {H0*math.sqrt(S_in_total/(2*T_int))*1e6:.3f} uV")
print(f"noise-only kurtosis {g['kurt']:.3f} (3.0 = Gaussian), P(|z|>3s) {g['f3']:.4f}")
