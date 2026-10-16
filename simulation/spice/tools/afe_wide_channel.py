"""Extract the wideband channel of the option-1 front end (afe_direct.spice)
for the coherent-detection Monte Carlo (simulation/detect/coherent_mc.py).

Per I_DC it writes simulation/spice/results/chan_<idc>.txt with columns
    f[Hz]  Re(H)  Im(H)  Sn      H  = v(w_out)/Iph  [V/A]
                                 Sn = output noise density [V/rtHz]
The servo is replaced by a bisected fixed Msv gate voltage (see
afe_direct_noise.py). Photodiode shot noise is NOT in SPICE; the Monte Carlo
adds 2*q*I_DC (A^2/Hz) at the input.

usage: TAG=c1_ python afe_wide_channel.py IDC [IBX] [CC]
"""
import os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import afe_direct_noise as dn   # noqa: E402  (reads env TAG / NGSPICE)

idc = sys.argv[1]
ibx = sys.argv[2] if len(sys.argv) > 2 else "1u"
cc = sys.argv[3] if len(sys.argv) > 3 else "50p"

vsg = dn.bisect(idc, ibx, cc)
if vsg is None:
    sys.exit(f"bisect failed for IDC={idc}")
ctl = f""".control
  op
  ac dec 40 1k 20meg
  wrdata {dn.TAG}h.txt v(w_out)
  noise v(w_out) Iph dec 40 1k 20meg
  setplot noise1
  wrdata {dn.TAG}n.txt onoise_spectrum
  quit
.endc"""
dn.sh("c.spice", dn.make(idc, ibx, cc, vsg, ctl))
h = dn.rd("h.txt")
n = dn.rd("n.txt")
assert len(h) == len(n), (len(h), len(n))
out = pathlib.Path(__file__).resolve().parent.parent / "results"
out.mkdir(exist_ok=True)
with open(out / f"chan_{idc}.txt", "w") as fh:
    fh.write(f"# afe_direct.spice wide channel, IDC={idc} IBX={ibx} Cc={cc} Vsg={vsg:.5f}\n")
    for a, b in zip(h, n):
        fh.write(f"{a[0]:.6e} {a[1]/1e-9:.6e} {a[2]/1e-9:.6e} {b[1]:.6e}\n")
print("wrote", out / f"chan_{idc}.txt", "Vsg", vsg)
