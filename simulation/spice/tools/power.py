import sys,re,subprocess
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import wide_noise_sweep as w
FIN=dict(vgc="0",mcw="80",ibx="300n",mm="4",rdeg="200k",real="1",rs="3Meg",rref="3.6314Meg",cref="20p",idc="100n",
         tnet="1",t1="10Meg",t3="102k",tcf="50f",vcm="1.4",iref="300n",mcbulk="vcm",inbulk="src",ibias="2u,4u")
def ptot(o):
    t=w.netlist(dict(o,oponly="1"))
    t=re.sub(r"\.control.*?\.endc",lambda m:".control\n  op\n  print i(VPWR)\n  quit\n.endc",t,flags=re.S)
    (w.B/"pw.spice").write_text(t,encoding="utf-8")
    out=subprocess.run([w.NG,"-b","pw.spice"],cwd=w.B,capture_output=True,text=True).stdout
    m=re.search(r"i\(vpwr\)\s*=\s*([-\d.e+]+)",out,re.I)
    return -float(m.group(1))
cases=[("tt27 3.3V","tt","27","3.3","0.552389"),("tt27 3.63V","tt","27","3.63","0.552389"),("ss125 2.97V","ss","125","2.97","0.373863"),
       ("ff-40 3.63V","ff","-40","3.63","0.6632"),("tt125 3.3V","tt","125","3.3","0.343940")]
print("case           total   wide-only  slow-only(+servo sink)   [uA / uW]")
for nm,c,tmp,vdd,vsg in cases:
    base=dict(FIN,corner=c,temp=tmp,vdd=vdd)
    full=ptot(dict(base,slow="1",vsg=vsg))
    wide=ptot(dict(base,slow="0"))
    v=float(vdd)
    print(f"{nm:14s} {full*1e6:6.1f} uA {full*v*1e6:6.0f} uW | wide {wide*1e6:6.1f} uA {wide*v*1e6:5.0f} uW | slow {(full-wide)*1e6:6.1f} uA {(full-wide)*v*1e6:5.0f} uW",flush=True)
