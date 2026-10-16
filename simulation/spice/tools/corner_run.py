"""PVT check of the optimised front end (common-gate PMOS Mc, real PMOS bias
mirror, 4x degenerated NMOS mirror, slow TIA + NMOS sink with the servo
replaced by a bisected fixed gate voltage).

For one (corner, temperature, I_DC) it
  1. finds the Msv gate voltage that puts s_out at VCM (the job of the servo)
     and reports whether such a lock window exists (tight solver tolerances),
  2. reports bias currents and DC operating points,
  3. measures the slow path (gain @10 Hz, -3 dB BW, input-referred noise;
     tight tolerances) and the wideband path (|H|, input-referred noise, analytic
     coherent-detection minimum I_DC at m = 2 %; DEFAULT tolerances).
Why two tolerance sets: tight tolerances (abstol 1e-16 A) are needed to resolve
picoamp cancel currents through multi-GOhm feedback, but they intermittently
make the wideband .noise analysis return ~40 % too little noise (same netlist,
default tolerances: stable). Rref is NOT re-trimmed per corner.

usage: TAG=k1_ python corner_run.py NAME corner temp idc [key=val ...]
       extra keys: tnet=1 t1=10Meg t3=102k tcf=50f (poly T-network feedback)
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

name, corner, temp, idc = sys.argv[1:5]
BASE = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg",
            rref="3.6314Meg", cref="20p", corner=corner, temp=temp, idc=idc)
for kv in sys.argv[5:]:
    k, v = kv.split("=", 1)
    BASE[k] = v

T = float(BASE.get("vcm", 1.65))        # servo target = TIA common-mode


def parse(out, k):
    m = re.search(rf"^v\({k}\)\s*=\s*([-\d.e+]+)", out, re.M)
    return float(m.group(1)) if m else None


def op(vsg):
    o = dict(BASE, vsg=f"{vsg:.6f}", oponly="1", tight="1")
    (w.B / f"{w.TAG}t.spice").write_text(w.netlist(o), encoding="utf-8")
    out = subprocess.run([w.NG, "-b", f"{w.TAG}t.spice"], cwd=w.B, capture_output=True, text=True).stdout
    return out, parse(out, "s_out")


def lock():
    prev = None
    v = 0.20
    while v < 1.40:
        _, so = op(v)
        if so is not None and prev is not None and prev[1] < T <= so:
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
        lo, hi = (mid, hi) if so < T else (lo, mid)
    return (lo + hi) / 2


def analyze(vsg, tight, tag):
    """AC + wideband noise + slow noise; returns arrays."""
    o = dict(BASE, vsg=f"{vsg:.6f}", tight=tight)
    text = w.netlist(o)
    ctl = f""".control
  op
  ac dec 40 0.1 20meg
  wrdata {w.TAG}{tag}h.txt v(w_out) v(s_out)
  noise v(w_out) Iph dec 40 1k 20meg
  setplot noise1
  wrdata {w.TAG}{tag}n.txt onoise_spectrum
  noise v(s_out) Iph dec 10 0.1 100k
  setplot noise3
  wrdata {w.TAG}{tag}ns.txt onoise_spectrum
  quit
.endc"""
    text = re.sub(r"\.control.*?\.endc", lambda m: ctl, text, flags=re.S)
    (w.B / f"{w.TAG}{tag}f.spice").write_text(text, encoding="utf-8")
    subprocess.run([w.NG, "-b", f"{w.TAG}{tag}f.spice"], cwd=w.B, capture_output=True, text=True)
    h = np.loadtxt(w.B / f"{w.TAG}{tag}h.txt")
    return h, np.loadtxt(w.B / f"{w.TAG}{tag}n.txt"), np.loadtxt(w.B / f"{w.TAG}{tag}ns.txt")


vsg = lock()
if vsg is None:
    print(f"{name:22s} {corner}/{temp}C IDC={idc}: NO LOCK WINDOW for s_out=VCM (slow path cannot be centred)", flush=True)
    sys.exit(0)

out, so = op(vsg)
R = 3e6
VDD = float(BASE.get("vdd", 3.3))
ix = (VDD - parse(out, "sx")) / R * 1e9
iw = (VDD - parse(out, "sw")) / R * 1e9

# --- slow path: tight tolerances ---
h1, _, ns = analyze(vsg, "1", "s")
f = h1[:, 0]
Hs = (h1[:, 4] + 1j * h1[:, 5]) / 1e-9      # wrdata repeats the frequency column per vector
gs10 = abs(Hs[int(np.argmin(np.abs(np.log(f / 10))))])
gsm = np.abs(Hs)
bw_s = next((f[k] for k in range(len(f)) if f[k] > 10 and gsm[k] < gs10 / 1.4142), float("nan"))
fn, dens = ns[:, 0], ns[:, 1] / np.interp(np.log(ns[:, 0]), np.log(f), gsm)
sel = (fn >= 0.5) & (fn <= 100)
rms_s = float(np.sqrt(np.trapezoid(dens[sel] ** 2, fn[sel]))) * 1e12
d10 = dens[int(np.argmin(np.abs(np.log(fn / 10))))] * 1e15

if os.environ.get("DUMP"):   # plant + noise data for the digital-servo co-simulation
    dd = pathlib.Path(os.environ["DUMP"]); dd.mkdir(parents=True, exist_ok=True)
    np.savetxt(dd / f"slow_psd_{idc}.txt", np.c_[fn, dens], header="f[Hz] input-referred slow-path noise [A/rtHz]")
    np.savetxt(dd / f"slow_plant_{idc}.txt", np.c_[f, np.abs(Hs), np.unwrap(np.angle(Hs))], header="f[Hz] |Z|[V/A] phase[rad] (Iph->s_out)")

# --- wideband path: default tolerances ---
h0, n0, _ = analyze(vsg, "0", "w")
fw_all = h0[:, 0]
Hw = (h0[:, 1] + 1j * h0[:, 2]) / 1e-9
m = fw_all >= 1e3
fw, Hwm, Sn = fw_all[m], Hw[m], n0[:, 1]
assert len(Sn) == len(fw), (len(Sn), len(fw))
sigma, dn_, need, _ = w.metric(fw, Hwm, Sn, w.tonum(idc))
i = lambda fr: int(np.argmin(np.abs(np.log(fw / fr))))
rti = lambda fr: Sn[i(fr)] / abs(Hwm[i(fr)]) * 1e15

print(f"{name:22s} {corner}/{temp}C IDC={idc}: Vsg={vsg:.4f} s_out={so:.3f} | slow Z10Hz={gs10:.3g} BW={bw_s:.3g}Hz "
      f"noise@10Hz={d10:.0f}fA RMS0.5-100Hz={rms_s:.1f}pA | Ixc/Iw={ix:.0f}/{iw:.0f}nA xc={parse(out,'xc'):.2f} "
      f"w_in={parse(out,'w_in'):.3f} | wide |H|100k={abs(Hwm[i(1e5)]):.3g} RTI100k={rti(1e5):.0f}fA "
      f"minIDC(m2%)={need:.1f}nA", flush=True)
