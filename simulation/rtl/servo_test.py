"""Closed-loop check: servo RTL (Amaranth sim) + the SPICE-fitted plants of servo/servo_loop.py (noise-free) with a 10-bit ADC model."""
import sys, pathlib, math
import numpy as np
from amaranth.sim import Simulator
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "servo"))
import servo_loop as sl
from servo_hw import Servo

def run(idc_amp, t_end=0.6, ppg_pct=0.0):
    plants = {}
    for i, nm in enumerate(sl.ORDER):
        dd, tag, _ = sl.RANGES[nm]
        (zz, ff, qq), _ = sl.fit_plant(tag, dd)
        plants[i] = (zz, sl.make_plant(zz, ff, qq))
    dut = Servo()
    n = int(t_end / sl.DT)
    log = dict(t_lock=None, rng_changes=[], final_code=None, final_rng=None, maxerr=0.0, resid_mV=None)
    rngs = np.random.default_rng(3)
    sim = Simulator(dut); sim.add_clock(1e-5)
    outs = []

    async def tb(ctx):
        x = np.zeros(2); cur = 2
        z0, (Ad, Bd, Cd) = plants[cur]
        lsb = sl.ADC_FS / 2 ** sl.N_ADC
        for k in range(n):
            r = ctx.get(dut.rng)
            if r != cur:
                cur = r; z0, (Ad, Bd, Cd) = plants[cur]; x = np.zeros(2); log["rng_changes"].append((k * sl.DT, r))
            d = ctx.get(dut.dac) * sl.LSB_C
            ip = idc_amp + (ppg_pct / 100 * idc_amp * math.sin(2 * math.pi * 1.2 * k * sl.DT) if ppg_pct else 0.0)
            x = Ad @ x + Bd * (d - ip)
            y = float(Cd @ x)
            v = min(max(y, -sl.CLIP), sl.CLIP)
            q = int(np.clip(np.round(v / lsb + rngs.standard_normal() * sl.ADC_NOISE), -512, 511))
            ctx.set(dut.e, q)
            await ctx.tick()
            if ctx.get(dut.locked) and log["t_lock"] is None:
                log["t_lock"] = k * sl.DT
            outs.append((v, ctx.get(dut.code_dbg)))
            if k > n - 2000:
                log["maxerr"] = max(log["maxerr"], abs(v))
        log["final_code"] = ctx.get(dut.code_dbg); log["final_rng"] = ctx.get(dut.rng)
    sim.add_testbench(tb)
    sim.run()
    return log

if __name__ == "__main__":
    for lab, amp in (("5n", 5e-9), ("30n", 30e-9), ("100n", 100e-9), ("300n", 300e-9), ("1u", 1e-6)):
        L = run(amp)
        exp = amp / sl.LSB_C
        print(f"I_DC {lab:4s}: lock at {('%.1f ms' % (L['t_lock']*1e3)) if L['t_lock'] else 'NO LOCK'}, final range {L['final_rng']} (changes {[(round(t*1e3), r) for t, r in L['rng_changes']]}), "
              f"DAC code {L['final_code']} (ideal {exp:.0f}), |out-VCM| over last 20 ms max {L['maxerr']*1e3:.1f} mV", flush=True)
