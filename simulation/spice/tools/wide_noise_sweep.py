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
    if o.get("opamp2") == "1":
        # Op-amp v2: no NMOS source-follower buffer (the CS stage drives the output, so amp_out sits at VCM
        # instead of VCM + Vgs, freeing ~1.3 V) and a cascoded PMOS load whose gate bias is AC-tied to VDD.
        dev_p, dev_n = "sky130_fd_pr__pfet_g5v0d10v5", "sky130_fd_pr__nfet_g5v0d10v5"
        rx = o.get("rcasc", "150k")
        for t in ("s", "w"):
            out = f"{t}_out"
            s = re.sub(rf"^(XM9_{t}|XM10_{t}) [^\n]*\n", "", s, flags=re.M)
            s = re.sub(rf"\bamp_out_{t}\b", out, s)
            s = s.replace(f"XM7_{t} {out} pbias_{t} vdpwr vdpwr {dev_p} W=20 L=2",
                          f"XM7_{t} mid7_{t} pbias_{t} vdpwr vdpwr {dev_p} W=20 L=2\n"
                          f"XM7c_{t} {out} pcasc_{t} mid7_{t} vdpwr {dev_p} W=20 L=2\n"
                          f"XMxa_{t} pxa_{t} pxa_{t} vdpwr vdpwr {dev_p} W=4 L=2\n"
                          f"Rxc_{t} pxa_{t} pcasc_{t} {rx}\n"
                          f"XMxc_{t} pcasc_{t} nbias_{t} vgnd vgnd {dev_n} W=4 L=2\n"
                          f"Ccasc_{t} pcasc_{t} vdpwr 10p")
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
    if "ibias" in o:   # supply-independent op-amp bias currents (ideal here) instead of R from VDD into the reference diode
        s = re.sub(r"^Rbias_s [^\n]*$", "Ibs vdpwr nbias_s DC " + o["ibias"].split(",")[0], s, flags=re.M)
        s = re.sub(r"^Rbias_w [^\n]*$", "Ibw vdpwr nbias_w DC " + o["ibias"].split(",")[1], s, flags=re.M)
    if o.get("inbulk") == "src":   # op-amp input pairs in their own n-well tied to the tail node: no VDD body effect on Vt
        s = re.sub(r"^(XM[12]_[sw]\s+\S+\s+\S+\s+(tail1_[sw]))\s+vdpwr", r"\1 \2", s, flags=re.M)
    if "msvm" in o or "msvl" in o:   # cancel-device geometry: multiplier m and channel length L (area study)
        s = s.replace("XMsv  x vc_s vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W=100 L=2",
                      "XMsv  x vc_s vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W=100 L=" + o.get("msvl", "2") + " m=" + o.get("msvm", "1"), 1)
    if "sdeg" in o:   # source-degenerated cancel (sink) device: lowers its flicker-noise current
        s = s.replace("XMsv  x vc_s vgnd vgnd", "XMsv  x vc_s sd_n vgnd", 1)
        s = s.replace(".param IDC", "Rsd   sd_n vgnd " + o["sdeg"] + "\n.param IDC", 1)
    if "cpb" in o:   # AC-tie the PMOS gate-bias nodes to VDD so tail / load current sources see no Vgs ripple
        s = s.replace(".param IDC", "Cpb_s pbias_s vdpwr " + o["cpb"] + "\nCpb_w pbias_w vdpwr " + o["cpb"] + "\n.param IDC", 1)
    if o.get("mcbulk") == "vcm":   # Mc well on the quiet VCM node: no VDD body path, well capacitance not on the signal node
        s = s.replace("XMc   dmir gc xc vdpwr", "XMc   dmir gc xc vcm", 1)
    if o.get("mcbulk") == "src":   # Mc in its own n-well tied to its source: no body-effect path from VDD ripple
        s = s.replace("XMc   dmir gc xc vdpwr", "XMc   dmir gc xc xc", 1)
    if o.get("mct") == "thin":   # thin-oxide Mc, own n-well (bulk = source) so Vgb stays < 1.8 V
        s = re.sub(r"XMc   dmir gc xc vdpwr sky130_fd_pr__pfet_g5v0d10v5", "XMc   dmir gc xc xc sky130_fd_pr__pfet_01v8", s)
    s = s.replace("XMb   gc   xc vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W=1  L=8",
                  f"XMb   gc   xc vgnd vgnd sky130_fd_pr__nfet_g5v0d10v5 W={o.get('mbw','1')} L={o.get('mbl','8')}")
    if "vgc" in o:   # no booster: plain common-gate PMOS Mc with an ideal fixed gate voltage
        s = re.sub(r"^(XMb |XMib |XMibd |Rib )[^\n]*\n", "", s, flags=re.M)
        s = s.replace("Ibx   vdpwr xc DC {IBX}", "Ibx   vdpwr xc DC {IBX}\nVgc   gc 0 DC " + o["vgc"])
    s = s.replace("Rib   pbias_b vgnd 1.5Meg", f"Rib   pbias_b vgnd {o.get('rib','1.5Meg')}")
    s = s.replace("Rbias_w vdpwr nbias_w 600k", f"Rbias_w vdpwr nbias_w {o.get('rbw','600k')}")
    if o.get("corner", "tt") != "tt":   # process corner: swap the model library
        c = o["corner"]
        tt = (B / "sky130_min.lib").read_text(encoding="utf-8")
        lib = tt.replace("__tt.", f"__{c}.").replace("/tt/", f"/{c}/")
        (B / f"sky130_min_{c}.lib").write_text(lib, encoding="utf-8")
        s = s.replace('.include "sky130_min.lib"', f'.include "sky130_min_{c}.lib"')
    if o.get("tnet") == "1":   # poly T-network feedback (R1=R2=t1, R3=t3 to VCM) instead of the PMOS pseudo-resistor
        s = re.sub(r"^XMPR1_s [^\n]*\n", f"R1_s   x tn_s {o.get('t1','10Meg')}\n", s, flags=re.M)
        s = re.sub(r"^XMPR2_s [^\n]*\n", f"R2_s   tn_s s_out {o.get('t1','10Meg')}\nR3_s   tn_s vcm {o.get('t3','102k')}\n", s, flags=re.M)
        s = s.replace("Cf_s x s_out 1f", f"Cf_s x s_out {o.get('tcf','50f')}")
        if "rpar" in o:   # lower-gain range: switched resistor in parallel with the whole T-network (switch Ron ignored)
            s = s.replace(f"R3_s   tn_s vcm {o.get('t3','102k')}\n", f"R3_s   tn_s vcm {o.get('t3','102k')}\nRp_s   x s_out {o['rpar']}\n", 1)
    if "vcm" in o:   # common-mode level of both TIAs (default 1.65 V)
        v = o["vcm"]
        s = s.replace("VCM  vcm   0 DC 1.65", f"VCM  vcm   0 DC {v}")
        s = re.sub(r"(v\((?:x|s_out|w_in|w_out)\))=1\.65", lambda m: f"{m.group(1)}={v}", s)
        s = s.replace("abs(v(s_out)-1.65)", f"abs(v(s_out)-{v})").replace("(1.65-v(s_out))", f"({v}-v(s_out))")
    if "vdd" in o:   # supply sensitivity
        s = s.replace("VPWR vdpwr 0 DC 3.3", f"VPWR vdpwr 0 DC {o['vdd']}")
    if o.get("tight") == "1":   # pA-level cancel currents through multi-GOhm feedback need tight solver tolerances
        s = s.replace(".option scale=1u", ".option scale=1u\n.option abstol=1e-16 vntol=1e-9 reltol=1e-5", 1)
    if "temp" in o:
        s = s.replace(".option scale=1u", f".option scale=1u\n.temp {o['temp']}", 1)
    extra = ""
    if o.get("real") == "1":
        # Real PMOS mirror bias replaces the ideal Ibx (into xc) and Icompw (into w_in).
        # Reference: diode PMOS + Rref to ground, filter cap on the gate; two 1:1
        # outputs. Equal source degeneration Rs in all three legs.
        rs, rref, cref = o.get("rs", "1Meg"), o.get("rref", "6.5Meg"), o.get("cref", "20p")
        pw, pl = o.get("pw", "10"), o.get("pl", "4")
        dev = "sky130_fd_pr__pfet_g5v0d10v5"
        blk = (f"* ---- real PMOS bias mirror (replaces ideal Ibx / Icompw) ----\n"
               f"Rs0   vdpwr s0 {rs}\nXMp0  pref pref s0 vdpwr {dev} W={pw} L={pl}\n"
               f"Rref  pref vgnd {rref}\nCref  pref vdpwr {cref}\n"
               f"Rsx   vdpwr sx {rs}\nXMpx  xc   pref sx vdpwr {dev} W={pw} L={pl}\n"
               f"Rsw   vdpwr sw {rs}\nXMpw  w_in pref sw vdpwr {dev} W={pw} L={pl}\n")
        if o.get("ccas") == "1":   # cascode the cancel leg so its VDD-following gate/source/well caps do not drive the TIA input
            blk = blk.replace(f"XMpw  w_in pref sw vdpwr {dev} W={pw} L={pl}\n",
                              f"XMpw  wc pref sw vdpwr {dev} W={pw} L={pl}\nXMpwc w_in vcw wc wc {dev} W={pw} L={pl}\nVcw   vcw 0 DC {o.get('vcw', '0.75')}\n")
        if "iref" in o:   # supply-independent reference current (bandgap-derived in silicon; ideal here) instead of Rref to ground
            blk = blk.replace(f"Rref  pref vgnd {rref}\n", f"Iref  pref vgnd DC {o['iref']}\n")
        assert "Icompw vdpwr w_in DC {IBX}" in s and "Ibx   vdpwr xc DC {IBX}" in s
        s = s.replace("Icompw vdpwr w_in DC {IBX}", "* Icompw replaced by XMpw")
        s = s.replace("Ibx   vdpwr xc DC {IBX}", blk)
        s = s.replace(".nodeset ", ".nodeset v(pref)=1.0 v(s0)=3.2 v(sx)=3.2 v(sw)=3.2 ", 1)
        extra = " v(s0) v(sx) v(sw) v(pref)"
    # worst-case gate-referred threshold-offset hooks for the mismatch sensitivity study [V]
    hooks = ""
    if "vmm" in o:    # mirror output device Mo1 vs diode Mm
        s = s.replace("XMo1  w_in dmir", "XMo1  w_in gmo", 1); hooks += "Vmm gmo dmir DC " + o["vmm"] + "\n"
    if "vbw" in o:    # bias mirror: wide-input cancel leg vs reference
        s = s.replace("XMpw  w_in pref", "XMpw  w_in gpw", 1); hooks += "Vbw gpw pref DC " + o["vbw"] + "\n"
    if "vbx" in o:    # bias mirror: xc bias leg vs reference
        s = s.replace("XMpx  xc   pref", "XMpx  xc   gpx", 1); hooks += "Vbx gpx pref DC " + o["vbx"] + "\n"
    if "vosw" in o:   # wideband TIA op-amp input offset (series with the M1 gate)
        s = s.replace("XM1_w n1out_w w_in", "XM1_w n1out_w gin_w", 1); hooks += "Vosw gin_w w_in DC " + o["vosw"] + "\n"
    if hooks:
        s = s.replace(".param IDC", hooks + ".param IDC", 1)
    ctl = f""".control
  op
  print v(x) v(xc) v(dmir) v(gc) v(w_in) v(w_out){extra}
  let p = -i(VPWR)*3.3
  print p
  ac dec 40 1k 20meg
  wrdata {TAG}h.txt v(w_out)
  noise v(w_out) Iph dec 40 1k 20meg
  setplot noise1
  wrdata {TAG}n.txt onoise_spectrum
  quit
.endc"""
    if o.get("oponly") == "1":
        sx = "" if o.get("slow", "1") == "0" else " v(s_out)"
        ctl = f".control\n  op\n  print v(x) v(xc) v(dmir) v(gc) v(w_in) v(w_out){sx}{extra}\n  quit\n.endc"
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
    d_per_m = abs(mu1) / sigma               # detection SNR per unit modulation depth (receiver may flip sign)
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
