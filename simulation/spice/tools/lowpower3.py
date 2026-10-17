import sys,re,subprocess,numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import wide_noise_sweep as w
FIN=dict(vgc="0",mcw="80",ibx="300n",mm="4",rdeg="200k",real="1",rs="3Meg",rref="3.6314Meg",cref="20p",idc="100n",
         tnet="1",t1="10Meg",t3="102k",tcf="50f",vcm="1.4",iref="300n",mcbulk="vcm",inbulk="src")
def resonance(f,mag,fpk):
    """largest rise (dB) of |H| above the pass-band peak, i.e. secondary resonance / peaking indicator"""
    m=(f>fpk)
    ff,mm=f[m],20*np.log10(mag[m])
    run=np.minimum.accumulate(mm)         # running minimum going up in frequency
    return float(np.max(mm-run))
def go(tag,corner,temp,vdd,vsg,ib,cf="50f",rpar=None):
    o=dict(FIN,corner=corner,temp=temp,vdd=vdd,vsg=vsg,slow="1",ibias=ib,tcf=cf)
    if rpar: o["rpar"]=rpar
    t=w.netlist(o)
    ctl=""".control
  op
  print i(VPWR)
  ac dec 40 1 20meg
  wrdata lp.txt v(w_out) v(s_out)
  quit
.endc"""
    t=re.sub(r"\.control.*?\.endc",lambda m:ctl,t,flags=re.S)
    (w.B/"lp.spice").write_text(t,encoding="utf-8")
    out=subprocess.run([w.NG,"-b","lp.spice"],cwd=w.B,capture_output=True,text=True).stdout
    i=-float(re.search(r"i\(vpwr\)\s*=\s*([-\d.e+]+)",out,re.I).group(1))
    d=np.loadtxt(w.B/"lp.txt")
    f=d[:,0]; hw=np.abs(d[:,1]+1j*d[:,2]); hs=np.abs(d[:,4]+1j*d[:,5])
    kw=int(np.argmax(hw)); 
    # slow path: peaking above the 10 Hz value
    gs10=hs[int(np.argmin(abs(np.log(f/10))))]
    peak_s=20*np.log10(hs.max()/gs10)
    res_w=resonance(f,hw,f[kw]); 
    print(f"{rpar or '1G':8s} Cf={cf:5s} {tag:8s} {corner}/{temp}C {vdd}V ibias={ib:9s} P={i*float(vdd)*1e6:6.0f} uW ({i*1e6:5.1f} uA) | slow peaking {peak_s:+5.2f} dB, slow -3dB~{f[np.where((hs<gs10/1.4142)&(f>10))[0][0]]:.0f} Hz | wide peak at {f[kw]/1e3:.0f} kHz, resonance indicator {res_w:.2f} dB",flush=True)
cs=[("tt27","tt","27","3.3","0.552389"),("ss125","ss","125","2.97","0.373863"),("ff-40","ff","-40","3.63","0.663200")]
for rp,cfs in (("111Meg",("100f","200f","300f")),("10.1Meg",("500f","1p","1.5p"))):
    for cf in cfs:
        for tag,c,tp,vdd,vsg in cs:
            go(tag,c,tp,vdd,vsg,"0.5u,1u",cf,rp)
