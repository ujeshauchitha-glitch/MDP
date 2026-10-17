"""Relay attack: what the receiver can and cannot do (twin, I_DC = 100 nA, m = 2 %).
Adds an amplitude-window test (accept only if the correlation is within the legitimate 0.1-99.9 % range)."""
import numpy as np
import trustsense_twin as t

f = t.FastPath(100e-9, seed=3)
zl, rl = f._collect(f.legit(), 8000)
lo, hi = np.quantile(zl, [0.001, 0.999])
print(f"legit z/sigma0: mean {zl.mean()/f.s0:.1f}, window [{lo/f.s0:.1f}, {hi/f.s0:.1f}] sigma0")
print("relay (attacker re-emits every chip with delay tau, LED blocked so only the relay light arrives):")
print("   tau      A     D1 accepts   D1+amplitude window accepts")
for tau in (20e-9, 130e-9, 260e-9, 520e-9):
    for A in (1.0, 1.5, 2.0):
        z, r = f._collect(f.relay(A, tau), 4000)
        a1 = np.mean(f.accept(z, r)); a2 = np.mean(f.accept(z, r) & (z < hi) & (z > lo))
        print(f"{tau*1e9:5.0f} ns  {A:3.1f}   {a1:8.3f}      {a2:8.3f}")
