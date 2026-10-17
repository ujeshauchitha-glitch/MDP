import sys,re,subprocess,numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import wide_noise_sweep as w
O=dict(slow="1",vgc="0",mcw="80",ibx="300n",mm="4",rdeg="200k",real="1",rs="3Meg",rref="3.6314Meg",cref="20p",idc="100n",
       tnet="1",t1="10Meg",t3="102k",tcf="50f",vcm="1.4",vsg="0.5524",tight="1",mcbulk="vcm",iref="300n")
base=w.netlist(O)
i_slow=base.index("* ===== slow TIA =====")
i_wide=base.index("* ===== wideband TIA =====")
i_end=base.index(".param IDC",i_wide)
i_bias=base.index("* ---- real PMOS bias mirror")
i_bias_end=base.index("* ---- 1:1 mirror") if "* ---- 1:1 mirror" in base else None
def isolate(mode):
    s=base
    segs={"slowTIA":(i_slow,i_wide),"wideTIA":(i_wide,i_end)}
    if mode in segs:
        a,b=segs[mode]; s=s[:a]+s[a:b].replace("vdpwr","vdd_x")+s[b:]
    elif mode=="bias":
        # the real-bias block: lines from the marker to the mirror devices
        a=i_bias; b=s.index("XMm ",a)
        s=s[:a]+s[a:b].replace("vdpwr","vdd_x")+s[b:]
    elif mode=="mirror":
        a=s.index("XMm "); b=s.index("Icompw") if "Icompw" in s else a
        s=s
    if mode!="none": s=s.replace("VCM  vcm   0 DC 1.4","VCM  vcm   0 DC 1.4\nVX vdd_x 0 DC 3.3",1)
    return s
def run(mode,fr_list):
    text=isolate(mode)
    text=text.replace("VPWR vdpwr 0 DC 3.3","VPWR vdpwr 0 DC 3.3 AC 1").replace("DC {IDC} AC 1n","DC {IDC} AC 0")
    pr="mag(v(w_out)) mag(v(s_out))"
    res={}
    for fr in fr_list:
        ctl=f".control\n  op\n  ac lin 1 {fr} {fr}\n  wrdata pb.txt {pr}\n  quit\n.endc"
        t=re.sub(r"\.control.*?\.endc",lambda m:ctl,text,flags=re.S)
        (w.B/"pb.spice").write_text(t,encoding="utf-8")
        subprocess.run([w.NG,"-b","pb.spice"],cwd=w.B,capture_output=True,text=True)
        d=np.loadtxt(w.B/"pb.txt").ravel(); res[fr]=(d[1],d[3])
    return res
frs=(100,1000,1e5,1e6)
print("mode        |w_out/VDD| @100k, @1M        |s_out/VDD| @100Hz, @1kHz")
for mode in ("none","slowTIA","wideTIA","bias"):
    r=run(mode,frs)
    print(f"{mode:10s}  {r[1e5][0]:.3g}  {r[1e6][0]:.3g}         {r[100][1]:.3g}  {r[1000][1]:.3g}",flush=True)
