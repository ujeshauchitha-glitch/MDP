"""Slow-path input-referred noise with servo + mirror in place.

The behavioral servo is replaced by a fixed Msv gate voltage (bisected so that
s_out = VCM); Msv's own device noise is kept, the digital loop's is not.

env: TAG (file-name prefix, lets runs go in parallel), GUESS (Vsg bracket
centre), VAR = msv4 | mir4 | both  (x4 area on Msv / mirror devices to see
which one carries flicker noise).
usage: python afe_slow_noise.py IDC IBX [IBX ...]
"""
import re, subprocess, os, sys, math, pathlib

D = pathlib.Path(__file__).resolve().parent.parent
B = D / "build"
NG = os.environ["NGSPICE"]
TAG = os.environ.get("TAG", "v0")
VAR = os.environ.get("VAR", "")
GUESS = os.environ.get("GUESS")

base = (D / "afe_front.spice").read_text(encoding="utf-8")
if VAR in ("msv4", "both"):
    base = base.replace("W=100 L=2\nBint", "W=100 L=2 m=4\nBint")
    base = re.sub(r"(XMsv[^\n]*W=100 L=2)\s*\n", r"\1 m=4\n", base) if "m=4" not in base else base
if VAR in ("mir4", "both"):
    for n in ("XMm ", "XMo1", "XMo2"):
        base = re.sub("(" + n + r" [^\n]*W=20 L=2)", r"\1 m=4", base)


def make(ibx, idc, mode, vsg, ctl):
    s = base.replace(".param IDC=10n", f".param IDC={idc}").replace(".param IBX=1u", f".param IBX={ibx}")
    s = re.sub(r"\* coarse acquisition[^\n]*\nBint[^\n]*\n", "", s)
    if mode == "real":
        s = re.sub(r"Cint[^\n]*\n", f"Vsv  vc_s vdpwr DC {-vsg}\n", s)
    else:  # ideal noiseless cancel (needs trimmed value; unreliable, see doc)
        s = re.sub(r"XMsv[^\n]*\n", "", s)
        s = re.sub(r"Cint[^\n]*\n", "Icmp vdpwr s_in DC {IBX+IDC}\n", s)
    return re.sub(r"\.control.*?\.endc", lambda m: ctl, s, flags=re.S)


def sh(name, text):
    (B / (TAG + name)).write_text(text, encoding="utf-8")
    return subprocess.run([NG, "-b", TAG + name], cwd=B, capture_output=True, text=True).stdout


def s_out(ibx, idc, vsg):
    out = sh("n_op.spice", make(ibx, idc, "real", vsg, ".control\n op\n print v(s_out)\n quit\n.endc"))
    m = re.search(r"v\(s_out\)\s*=\s*([-\d.e+]+)", out)
    return float(m.group(1)) if m else None


def bisect(ibx, idc):
    # s_out is railed high below the right Vsg and drops through 1.65 V in a
    # window only tens of uV wide (1 GOhm x ~nA): bracket first, then bisect.
    v = float(GUESS) - 0.05 if GUESS else 0.60
    stop = float(GUESS) + 0.06 if GUESS else 1.20
    prev = None
    lo = hi = None
    while v < stop:
        so = s_out(ibx, idc, v)
        if so is not None and so < 1.65 and prev is not None and prev[1] > 1.65:
            lo, hi = prev[0], v
            break
        if so is not None:
            prev = (v, so)
        v += 0.01
    if lo is None:
        return None
    for _ in range(20):
        mid = (lo + hi) / 2
        so = s_out(ibx, idc, mid)
        if so is None:
            return None
        if so > 1.65:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def noise(ibx, idc, mode, vsg):
    ctl = f""".control
  op
  ac dec 5 0.1 100k
  wrdata {TAG}n_ac.txt mag(v(s_out))
  noise v(s_out) Iph dec 20 0.1 100k
  setplot noise1
  wrdata {TAG}n_nz.txt onoise_spectrum
  quit
.endc"""
    sh("n_run.spice", make(ibx, idc, mode, vsg, ctl))
    rd = lambda f: [tuple(map(float, l.split())) for l in (B / (TAG + f)).read_text().splitlines() if l.strip()]
    ac, nz = rd("n_ac.txt"), rd("n_nz.txt")
    gain = ac[min(range(len(ac)), key=lambda i: abs(math.log(ac[i][0] / 10)))][1] / 1e-9  # V/A at 10 Hz
    dens = [(f, v / gain) for f, v in nz]
    at = lambda fr: min(dens, key=lambda d: abs(math.log(d[0] / fr)))[1]

    def rms(f1, f2):
        pts = [d for d in dens if f1 <= d[0] <= f2]
        return math.sqrt(sum(0.5 * (a[1] ** 2 + b[1] ** 2) * (b[0] - a[0]) for a, b in zip(pts, pts[1:])))

    return gain, at(10), at(100), at(1e3), rms(0.5, 100), rms(0.5, 5e3)


if __name__ == "__main__":
    idc = sys.argv[1]
    modes = ("real",) if VAR or os.environ.get("REAL_ONLY") else ("real", "ideal")
    print(f"[{TAG} {VAR or 'base'}] I_DC={idc} (gain V/A | density fA/rtHz @10/100/1k Hz | RMS pA 0.5-100 Hz, 0.5-5k Hz)")
    for ibx in sys.argv[2:]:
        vsg = bisect(ibx, idc)
        if vsg is None:
            print(" IBX", ibx, "bracket/op failed", flush=True)
            continue
        for mode in modes:
            g, d10, d100, d1k, r1, r2 = noise(ibx, idc, mode, vsg)
            print(f" IBX={ibx:>5} {mode:5} Vsg={vsg:.4f} gain={g:.3g} | {d10*1e15:8.1f} {d100*1e15:8.1f} {d1k*1e15:8.1f} | {r1*1e12:7.2f} pA {r2*1e12:7.2f} pA", flush=True)
