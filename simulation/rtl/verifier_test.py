"""Bit-exact check of verifier_hw.Verifier against the integer model in twin/hw_model.py."""
import sys, pathlib
import numpy as np
from amaranth.sim import Simulator
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "twin"))
import hw_model as hm
from verifier_hw import Verifier, NSAMP, D4

def run(seed=1, nframes=6):
    rng = np.random.default_rng(seed)
    n = NSAMP * nframes
    chips = rng.choice([-1, 1], size=n)
    tmpl_f = hm.template(chips[None, :].astype(float))[0]
    t_ref = np.floor(tmpl_f + 0.5).astype(int)
    # y: scaled template plus noise (so z, yt are non-trivial), occasionally a different code (attack-like) in later frames
    y = np.clip(np.round(0.4 * t_ref + rng.normal(0, 30, n)), -128, 127).astype(int)
    dly = np.r_[-np.ones(D4, int), chips][:n]               # chip partner for the correlator = chip delayed by D4
    eta = 1500
    rs = []
    for k in range(nframes):
        s_ = slice(k * NSAMP, (k + 1) * NSAMP)
        yt_ = (y[s_] * t_ref[s_]).sum(); tt_ = (t_ref[s_] ** 2).sum(); yy_ = (y[s_] ** 2).sum()
        rs.append((yy_ * tt_ - yt_ * yt_) / tt_)
    thr = int(np.median(rs))
    exp = []
    for k in range(nframes):
        s = slice(k * NSAMP, (k + 1) * NSAMP)
        z = int((y[s] * dly[s]).sum()); yt = int((y[s] * t_ref[s]).sum()); tt = int((t_ref[s] ** 2).sum()); yy = int((y[s] ** 2).sum())
        exp.append((z, yt, tt, yy, int(z > eta and (yy * tt - yt * yt) < thr * tt)))
    dut = Verifier()
    got = []
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    async def tb(ctx):
        ctx.set(dut.en, 1); ctx.set(dut.eta, eta); ctx.set(dut.thr, thr)
        for i in range(n + 400):
            ctx.set(dut.c, int(chips[i] > 0) if i < n else 0)
            ctx.set(dut.y, int(y[i]) if i < n else 0)
            ctx.set(dut.frame_start, int(i % NSAMP == 0 and i < n))
            await ctx.tick()
            if ctx.get(dut.done):
                got.append((ctx.get(dut.z_out), ctx.get(dut.accept)))
    sim.add_testbench(tb)
    sim.run()
    ok = True
    for k, (e, g) in enumerate(zip(exp, got)):
        match = (e[0] == g[0]) and (e[4] == g[1])
        ok &= match
        print(f"frame {k}: z model {e[0]:7d} rtl {g[0]:7d}  accept model {e[4]} rtl {g[1]}  {'OK' if match else 'MISMATCH'}")
    print("frames decided:", len(got), "of", nframes)
    return ok and len(got) == nframes

if __name__ == "__main__":
    a = run(1)
    print("VERIFIER RTL BIT-EXACT:" , a)
    raise SystemExit(0 if a else 1)
