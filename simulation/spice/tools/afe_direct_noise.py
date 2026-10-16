"""Option-1 front end (afe_direct.spice): AC gains of both paths (node
contention check) and input-referred noise of both paths.

The behavioral servo is replaced by a fixed Msv gate voltage bisected so that
s_out = VCM (the .op of the closed servo latches in a wrong state).

env: TAG (file prefix, for parallel runs)
usage: python afe_direct_noise.py IDC IBX CC [CC ...]
"""
import re, subprocess, os, sys, math, pathlib

D = pathlib.Path(__file__).resolve().parent.parent
B = D / "build"
NG = os.environ["NGSPICE"]
TAG = os.environ.get("TAG", "d0")
base = (D / "afe_direct.spice").read_text(encoding="utf-8")


def make(idc, ibx, cc, vsg, ctl):
    s = base.replace(".param IDC=100n", f".param IDC={idc}")
    s = s.replace(".param IBX=1u", f".param IBX={ibx}").replace(".param CC=50p", f".param CC={cc}")
    s = s.replace(".option gmin=1e-17", ".option gmin=1e-14")  # servo removed: gmin no longer starves it; avoids singular xc at HF
    s = re.sub(r"\* coarse acquisition[^\n]*\nBint[^\n]*\n", "", s)
    s = re.sub(r"Cint[^\n]*\n", f"Vsv  vc_s vgnd DC {vsg}\n", s)
    return re.sub(r"\.control.*?\.endc", lambda m: ctl, s, flags=re.S)


def sh(name, text):
    (B / (TAG + name)).write_text(text, encoding="utf-8")
    return subprocess.run([NG, "-b", TAG + name], cwd=B, capture_output=True, text=True).stdout


def s_out(idc, ibx, cc, vsg):
    out = sh("o.spice", make(idc, ibx, cc, vsg, ".control\n op\n print v(s_out)\n quit\n.endc"))
    m = re.search(r"v\(s_out\)\s*=\s*([-\d.e+]+)", out)
    return float(m.group(1)) if m else None


def bisect(idc, ibx, cc):
    v, prev, lo, hi = 0.30, None, None, None
    while v < 1.40:
        so = s_out(idc, ibx, cc, v)
        if so is not None and so > 1.65 and prev is not None and prev[1] < 1.65:
            lo, hi = prev[0], v
            break
        if so is not None:
            prev = (v, so)
        v += 0.01
    if lo is None:
        return None
    for _ in range(20):
        mid = (lo + hi) / 2
        so = s_out(idc, ibx, cc, mid)
        if so is None:
            return None
        lo, hi = (mid, hi) if so < 1.65 else (lo, mid)
    return (lo + hi) / 2


def rd(f):
    return [tuple(map(float, l.split())) for l in (B / (TAG + f)).read_text().splitlines() if l.strip()]


def run(idc, ibx, cc):
    vsg = bisect(idc, ibx, cc)
    if vsg is None:
        return None
    ctl = f""".control
  op
  ac dec 20 0.1 100meg
  wrdata {TAG}a.txt mag(v(s_out)) mag(v(w_out))
  noise v(s_out) Iph dec 10 0.1 100k
  setplot noise1
  wrdata {TAG}ns.txt onoise_spectrum
  noise v(w_out) Iph dec 20 1k 100meg
  setplot noise3
  wrdata {TAG}nw.txt onoise_spectrum
  quit
.endc"""
    sh("r.spice", make(idc, ibx, cc, vsg, ctl))
    ac, ns, nw = rd("a.txt"), rd("ns.txt"), rd("nw.txt")
    f = [r[0] for r in ac]
    gs = [r[1] / 1e-9 for r in ac]          # slow  V/A
    gw = [r[3] / 1e-9 for r in ac]          # wide  V/A
    near = lambda arr, x: min(arr, key=lambda r: abs(math.log(r[0] / x)))
    g_s10 = gs[min(range(len(f)), key=lambda i: abs(math.log(f[i] / 10)))]
    # slow -3 dB
    bw_s = next((f[i] for i in range(len(f)) if gs[i] < g_s10 / 1.4142), None)
    # wide band-pass: peak and -3 dB edges
    ipk = max(range(len(gw)), key=lambda i: gw[i])
    lo_w = next((f[i] for i in range(len(f)) if gw[i] > gw[ipk] / 1.4142), None)
    hi_w = next((f[i] for i in range(ipk, len(f)) if gw[i] < gw[ipk] / 1.4142), None)

    def slow_d(fr):
        r = near(ns, fr)
        gi = gs[min(range(len(f)), key=lambda i: abs(math.log(f[i] / r[0])))]
        return r[1] / gi

    def wide_d(fr):
        r = near(nw, fr)
        gi = gw[min(range(len(f)), key=lambda i: abs(math.log(f[i] / r[0])))]
        return r[1] / gi

    pts = [(r[0], slow_d(r[0])) for r in ns if 0.5 <= r[0] <= 100]
    rms = math.sqrt(sum(0.5 * (a[1] ** 2 + b[1] ** 2) * (b[0] - a[0]) for a, b in zip(pts, pts[1:])))
    return dict(vsg=vsg, g_s10=g_s10, bw_s=bw_s, g_wpk=gw[ipk], f_pk=f[ipk], lo_w=lo_w, hi_w=hi_w,
                s10=slow_d(10), s100=slow_d(100), s1k=slow_d(1e3), rms=rms,
                w10k=wide_d(1e4), w100k=wide_d(1e5), w316k=wide_d(3.16e5), w1m=wide_d(1e6))


if __name__ == "__main__":
    idc, ibx = sys.argv[1], sys.argv[2]
    for cc in sys.argv[3:]:
        r = run(idc, ibx, cc)
        if r is None:
            print(f"IDC={idc} IBX={ibx} CC={cc}: bracket/op failed", flush=True)
            continue
        print(f"IDC={idc} IBX={ibx} CC={cc} Vsg={r['vsg']:.4f}", flush=True)
        print(f"  slow: gain(10Hz)={r['g_s10']:.3g} V/A  -3dB={r['bw_s']}Hz | noise fA/rtHz @10/100/1k = "
              f"{r['s10']*1e15:.1f} {r['s100']*1e15:.1f} {r['s1k']*1e15:.1f}  RMS0.5-100Hz={r['rms']*1e12:.3f} pA", flush=True)
        print(f"  wide: peak gain={r['g_wpk']:.3g} V/A at {r['f_pk']:.3g}Hz  band {r['lo_w']}..{r['hi_w']} Hz | noise fA/rtHz @10k/100k/316k/1M = "
              f"{r['w10k']*1e15:.0f} {r['w100k']*1e15:.0f} {r['w316k']*1e15:.0f} {r['w1m']*1e15:.0f}", flush=True)
