"""Chip-rate / code-length trade on the simulated wideband channel.

For each (chip rate, N) it reports the T_int = N/rate, the matched-filter
detection SNR per unit modulation and the I_DC [nA] needed for Pd 99.9 % at
Pfa 1e-8 (m = 2 %), using the analytic figure of merit from
spice/tools/wide_noise_sweep.py on a channel file (default: results_real,
I_DC = 100 nA).  Each config runs in a subprocess because the detector
constants are read from the environment at import.

usage: python chip_rate_sweep.py [chan_file]
"""
import os, sys, subprocess, pathlib

HERE = pathlib.Path(__file__).resolve().parent
CHAN = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parent / "spice" / "results_real" / "chan_100n.txt")

CHILD = r'''
import sys, numpy as np
sys.path.insert(0, r"%s")
import wide_noise_sweep as w, coherent_mc as cm
a = np.loadtxt(r"%s")
f, H, Sn = a[:, 0], a[:, 1] + 1j * a[:, 2], a[:, 3]
sigma, dn, need, dly = w.metric(f, H, Sn, 100e-9)
print("%%.1f %%d %%.1f %%.4f %%.1f %%.2f" %% (cm.RCHIP / 1e3, cm.N, cm.N / cm.RCHIP * 1e6, dn, need, dly / cm.OS))
''' % (str(HERE.parent / "spice" / "tools"), CHAN)

configs = [(240e3, 24), (240e3, 48), (320e3, 32), (320e3, 48), (400e3, 40), (400e3, 48), (480e3, 48),
           (600e3, 60), (720e3, 72), (960e3, 96), (480e3, 96), (480e3, 144)]
print(f"channel: {CHAN}\n  kchip/s    N   T_int[us]  d/(m*nA)  I_DC_min(m=2%)[nA]  rx delay[chips]")
for r, n in configs:
    env = dict(os.environ, RCHIP=str(r), NCHIPS=str(n), TAG="cr_", NGSPICE=os.environ.get("NGSPICE", "x"))
    out = subprocess.run([sys.executable, "-c", CHILD], env=env, capture_output=True, text=True)
    print("  " + (out.stdout.strip() or out.stderr.strip()[-200:]))
