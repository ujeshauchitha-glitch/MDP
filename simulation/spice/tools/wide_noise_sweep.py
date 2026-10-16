"""Wideband-path noise sweeps on the option-1 front end.

Figure of merit = coherent-detection SNR d = mu/sigma0 for the 48-chip code
(same chain as simulation/detect/coherent_mc.py) but with sigma0 computed
analytically from the SPICE output-noise PSD:
    sigma0^2 = (N/NS^2) * int S_out(f) * D(f) df ,
    D(f) = sin^2(pi f OS/FS) / sin^2(pi f/FS)           (rect-chip correlator)
and mu from a noise-free pass through H(f) averaged over random codes.
Quoted as d per (m * I_DC[nA]) and the I_DC [nA] needed for Pd=99.9% @ Pfa=1e-8
(d = 8.70) at m = 2 %.

variants 'slow=0' remove the slow TIA + servo (an ideal 1 MH inductor holds x
at VCM) to separate the slow path's noise contribution.

usage: TAG=w1_ python wide_noise_sweep.py NAME key=val [key=val ...]
keys: slow(0/1) idc ibx cc mm(mirror mult) rdeg(ohm) mcw mcl mbw mbl rbw(wide Rbias)
      vsg (Msv gate voltage when slow=1)
"""
import os, re, sys, subprocess, pathlib, math
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
D = HERE.parent
sys.path.insert(0, str(D.parent / "detect"))
import coherent_mc as cm   # noqa: E402

B = D / "build"
NG = os.environ["NGSPICE"]
TAG = os.environ.get("TAG", "w0_")
Q_E = 1.602176634e-19
DREQ = cm.D_REQ


def netlist(o):
    s = (D / "afe_direct.spice").read_text(encoding="utf-8")
    s = s.replace(".param IDC=100n", f".param IDC={o.get('idc','100n')}")
    s = s.replace(".param IBX=1u", f".param IBX={o.get('ibx','1u')}").replace(".param CC=50p", f".param CC={o.get('cc','50p')}")
    s = s.replace(".option gmin=1e-17", ".option gmin=1e-14")
    s = re.sub(r"\* coarse acquisition[^\n]*\nBint[^\n]*\n", "", s)
    if o.get("slow", "1") == "0":
        a = s.index("* ---- slow path DC servo"); b = s.index("* ===== wideband TIA =====")
        s = s[:a] + "Lx x vcm 1e6\n\n" + s[b:]
    else:
        s = re.sub(r"Cint[^\n]*\n", f"Vsv  vc_s vgnd DC {o['vsg']}\n", s)
    mm = o.get("mm", "1"); rd = o.get("rdeg", "0")
    mir_m = f" m={mm}" if mm != "1" else ""
    if rd != "0":
        s = s.replace("XMm   dmir dmir vgnd vgnd", "XMm   dmir dmir sm vgnd").replace("XMo1  w_in dmir vgnd vgnd", "XMo1  w_in dmir so vgnd")
        s = s.replace("Icompw vdpwr w_in DC {IBX}", f"Icompw vdpwr w_in DC {{IBX}}\nRdm sm vgnd {rd}\nRdo so vgnd {rd}")
    s = re.sub(r"(XMm [^\n]*W=20 L=2)", r"\1" + mir_m, s)
    s = re.sub(r"(XMo1 [^\n]*W=20 L=2)", r"\1" + mir_m, s)
    s = s.replace("XMc   dmir gc xc vdpwr sky130_fd_pr__pfet_g5v0d10v5 W=20 L=1",
                  f"XMc   dmir gc xc vdpwr sky130_fd_pr__pfet_g5v0d10v5 W={o.get('mcw','20')} L={o.get('mcl','1')}")
    if o.get("mct") == "thin":   # thin-oxide Mc, own n-well (bulk = source) so Vgb stays < 1.8 V
        s = re.sub(r"XMc   dmir gc xc vdpwr sky130_fd_pr__pfet_g5v0d10v5", "XMc   dmir gc xc xc sky130_fd_pr__pfet_01v8", s)
    s = s.replace("XMb   gc   xc vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W=1  L=8",
                  f"XMb   gc   xc vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W={o.get('mbw','1')} L={o.get('mbl','8')}")
    if "vgc" in o:   # no booster: plain common-gate PMOS Mc with an ideal fixed gate voltage
        s = re.sub(r"^(XMb |XMib |XMibd |Rib )[^\n]*\n", "", s, flags=re.M)
        s = s.replace("Ibx   vdpwr xc DC {IBX}", "Ibx   vdpwr xc DC {IBX}\nVgc   gc 0 DC " + o["vgc"])
    s = s.replace("Rib   pbias_b vgnd 1.5Meg", f"Rib   pbias_b vgnd {o.get('rib','1.5Meg')}")
    s = s.replace("Rbias_w vdpwr nbias_w 600k", f"Rbias_w vdpwr nbias_w {o.get('rbw','600k')}")
    ctl = f""".control
  op
  print v(x) v(xc) v(dmir) v(gc) v(w_in) v(w_out)
  let p = -i(VPWR)*3.3
  print p
  ac dec 40 1k 20meg
  wrdata {TAG}h.txt v(w_out)
  noise v(w_out) Iph dec 40 1k 20meg
  setplot noise1
  wrdata {TAG}n.txt onoise_spectrum
  quit
.endc"""
    return re.sub(r"\.control.*?\.endc", lambda m: ctl, s, flags=re.S)


