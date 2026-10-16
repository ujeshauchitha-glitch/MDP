"""Re-extract the wideband channel for the OPTIMISED front end (full chain, slow
path + servo-as-fixed-bias included) into results_opt/chan_<I_DC>.txt, for
simulation/detect/coherent_mc.py.

Optimised stage (see docs/afe-architecture.md s17): no booster, plain
common-gate PMOS Mc (W=80), IBX=300n, mirror m=4, 200k source degeneration,
Cc=50p.  Msv gate voltages are the ones bisected for results/chan_*.txt
(they depend only on I_DC, not on the wide path).

usage: TAG=o1_ python make_chan_opt.py IDC VSG
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

idc, vsg = sys.argv[1], sys.argv[2]
o = dict(slow="1", vsg=vsg, idc=idc, vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", cc="50p")
text = w.netlist(o).replace("print v(x) v(xc)", "print v(s_out) v(x) v(xc)")
(w.B / f"{w.TAG}v.spice").write_text(text, encoding="utf-8")
out = subprocess.run([w.NG, "-b", f"{w.TAG}v.spice"], cwd=w.B, capture_output=True, text=True).stdout
m = re.search(r"^v\(s_out\)\s*=\s*([-\d.e+]+)", out, re.M)
rd = lambda f: np.loadtxt(w.B / (w.TAG + f))
h, n = rd("h.txt"), rd("n.txt")
dst = pathlib.Path(__file__).resolve().parent.parent / "results_opt"
dst.mkdir(exist_ok=True)
with open(dst / f"chan_{idc}.txt", "w") as fh:
    fh.write(f"# OPTIMISED front end IDC={idc} Vsg={vsg} s_out={m.group(1) if m else 'n/a'}\n")
    for a, b in zip(h, n):
        fh.write(f"{a[0]:.6e} {a[1]/1e-9:.6e} {a[2]/1e-9:.6e} {b[1]:.6e}\n")
print("IDC", idc, "s_out =", m.group(1) if m else "n/a")
