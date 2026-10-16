import re,subprocess,os,sys
base=open('../afe_front.spice').read()
idc=sys.argv[1]; tstop=sys.argv[2]
s=base.replace(".param IDC=10n",".param IDC="+idc)
s=re.sub(r"\.nodeset[^\n]*\n\+[^\n]*\n","",s)
s=s.replace("VPWR vdpwr 0 DC 3.3","VPWR vdpwr 0 PWL(0 0 1m 3.3)").replace("VCM  vcm   0 DC 1.65","VCM  vcm   0 PWL(0 0 1m 1.65)")
s=s.replace("Iph  anode_int x  DC {IDC} AC 1n","Iph  anode_int x  DC {IDC} AC 1n PULSE({IDC} {IDC+10p} 5 1m 1m 1 100)")
s=re.sub(r"\.control.*?\.endc",f""".control
  tran 100u {tstop} 0 100u
  wrdata long_{idc}.txt v(s_in) v(s_out) v(vc_s) v(w_out)
  quit
.endc""",s,flags=re.S)
open(f'long_{idc}.spice','w').write(s)
subprocess.run([os.environ['NGSPICE'],'-b',f'long_{idc}.spice'],capture_output=True,text=True)
print("done",idc)