def fom(o):
    (B / f"{TAG}v.spice").write_text(netlist(o), encoding="utf-8")
    out = subprocess.run([NG, "-b", f"{TAG}v.spice"], cwd=B, capture_output=True, text=True).stdout
    rd = lambda f: np.loadtxt(B / (TAG + f))
    h, n = rd("h.txt"), rd("n.txt")
    f = h[:, 0]; H = (h[:, 1] + 1j * h[:, 2]) / 1e-9; Sn = n[:, 1]
    pw = re.search(r"^p\s*=\s*([-\d.e+]+)", out, re.M)
    return f, H, Sn, float(pw.group(1)) if pw else float("nan"), out


def metric(f, H, Sn, idc_a):
    S_out = Sn ** 2 + 2 * Q_E * idc_a * np.abs(H) ** 2
    m = f <= cm.FS / 2
    ff, SS = f[m], S_out[m]
    D_ = np.sin(np.pi * ff * cm.OS / cm.FS) ** 2 / np.sin(np.pi * ff / cm.FS) ** 2
    sigma2 = (cm.N / cm.NS ** 2) * np.trapezoid(SS * D_, ff)
    sigma = math.sqrt(sigma2)
    fg = np.fft.rfftfreq(cm.L, 1 / cm.FS)
    lf, lfg = np.log(f), np.log(np.maximum(fg, f[0]))
    Hg = np.interp(lfg, lf, H.real) + 1j * np.interp(lfg, lf, H.imag)
    Hg[fg < f[0]] = 0.0
    d = cm.best_delay(Hg)
    rng = np.random.default_rng(7)
    c = cm.make_codes(rng, 300); cu = cm.upsample(c)
    y = np.fft.irfft(np.fft.rfft(cu * idc_a, axis=1) * Hg, n=cm.L, axis=1)      # m = 1 (unit depth)
    z = (y[:, 2 * cm.NS + d: 3 * cm.NS + d] * cu[:, 2 * cm.NS: 3 * cm.NS]).sum(axis=1) / cm.NS
    mu1 = z.mean()
    d_per_m = mu1 / sigma                    # detection SNR per unit modulation depth
    idc_nA = idc_a * 1e9
    d_per_m_nA = d_per_m / idc_nA            # per (m * nA)
    need_nA_2pct = DREQ / (0.02 * d_per_m_nA)
    return sigma, d_per_m_nA, need_nA_2pct, d


def parse(a):
    o = {}
    for kv in a:
        k, v = kv.split("=", 1); o[k] = v
    return o


def tonum(x):
    return float(x.replace("n", "e-9").replace("u", "e-6").replace("p", "e-12"))


if __name__ == "__main__":
    name = sys.argv[1]; o = parse(sys.argv[2:])
    f, H, Sn, pw, _ = fom(o)
    idc_a = tonum(o.get("idc", "100n"))
    sigma, dn_, need, dly = metric(f, H, Sn, idc_a)
    # input-referred density at a few frequencies
    def rti(fr):
        i = int(np.argmin(np.abs(np.log(f / fr)))); return Sn[i] / abs(H[i]) * 1e15
    op = {k: float(m.group(1)) for k in ("x", "xc", "dmir", "gc", "w_in", "w_out") if (m := re.search(rf"^v\({k}\)\s*=\s*([-\d.e+]+)", _, re.M))}
    print(f"{name:28s} op xc/dmir/gc/w_in={op.get('xc',0):.2f}/{op.get('dmir',0):.2f}/{op.get('gc',0):.2f}/{op.get('w_in',0):.3f} sigma0={sigma*1e6:7.2f}uV  d/(m*nA)={dn_:.4f}  I_DC for Pd99.9@m2%={need:6.1f} nA  "
          f"RTI fA/rtHz @30k/100k/316k={rti(3e4):.0f}/{rti(1e5):.0f}/{rti(3.16e5):.0f}  |H|@100k={abs(H[int(np.argmin(np.abs(np.log(f/1e5))))]):.3g}  P={pw*1e6:.0f}uW", flush=True)
