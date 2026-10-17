"""End-to-end scenarios on the twin: genuine skin contact and several attacks (Trivium chip stream)."""
import trustsense_twin as t

I = 100e-9
tw = t.TrustSenseTwin(I, m=0.02)
print(f"twin at I_DC = 100 nA, m = 2 %: eta = {tw.fast.eta*1e6:.1f} uV (sigma0 {tw.fast.s0*1e6:.2f} uV), residual threshold {tw.fast.r_thr:.2e}")
cases = [("genuine", None), ("blind spoof, 1x amplitude", ("blind", 1.0)), ("blind spoof, 30x amplitude (loud)", ("blind", 30.0)),
         ("attacker knows 90 % of chips", ("partial", 1.0, 0.9)), ("relay, 130 ns", ("relay", 1.0, 130e-9)),
         ("relay, 520 ns", ("relay", 1.0, 520e-9))]
for name, a in cases:
    r = tw.session(nframes=60, attack=a, tstop=3.0)
    print(f"{name:36s} frames accepted {r['accepted']:3d}/{r['frames']}  mean z/sigma {r['mean_z_over_sigma']:6.1f}  -> {r['verdict']}   "
          f"(slow: range {r['slow']['range']}, lock {r['slow']['lock_s']*1e3:.0f} ms, PPG gain {r['slow']['ppg_gain']:.3f})")
