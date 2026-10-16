"""Cross-check: drive the transistor-level slow TIA (afe_direct.spice, T-network, tt/27C,
VCM 1.4 V) with the Python servo's DAC current waveform (ideal sink at x, incl. the
sigma-delta toggling) and the same photocurrent, and compare s_out with the Python plant.
usage: TAG=sc_ python spice_check.py"""
import os, re, sys, subprocess, pathlib, math
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "spice" / "tools"))
import wide_noise_sweep as w
import servo_loop as sl

IDC, AMP, FPPG = 100e-9, 150e-12, 1.2
T0, T1 = 1.5, 1.8                          # SPICE window (python run settles first)
r = sl.simulate("100n", T1, IDC, ppg=(AMP, FPPG), noise=False, gain_sched=False)
t, out, idac = r["t"], r["out"], r["idac"]
m = t >= T0
tw, iw = t[m] - T0, idac[m]
# decimate PWL: keep points where the DAC value changes
chg = np.r_[True, np.diff(iw) != 0]
# PWL interpolates linearly: hold the old value until 1 ns before each change to keep the steps square
idx = np.where(chg)[0]
pts = [(tw[0], iw[0])]
for k in idx[1:]:
    pts.append((tw[k] - 1e-9, iw[k - 1])); pts.append((tw[k], iw[k]))
pts.append((tw[-1], iw[-1]))
pw = " ".join(f"{a:.9e} {b:.6e}" for a, b in pts)
print("DAC PWL points:", len(pts))
o = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg",
         cref="20p", idc="100n", tnet="1", t1="10Meg", t3="102k", tcf="50f", vcm="1.4", vsg="0.55", tight="1")
text = w.netlist(o)
text = re.sub(r"^XMsv[^\n]*\n", "", text, flags=re.M)
text = re.sub(r"^Vsv[^\n]*\n", "", text, flags=re.M)
text = text.replace("Iph  anode_int x  DC {IDC} AC 1n",
                    f"Iph  anode_int x  DC {{IDC}} AC 1n SIN({IDC} {AMP} {FPPG} 0 0 {360*FPPG*T0})")
text = text.replace("Cj   x anode_int  10p", f"Idac  x 0 PWL({pw})\nCj   x anode_int  10p")
ctl = f""".control
  tran 10u {T1-T0} 0 10u
  wrdata {w.TAG}tr.txt v(s_out)
  quit
.endc"""
text = re.sub(r"\.control.*?\.endc", lambda mm: ctl, text, flags=re.S)
(w.B / f"{w.TAG}chk.spice").write_text(text, encoding="utf-8")
subprocess.run([w.NG, "-b", f"{w.TAG}chk.spice"], cwd=w.B, capture_output=True, text=True)
d = np.loadtxt(w.B / f"{w.TAG}tr.txt")
ts, vs = d[:, 0], d[:, 1]
vp = np.interp(ts + T0, t, out)
sel = ts > 0.05                            # skip SPICE initial transient
a = vs[sel] - vs[sel].mean(); b = vp[sel] - vp[sel].mean()
print(f"SPICE s_out pk-pk {np.ptp(a)*1e3:.1f} mV, Python plant pk-pk {np.ptp(b)*1e3:.1f} mV, "
      f"rms difference {np.sqrt(np.mean((a-b)**2))*1e3:.2f} mV ({np.sqrt(np.mean((a-b)**2))/ (AMP*1e9*1e3/ math.sqrt(2)) *100:.1f} % of PPG rms), "
      f"mean offset spice {vs[sel].mean()-sl.VCM:+.4f} V python {vp[sel].mean()-sl.VCM:+.4f} V")
