"""Transient check of the gate-voltage DAC + first-order sigma-delta driving the degenerated cancel device:
ripple at the slow TIA output for DAC LSB sizes and DAC output resistance / gate capacitance.
usage: TAG=ds_ python dac_sd_tran.py"""
import os, re, subprocess, sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w

BASE = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg", cref="20p", corner="tt",
            temp="27", idc="100n", tnet="1", t1="10Meg", t3="102k", tcf="50f", vcm="1.4", mcbulk="vcm", inbulk="src", iref="300n", sdeg="3Meg", vsg="0.981148")

def run(lsb_mv, rdac, cg, duty=0.5, tstop=8e-3):
    o = dict(BASE, gdrv=rdac, gcap=cg)
    s = w.netlist(o)
    v0 = float(BASE["vsg"]) - duty * lsb_mv * 1e-3
    per = 10e-6
    pulse = f"Vsv  vdac_o vgnd PULSE({v0:.6f} {v0+lsb_mv*1e-3:.6f} 0 10n 10n {duty*per-10e-9:.9f} {per})"
    s = re.sub(r"^Vsv  vdac_o vgnd DC \S+$", pulse, s, flags=re.M)
    s = re.sub(r"\.control.*?\.endc", f".control\n  tran 100n {tstop} 0 200n\n  wrdata {w.TAG}tr.txt v(s_out) v(vc_s)\n  quit\n.endc", s, flags=re.S)
    (w.B / f"{w.TAG}tr.spice").write_text(s, encoding="utf-8")
    subprocess.run([w.NG, "-b", f"{w.TAG}tr.spice"], cwd=w.B, capture_output=True, text=True)
    d = np.loadtxt(w.B / f"{w.TAG}tr.txt")
    t, so, vg = d[:, 0], d[:, 1], d[:, 3]
    m = t > 0.6 * tstop
    return so[m].mean(), np.ptp(so[m]), np.ptp(vg[m])

if __name__ == "__main__":
    print("DAC LSB   R_dac   C_gate | mean s_out   ripple pk-pk at s_out   ripple pk-pk at gate")
    for lsb, rd, cg in ((2.35, "100k", "5p"), (2.35, "1Meg", "5p"), (0.147, "100k", "5p"), (0.147, "1Meg", "5p"), (0.147, "1Meg", "1p"), (0.0367, "1Meg", "1p")):
        mean, rip, rg = run(lsb, rd, cg)
        print(f"{lsb:6.3f} mV {rd:>5s} {cg:>5s} | {mean:.4f} V   {rip*1e3:8.3f} mV    {rg*1e6:8.1f} uV", flush=True)
