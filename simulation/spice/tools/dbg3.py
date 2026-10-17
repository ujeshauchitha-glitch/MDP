import sys,re,subprocess,numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import wide_noise_sweep as w
base=dict(slow="1",vgc="0",mcw="80",ibx="300n",mm="4",rdeg="200k",real="1",rs="3Meg",rref="3.6314Meg",cref="20p",idc="100n",
       tnet="1",t1="10Meg",t3="102k",tcf="50f",vcm="1.4",vsg="0.5524",tight="1",mcbulk="vcm",iref="300n")
nodes=["x","xc","dmir","gmo","w_in","w_out","sx","sw","s0","pref","tail1_w","n1out_w","n2out_w","amp_out_w","pbias_w","nbias_w","s_out","tail1_s","n2out_s","amp_out_s","pbias_s","nbias_s","gc"]
def run(fr):
    text=w.netlist(base)
    text=text.replace("VPWR vdpwr 0 DC 3.3","VPWR vdpwr 0 DC 3.3 AC 1").replace("DC {IDC} AC 1n","DC {IDC} AC 0")
    ok=[n for n in nodes if re.search(rf"\b{n}\b",text)]
    pr=" ".join(f"mag(v({n}))" for n in ok)
    ctl=f".control\n  op\n  ac lin 1 {fr} {fr}\n  wrdata dbg.txt {pr}\n  quit\n.endc"
    t=re.sub(r"\.control.*?\.endc",lambda m:ctl,text,flags=re.S)
    (w.B/"dbg.spice").write_text(t,encoding="utf-8")
    subprocess.run([w.NG,"-b","dbg.spice"],cwd=w.B,capture_output=True,text=True)
    d=np.loadtxt(w.B/"dbg.txt").ravel()
    return dict(zip(ok,d[1::2]))
for fr in (1e5,3e5,1e6):
    r=run(fr); print(f"--- {fr:.0e} Hz |v/VDD|:"); print("  "+"  ".join(f"{k}={v:.3g}" for k,v in r.items()))
