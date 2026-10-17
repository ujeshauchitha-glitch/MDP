"""Worst-case mismatch sensitivity of the wideband stage (optimised, real bias mirror).

The sky130 5 V device models carry no usable random mismatch (vth0_slope = 0), so a
model-based Monte Carlo is not possible. Instead gate-referred threshold offsets of
about +/-3 sigma (Pelgrom, assumed A_VT ~ 5-10 mV*um) are injected one block at a
time and the effect on bias currents, DC levels and detection reach is measured.

usage: TAG=ms_ python mismatch_sens.py NAME key=val ...   keys: vmm vbw vbx vosw (volts)
"""
import re, sys, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

name = sys.argv[1]
o = dict(slow="0", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg",
         cref="20p", idc="100n", vcm="1.4")
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1); o[k] = v
f, H, Sn, pw, out = w.fom(o)
g = lambda k: float(re.search(rf"^v\({k}\)\s*=\s*([-\d.e+]+)", out, re.M).group(1))
R = 3e6
ix, iw = (3.3 - g("sx")) / R * 1e9, (3.3 - g("sw")) / R * 1e9
sigma, dn_, need, _ = w.metric(f, H, Sn, 100e-9)
i = int(np.argmin(np.abs(np.log(f / 1e5))))
print(f"{name:20s} Ixc={ix:5.0f}nA Iw={iw:5.0f}nA  w_in={g('w_in'):.4f} V  w_out-VCM={(g('w_out')-1.4)*1e3:+7.1f} mV  "
      f"|H|100k={abs(H[i]):.3g}  RTI100k={Sn[i]/abs(H[i])*1e15:.0f} fA  minIDC(m2%)={need:.1f} nA", flush=True)
