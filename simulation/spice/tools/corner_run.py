"""PVT check of the optimised front end (common-gate PMOS Mc, real PMOS bias
mirror, 4x degenerated NMOS mirror, slow TIA + NMOS sink with the servo
replaced by a bisected fixed gate voltage).

For one (corner, temperature, I_DC) it
  1. finds the Msv gate voltage that puts s_out at VCM (the job of the servo)
     and reports whether such a lock window exists,
  2. reports bias currents and DC operating points,
  3. measures slow-path gain at 10 Hz and wideband |H|, input-referred noise,
     and the analytic coherent-detection minimum I_DC (m = 2 %).
Rref is NOT re-trimmed per corner (it is a fixed resistor in silicon).

usage: TAG=k1_ python corner_run.py NAME corner temp idc
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

name, corner, temp, idc = sys.argv[1:5]
BASE = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg",
            rref="3.6314Meg", cref="20p", corner=corner, temp=temp, idc=idc, tight="1")


def parse(out, k):
    m = re.search(rf"^v\({k}\)\s*=\s*([-\d.e+]+)", out, re.M)
    return float(m.group(1)) if m else None


def op(vsg):
    o = dict(BASE, vsg=f"{vsg:.6f}", oponly="1")
    (w.B / f"{w.TAG}t.spice").write_text(w.netlist(o), encoding="utf-8")
    out = subprocess.run([w.NG, "-b", f"{w.TAG}t.spice"], cwd=w.B, capture_output=True, text=True).stdout
    return out, parse(out, "s_out")


def lock():
    prev = None
    v = 0.20
    while v < 1.40:
        _, so = op(v)
        if so is not None and prev is not None and prev[1] < 1.65 <= so:
            lo, hi = prev[0], v
            break
        if so is not None:
            prev = (v, so)
        v += 0.04
    else:
        return None
    for _ in range(16):
        mid = (lo + hi) / 2
        _, so = op(mid)
        if so is None:
            return None
        lo, hi = (mid, hi) if so < 1.65 else (lo, mid)
    return (lo + hi) / 2


vsg = lock()
if vsg is None:
    print(f"{name:22s} {corner}/{temp}C IDC={idc}: NO LOCK WINDOW for s_out=1.65 V (slow path cannot be centred)", flush=True)
    sys.exit(0)

out, so = op(vsg)
R = 3e6
ix = (3.3 - parse(out, "sx")) / R * 1e9
iw = (3.3 - parse(out, "sw")) / R * 1e9
o = dict(BASE, vsg=f"{vsg:.6f}")
text = w.netlist(o)
ctl2 = f""".control
  op
  ac dec 40 0.1 20meg
  wrdata {w.TAG}h2.txt v(w_out) v(s_out)
  noise v(w_out) Iph dec 40 1k 20meg
  setplot noise1
  wrdata {w.TAG}n.txt onoise_spectrum
  quit
.endc"""
text = re.sub(r"\.control.*?\.endc", lambda m: ctl2, text, flags=re.S)
(w.B / f"{w.TAG}f.spice").write_text(text, encoding="utf-8")
subprocess.run([w.NG, "-b", f"{w.TAG}f.spice"], cwd=w.B, capture_output=True, text=True)
h = np.loadtxt(w.B / (w.TAG + "h2.txt")); n = np.loadtxt(w.B / (w.TAG + "n.txt"))
f = h[:, 0]
Hw = (h[:, 1] + 1j * h[:, 2]) / 1e-9
Hs = (h[:, 4] + 1j * h[:, 5]) / 1e-9    # wrdata repeats the frequency column per vector
gs10 = abs(Hs[int(np.argmin(np.abs(np.log(f / 10))))])
m = f >= 1e3
fw, Hwm = f[m], Hw[m]
Sn = n[:, 1]
assert len(Sn) == len(fw), (len(Sn), len(fw))
sigma, dn_, need, _ = w.metric(fw, Hwm, Sn, w.tonum(idc))
i = lambda fr: int(np.argmin(np.abs(np.log(fw / fr))))
rti = lambda fr: Sn[i(fr)] / abs(Hwm[i(fr)]) * 1e15
pk = abs(Hwm).max()
hi = next((fw[k] for k in range(int(np.argmax(abs(Hwm))), len(fw)) if abs(Hwm[k]) < pk / 1.4142), float("nan"))
print(f"{name:22s} {corner}/{temp}C IDC={idc}: Vsg={vsg:.4f} s_out={so:.3f} | Ixc/Iw={ix:.0f}/{iw:.0f}nA "
      f"xc={parse(out,'xc'):.2f} dmir={parse(out,'dmir'):.2f} w_in={parse(out,'w_in'):.3f} | slow|Z|10Hz={gs10:.3g} "
      f"| wide |H|100k={abs(Hwm[i(1e5)]):.3g} f-3dB={hi/1e3:.0f}k RTI100k={rti(1e5):.0f}fA | minIDC(m2%)={need:.1f}nA", flush=True)
