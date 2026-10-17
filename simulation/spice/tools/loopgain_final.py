"""Loop gain and phase margin of both TIAs in the FINAL netlist (AC voltage injected in series with
the feedback path, single-injection method: the feedback network is high-impedance against a
low-impedance output, so the Middlebrook correction is small).

Slow TIA (T-network, 1 GOhm range): the elements that connect to s_out (R2_s, Cf_s, and Rp_s when a range
resistor is present) are moved to node fb_s; Vinj fb_s s_out AC 1. T = -v(s_out)/v(fb_s).
Wide TIA: Rf_w and Cf_w moved to fb_w; T = -v(w_out)/v(fb_w).

usage: TAG=lg_ python loopgain_final.py ibias(slow,wide e.g. 0.5u,1u) tcf corner temp vdd vsg [rpar]
"""
import re, sys, subprocess, pathlib, math
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wide_noise_sweep as w   # noqa: E402

ib, tcf, corner, temp, vdd, vsg = sys.argv[1:7]
rpar = sys.argv[7] if len(sys.argv) > 7 else None
O = dict(slow="1", vgc="0", mcw="80", ibx="300n", mm="4", rdeg="200k", real="1", rs="3Meg", rref="3.6314Meg", cref="20p",
         idc="100n", tnet="1", t1="10Meg", t3="102k", tcf=tcf, vcm="1.4", iref="300n", mcbulk="vcm", inbulk="src",
         ibias=ib, corner=corner, temp=temp, vdd=vdd, vsg=vsg)
if rpar:
    O["rpar"] = rpar
text = w.netlist(O)
for line in ("R2_s", "Cf_s", "Rp_s", "Rf_w", "Cf_w"):
    pass
text = re.sub(r"^(R2_s\s+tn_s\s+)s_out", r"\1fb_s", text, flags=re.M)
text = re.sub(r"^(Cf_s\s+x\s+)s_out", r"\1fb_s", text, flags=re.M)
text = re.sub(r"^(Rp_s\s+x\s+)s_out", r"\1fb_s", text, flags=re.M)
text = re.sub(r"^(Rf_w\s+w_in\s+)w_out", r"\1fb_w", text, flags=re.M)
text = re.sub(r"^(Cf_w\s+w_in\s+)w_out", r"\1fb_w", text, flags=re.M)
text = text.replace(".param IDC", "Vinj_s fb_s s_out DC 0 AC 1\nVinj_w fb_w w_out DC 0 AC 1\n.param IDC", 1)
# Iph AC = 0 so only the injections excite the circuit; run each injection separately
def run(tag, on_s):
    t = text.replace("DC {IDC} AC 1n", "DC {IDC} AC 0")
    t = t.replace("Vinj_s fb_s s_out DC 0 AC 1", "Vinj_s fb_s s_out DC 0 AC " + ("1" if on_s else "0"))
    t = t.replace("Vinj_w fb_w w_out DC 0 AC 1", "Vinj_w fb_w w_out DC 0 AC " + ("0" if on_s else "1"))
    ctl = f""".control
  op
  ac dec 40 1 100meg
  wrdata {w.TAG}{tag}.txt v(s_out) v(fb_s) v(w_out) v(fb_w)
  quit
.endc"""
    t = re.sub(r"\.control.*?\.endc", lambda m: ctl, t, flags=re.S)
    (w.B / f"{w.TAG}{tag}.spice").write_text(t, encoding="utf-8")
    subprocess.run([w.NG, "-b", f"{w.TAG}{tag}.spice"], cwd=w.B, capture_output=True, text=True)
    d = np.loadtxt(w.B / f"{w.TAG}{tag}.txt")
    f = d[:, 0]
    c = lambda k: d[:, k] + 1j * d[:, k + 1]
    return f, c(1), c(4), c(7), c(10)      # wrdata repeats the frequency column before each vector


def margins(f, T, name):
    mag = 20 * np.log10(np.abs(T)); ph = np.degrees(np.unwrap(np.angle(T)))
    ph = ph - 360 * np.round((ph[0]) / 360)          # start near 0
    res = f"{name}: DC loop gain {mag[0]:.1f} dB"
    for a in range(len(f) - 1):
        if mag[a] > 0 >= mag[a + 1]:
            t = mag[a] / (mag[a] - mag[a + 1]); fu = f[a] * (f[a + 1] / f[a]) ** t
            p = ph[a] + t * (ph[a + 1] - ph[a])
            res += f", unity-gain {fu:.4g} Hz, PM {180 + p:.1f} deg"
            # gain margin: first -180 crossing above fu
            for b in range(a, len(f) - 1):
                if ph[b] > -180 >= ph[b + 1]:
                    tb = (ph[b] + 180) / (ph[b] - ph[b + 1]); gm = -(mag[b] + tb * (mag[b + 1] - mag[b]))
                    res += f", GM {gm:.1f} dB"; break
            return res
    return res + ", no unity crossing"


f, vs, fbs, vw, fbw = run("S", True)
print(f"{corner}/{temp}C {vdd}V ibias={ib} Cf={tcf}" + (f" rpar={rpar}" if rpar else ""))
print("  slow :", margins(f, -vs / fbs, "T_slow"))
f, vs, fbs, vw, fbw = run("W", False)
print("  wide :", margins(f, -vw / fbw, "T_wide"))
