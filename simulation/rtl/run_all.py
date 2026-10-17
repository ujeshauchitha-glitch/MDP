"""Run all RTL self-tests and synthesise every block; write synth_results.txt."""
import synth
from trivium_hw import Trivium, selftest as t_self
from verifier_hw import Verifier
from servo_hw import Servo
import verifier_test
ok = t_self() and verifier_test.run(1) and verifier_test.run(2)
lines = [f"self-tests (Trivium vs reference, verifier bit-exact vs fixed-point model): {'PASS' if ok else 'FAIL'}"]
for name, d, ports in (("trivium", Trivium(), None), ("verifier", Verifier(), None), ("servo", Servo(), None)):
    ps = {"trivium": lambda d: [d.key, d.iv, d.start, d.en, d.ready, d.chip],
          "verifier": lambda d: [d.y, d.c, d.en, d.frame_start, d.eta, d.thr, d.done, d.accept, d.z_out, d.t_dbg],
          "servo": lambda d: [d.e, d.dac, d.rng, d.sample_tick, d.locked, d.code_dbg]}[name](d)
    r = synth.synth(d, ps, name)
    lines.append(f"{name:9s} {r['flops']:4d} FF  {r['gates']:5d} gates  {r['area_um2']:8.0f} um^2 (cell area, sky130_fd_sc_hd estimate)")
open("synth_results.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
