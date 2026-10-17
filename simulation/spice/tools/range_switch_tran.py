"""Range-switch transient with a REAL NMOS switch (thick oxide) in series with the lower-gain
range resistor Rpar of the slow TIA (final front end, tt/27C, VCM 1.4 V, I_DC = 100 nA, Msv gate fixed).
A step on the switch gate at T0 turns the range ON (1 GOhm -> 100 MOhm style) or OFF.
Measures: switch Ron, off-state leakage effect, output glitch (peak deviation of s_out) and recovery.

usage: TAG=sw_ python range_switch_tran.py NAME RPAR WSW LSW DIR [temp]
   DIR = on  (range resistor switched in) | off (switched out)
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

name, rpar, wsw, lsw, direction = sys.argv[1:6]
temp = sys.argv[6] if len(sys.argv) > 6 else "27"
VSG = sys.argv[7] if len(sys.argv) > 7 else "0.552389"
CORNER = sys.argv[8] if len(sys.argv) > 8 else "tt"
T0 = 1e-3
O = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg", cref="20p",
         idc="100n", tnet="1", t1="10Meg", t3="102k", tcf="100f", vcm="1.4", vsg=VSG, iref="300n", mcbulk="vcm",
         inbulk="src", ibias="2u,4u", rpar=rpar, temp=temp, corner=CORNER)
text = w.netlist(O)
# series switch between Rpar and s_out
text = text.replace("Rp_s   x s_out " + rpar, "Rp_s   x nr_s " + rpar + "\nXMsw_s nr_s gsw_s s_out vgnd sky130_fd_pr__nfet_g5v0d10v5 W=" + wsw + " L=" + lsw)
lo, hi = ("0", "3.3") if direction == "on" else ("3.3", "0")
text = text.replace(".param IDC", f"Vsw gsw_s 0 PWL(0 {lo} {T0} {lo} {T0+10e-9} {hi})\n.param IDC", 1)
ctl = f""".control
  tran 0.5u 4m 0 0.5u
  wrdata {w.TAG}sw.txt v(s_out) v(x) v(nr_s)
  quit
.endc"""
text = re.sub(r"\.control.*?\.endc", lambda m: ctl, text, flags=re.S)
(w.B / f"{w.TAG}sw.spice").write_text(text, encoding="utf-8")
subprocess.run([w.NG, "-b", f"{w.TAG}sw.spice"], cwd=w.B, capture_output=True, text=True)
d = np.loadtxt(w.B / f"{w.TAG}sw.txt")
t, vs, vx = d[:, 0], d[:, 1], d[:, 3]
pre = vs[(t > 0.8e-3) & (t < 0.99e-3)].mean()
post_t = t > T0
dev = vs[post_t] - pre
k = int(np.argmax(np.abs(dev)))
fin = vs[t > 3.5e-3].mean() - pre
tol = 0.02
bad = np.where((np.abs(vs - vs[t > 3.5e-3].mean()) > tol) & post_t)[0]
tset = (t[bad[-1]] - T0) * 1e6 if len(bad) else 0.0
print(f"{name:22s} Rpar={rpar} switch W/L={wsw}/{lsw} dir={direction} {temp}C: pre-switch s_out={pre:.4f} V, "
      f"peak glitch {dev[k]*1e3:+.0f} mV at +{(t[post_t][k]-T0)*1e6:.0f} us, final shift {fin*1e3:+.1f} mV, "
      f"settles to within 20 mV of final after {tset:.0f} us; x excursion {np.abs(vx[post_t]-vx[(t>0.8e-3)&(t<0.99e-3)].mean()).max()*1e3:.1f} mV", flush=True)
