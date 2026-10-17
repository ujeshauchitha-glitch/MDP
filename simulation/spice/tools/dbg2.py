import sys,re,subprocess,numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import wide_noise_sweep as w
base=dict(slow="1",vgc="0",mcw="80",ibx="300n",mm="4",rdeg="200k",real="1",rs="3Meg",rref="3.6314Meg",cref="20p",idc="100n",
       tnet="1",t1="10Meg",t3="102k",tcf="50f",vcm="1.4",vsg="0.5524",tight="1")
nodes=["x","s_out","tn_s","xc","dmir","gmo","sx","sw","s0","pref","w_in","w_out","tail1_s","n2out_s","pbias_s"]
def run(o,fr):
    text=w.netlist(dict(base,**o))
    text=text.replace("VPWR vdpwr 0 DC 3.3","VPWR vdpwr 0 DC 3.3 AC 1").replace("DC {IDC} AC 1n","DC {IDC} AC 0")
    ok=[n for n in nodes if re.search(rf"\b{n}\b",text)]
    pr=" ".join(f"mag(v({n}))" for n in ok)
    ctl=f".control\n  op\n  ac lin 1 {fr} {fr}\n  wrdata dbg.txt {pr}\n  quit\n.endc"
    t=re.sub(r"\.control.*?\.endc",lambda m:ctl,text,flags=re.S)
    (w.B/"dbg.spice").write_text(t,encoding="utf-8")
    subprocess.run([w.NG,"-b","dbg.spice"],cwd=w.B,capture_output=True,text=True)
    d=np.loadtxt(w.B/"dbg.txt").ravel()
    return dict(zip(ok,d[1::2]))
for label,o in (("old (Mc bulk=VDD)",{}),("Mc bulk=src",dict(mcbulk="src"))):
    for fr in (100,):
        r=run(o,fr); print(label,fr,"Hz:","  ".join(f"{k}={v:.3g}" for k,v in r.items()))
