"""Real PMOS bias mirror (replaces ideal Ibx / Icompw) in the optimised
wideband stage: trim Rref to hit IBX_target, then report the coherent-detection
figure of merit (see wide_noise_sweep.py).

usage: TAG=r1_ python real_bias_sweep.py NAME key=val ...   (keys: rs cref pw pl ibx_t(nA) slow vsg idc)
"""
import os, re, sys, subprocess, pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

BASE = dict(slow="0", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1")


def fmt(r):
    return f"{r/1e6:.4f}Meg"


def unit(x):
    return float(x.replace("Meg", "e6").replace("k", "e3").replace("n", "e-9").replace("p", "e-12"))


def op_current(o, rref):
    oo = dict(o, rref=fmt(rref), oponly="1")
    (w.B / f"{w.TAG}t.spice").write_text(w.netlist(oo), encoding="utf-8")
    out = subprocess.run([w.NG, "-b", f"{w.TAG}t.spice"], cwd=w.B, capture_output=True, text=True).stdout
    g = lambda k: float(re.search(rf"^v\({k}\)\s*=\s*([-\d.e+]+)", out, re.M).group(1))
    rs = unit(o.get("rs", "1Meg"))
    return (3.3 - g("sx")) / rs, (3.3 - g("sw")) / rs, g("w_in"), g("xc")


def trim(o, target):
    # I falls ~ with Rref; secant on log scale starting at a guess
    r0, r1 = 5.0e6, 7.5e6
    i0, i1 = op_current(o, r0)[0], op_current(o, r1)[0]
    for _ in range(6):
        r2 = r1 + (target - i1) * (r1 - r0) / (i1 - i0)
        r0, i0 = r1, i1
        r1, i1 = r2, op_current(o, r2)[0]
        if abs(i1 - target) < 0.01 * target:
            break
    return r1


if __name__ == "__main__":
    name = sys.argv[1]
    o = dict(BASE)
    for kv in sys.argv[2:]:
        k, v = kv.split("=", 1); o[k] = v
    target = unit(o.pop("ibx_t", "300n"))
    rref = trim(o, target)
    ix, iw, win, xc = op_current(o, rref)
    o["rref"] = fmt(rref)
    f, H, Sn, pw, _ = w.fom(o)
    idc_a = w.tonum(o.get("idc", "100n"))
    sigma, dn_, need, dly = w.metric(f, H, Sn, idc_a)
    i = lambda fr: int(np.argmin(np.abs(np.log(f / fr))))
    rti = lambda fr: Sn[i(fr)] / abs(H[i(fr)]) * 1e15
    print(f"{name:26s} Rref={fmt(rref)} Ixc/Iw={ix*1e9:.0f}/{iw*1e9:.0f}nA w_in={win:.4f} sigma0={sigma*1e6:5.2f}uV "
          f"minIDC(m2%)={need:5.1f}nA RTI@30k/100k/316k={rti(3e4):.0f}/{rti(1e5):.0f}/{rti(3.16e5):.0f}fA |H|100k={abs(H[i(1e5)]):.3g} P={pw*1e6:.0f}uW", flush=True)
