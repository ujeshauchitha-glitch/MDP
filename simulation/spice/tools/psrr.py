"""Supply rejection of the two paths (optimised stage, full chain, tt/27C, VDD 3.3 V, VCM 1.4 V).

Run A: Iph AC = 1 nA, supply AC = 0  -> signal response H(f) [V/A] of each output.
Run B: supply AC = 1 V, Iph AC = 0   -> P(f) [V/V] from VDD to each output.
Equivalent input current per 1 V/rtHz of supply noise: i_eq(f) = |P|/|H| [A per V/rtHz].

Slow-path Z and Msv gate voltage are taken at I_DC = 100 nA, T-network 1 GOhm range.
usage: TAG=ps_ python psrr.py [range: 1G|100M|10M]
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

rng_name = sys.argv[1] if len(sys.argv) > 1 else "1G"
extra = {"1G": dict(tcf="50f"), "100M": dict(rpar="111Meg", tcf="100f"), "10M": dict(rpar="10.1Meg", tcf="500f")}[rng_name]
O = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg",
         cref="20p", idc="100n", tnet="1", t1="10Meg", t3="102k", vcm="1.4", vsg="0.5524", tight="1", **extra)

for kv in sys.argv[2:]:            # variant overrides, e.g. real=0 cref=200p
    k, v = kv.split("=", 1)
    if v == "DEL":
        O.pop(k, None)
    else:
        O[k] = v

def run(tag, vdd_ac, iph_ac):
    text = w.netlist(O)
    text = text.replace("VPWR vdpwr 0 DC 3.3", f"VPWR vdpwr 0 DC 3.3 AC {vdd_ac}")
    text = text.replace("DC {IDC} AC 1n", f"DC {{IDC}} AC {iph_ac}")
    ctl = f""".control
  op
  ac dec 20 0.1 20meg
  wrdata {w.TAG}{tag}.txt v(w_out) v(s_out)
  quit
.endc"""
    text = re.sub(r"\.control.*?\.endc", lambda m: ctl, text, flags=re.S)
    (w.B / f"{w.TAG}{tag}.spice").write_text(text, encoding="utf-8")
    subprocess.run([w.NG, "-b", f"{w.TAG}{tag}.spice"], cwd=w.B, capture_output=True, text=True)
    d = np.loadtxt(w.B / f"{w.TAG}{tag}.txt")
    return d[:, 0], np.abs(d[:, 1] + 1j * d[:, 2]), np.abs(d[:, 4] + 1j * d[:, 5])


f, hw, hs = run("A", 0, "1n")
_, pw, ps = run("B", 1, 0)
hw, hs = hw / 1e-9, hs / 1e-9
near = lambda x: int(np.argmin(np.abs(np.log(f / x))))
print(f"range {rng_name}; slow path (s_out), at 100 nA:")
for fr in (0.5, 1, 10, 100, 1e3):
    i = near(fr)
    print(f"  f={fr:7g} Hz  Z={hs[i]:.3g} V/A  PSRR {20*np.log10(1/ps[i]):6.1f} dB  i_eq = {ps[i]/hs[i]*1e12:.3g} pA per V/rtHz of supply noise")
print("wideband path (w_out):")
for fr in (1e4, 1e5, 3e5, 1e6):
    i = near(fr)
    print(f"  f={fr:7g} Hz  |H|={hw[i]:.3g} V/A  PSRR {20*np.log10(1/pw[i]):6.1f} dB  i_eq = {pw[i]/hw[i]*1e15:.3g} fA per V/rtHz of supply noise")
