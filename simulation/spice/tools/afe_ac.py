import re,subprocess,os,math
base=open('../afe_front.spice').read()

def go(idc,tag):
    s=base.replace(".param IDC=10n",".param IDC="+idc)
    s=re.sub(r"\.control.*?\.endc",""".control
  op
  ac dec 20 10 100meg
  wrdata acw.txt db(v(w_out)) db(v(s_out)) db(v(x))
  noise v(w_out) Iph dec 10 1k 10meg
  setplot noise1
  wrdata nw.txt onoise_spectrum
  quit
.endc""",s,flags=re.S)
    open('t.spice','w').write(s)
    subprocess.run([os.environ['NGSPICE'],'-b','t.spice'],capture_output=True,text=True)
    rows=[list(map(float,l.split())) for l in open('acw.txt') if l.strip()]
    f=[r[0] for r in rows]; w=[r[1] for r in rows]; sl=[r[3] for r in rows]; x=[r[5] for r in rows]
    def bw(y):
        g=y[0]
        for i in range(1,len(y)):
            if y[i]<g-3: 
                t=(g-3-y[i-1])/(y[i]-y[i-1]); return f[i-1]*(f[i]/f[i-1])**t, g
    print(tag,"wide BW/gain(dB re 1ohm):",bw(w)," slow:",bw(sl)," max wide peaking dB: %.2f"%(max(w)-w[0]), " Zx at 100kHz (ohm): %.3g"%(10**(x[[i for i,v in enumerate(f) if v>1e5][0]]/20)/1))
    nr=[list(map(float,l.split())) for l in open('nw.txt') if l.strip()]
    g=10**(w[0]/20)/1e-9
    for fr in (1e4,1e5,3.16e5,1e6):
        r=min(nr,key=lambda r:abs(math.log(r[0]/fr)))
        print("   in-noise @%.3g Hz: %.0f fA/rtHz"%(fr, r[1]/g*1e15))
go("10n","IDC=10n"); go("100n","IDC=100n")
go("1u","IDC=1u")
