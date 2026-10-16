import re,subprocess,math
D='C:/Users/ujesh/Documents/MDP/simulation/spice/'
def pm(name,f1,f2):
    s=open(D+name).read().replace('.include "sky130_min.lib"','.include "'+D+'build/sky130_min.lib"')
    s=re.sub(r"Iph( .*?) AC \S+",r"Iph\1 AC 0",s,count=1) if False else s.replace("AC 1p PULSE","AC 0 PULSE").replace("AC 1n PULSE","AC 0 PULSE")
    # reroute feedback elements' tia_out end to fb_node
    lines=[]
    for l in s.splitlines():
        if re.match(r"^(XMPR2|Cf|Rf)\s",l): l=l.replace("tia_out","fb_node")
        lines.append(l)
    s="\n".join(lines)
    s=re.sub(r"\.control.*?\.endc",f""".control
  op
  ac dec 40 {f1} {f2}
  let T = -v(tia_out)/v(fb_node)
  let mag_db = db(T)
  let ph = 180/pi*cph(T)
  wrdata pm_{name}.txt mag_db ph
  quit
.endc""",s,flags=re.S)
    s=s.replace("Cload    tia_out","Vinj     fb_node  tia_out  DC 0 AC 1\nCload    tia_out",1)
    open('pm.spice','w').write(s)
    subprocess.run(['bash','-c','cd /c/Users/ujesh/eda/run && ../ngspice/Spice64/bin/ngspice_con.exe -b pm.spice >pm.log 2>&1'])
    rows=[l.split() for l in open(f'pm_{name}.txt') if l.strip()]
    pts=[(float(r[0]),float(r[1]),float(r[3])) for r in rows]
    print(name,"DC loop gain %.1f dB at %.3g Hz"%(pts[0][1],pts[0][0]))
    for a,b in zip(pts,pts[1:]):
        if a[1]>0>=b[1]:
            t=a[1]/(a[1]-b[1]); f=a[0]*(b[0]/a[0])**t; ph=a[2]+t*(b[2]-a[2])
            print("  unity-gain f = %.4g Hz, phase = %.1f deg, PM = %.1f deg"%(f,ph,180+ph if ph<=0 else ph-180)); break
    else: print("  no unity crossing; last",pts[-1])
pm('tia.spice',1,100e6)
pm('tia_wide.spice',100,1e9)
