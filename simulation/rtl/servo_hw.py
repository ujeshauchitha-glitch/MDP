"""Digital DC-cancellation servo with auto-ranging (Amaranth HDL), clocked at 100 kHz (= the sigma-delta rate).

Mirrors simulation/servo/servo_loop.py (float model) in integers:
  every 50th clock (2 kS/s)  : ADC sample `e` (signed 10 bit, >0 = too much cancel current)
    ACQ   : 12-step SAR on the DAC code (3 wait samples after each decision), then TRACK
    TRACK : integrator on a 36-bit accumulator (12 integer + 24 fraction bits), gain x64 when |e| > 20 LSB and a further
            x16 while the 2 s mean |m| > 31 LSB; re-acquire if |e| > 307 LSB for more than 10 samples
    range : 100 ms after lock the DAC code (= the DC photocurrent in 0.5 nA units) selects the TIA range (0 = 1G, 1 = 100M, 2 = 10M)
  every clock: first-order sigma-delta from the fractional part -> `dac` (12 bit)
Integrator step per ADC LSB per sample = ki * 0.977 mV / (Z0 * 0.5 nA) * 2^24 = 5 / 50 / 504 (units of 2^-24 code) for 1G / 100M / 10M."""
from amaranth.hdl import Elaboratable, Module, Signal, Mux, signed

NDAC = 12
FRAC = 24
ACC_W = NDAC + FRAC
SAR_WAIT = 3
KINC = (5, 50, 504)
T_BIG, T_MEAN, T_REACQ = 20, 31, 307
RANGE_THR = (25, 250)           # DAC codes (0.5 nA each): 12.5 nA and 125 nA
RANGE_WAIT = 200                # ADC samples after lock (100 ms)
LOCK_BAND = 5                   # |e| <= 5 LSB counts as locked
MEAN_SH = 12                    # 2 s mean: m += (e - m) / 2^12 (kept with 12 fraction bits)


class Servo(Elaboratable):
    def __init__(self):
        self.e = Signal(signed(10))       # ADC error sample, sampled when `sample_tick` is high
        self.dac = Signal(NDAC)           # sigma-delta DAC code
        self.rng = Signal(2)              # selected TIA range
        self.sample_tick = Signal()       # 2 kHz strobe (ADC convert / read request)
        self.locked = Signal()
        self.code_dbg = Signal(NDAC)

    def elaborate(self, platform):
        m = Module()
        pre = Signal(6, reset_less=True)
        tick = Signal()
        m.d.comb += tick.eq(pre == 49)
        m.d.sync += pre.eq(Mux(tick, 0, pre + 1))
        m.d.comb += self.sample_tick.eq(tick)

        acc = Signal(ACC_W)
        acq = Signal(reset=1)
        bit = Signal(4, reset=NDAC - 1)        # 15 = finished (-1)
        wait = Signal(3)
        code = Signal(NDAC)
        mean = Signal(signed(24))                       # Q12 mean of e
        big = Signal(4)
        rsel = Signal(2, reset=2)
        lockc = Signal(8)
        locked = Signal()
        ranged = Signal()
        sd = Signal(FRAC)

        e = self.e
        ea = Signal(signed(11))
        m.d.comb += ea.eq(Mux(e < 0, -e, e))
        ma = Signal(signed(25))
        m.d.comb += ma.eq(Mux(mean < 0, -mean, mean))
        sh = Signal(4)
        m.d.comb += sh.eq(Mux(ea > T_BIG, 6, 0) + Mux(ma > (T_MEAN << 12), 4, 0))
        kinc = Signal(10)
        m.d.comb += kinc.eq(Mux(rsel == 0, KINC[0], Mux(rsel == 1, KINC[1], KINC[2])))
        step = Signal(signed(40))
        m.d.comb += step.eq(-(e * kinc) << sh)
        nacc = Signal(signed(ACC_W + 3))
        m.d.comb += nacc.eq(acc + step)

        with m.If(tick):
            with m.If(acq):
                with m.If(wait != 0):
                    m.d.sync += wait.eq(wait - 1)
                with m.Else():
                    # trial bit (bit+1) is kept only if the output is not above VCM
                    keep = Signal(NDAC)
                    clr = Signal(4)
                    m.d.comb += clr.eq(bit + 1)
                    m.d.comb += keep.eq(Mux((code != 0) & (e > 0), code & ~(1 << clr), code))
                    with m.If(bit == 15):
                        m.d.sync += [acq.eq(0), acc.eq(keep << FRAC), code.eq(keep), mean.eq(0), lockc.eq(0)]
                    with m.Else():
                        newc = keep | (1 << bit)
                        m.d.sync += [code.eq(newc), acc.eq(newc << FRAC), bit.eq(bit - 1), wait.eq(SAR_WAIT)]
            with m.Else():
                # TRACK
                m.d.sync += mean.eq(mean + (((e << 12) - mean) >> MEAN_SH))
                with m.If(nacc < 0):
                    m.d.sync += acc.eq(0)
                with m.Elif(nacc > ((1 << ACC_W) - 1)):
                    m.d.sync += acc.eq((1 << ACC_W) - 1)
                with m.Else():
                    m.d.sync += acc.eq(nacc)
                # re-acquisition
                with m.If(ea > T_REACQ):
                    with m.If(big == 10):
                        m.d.sync += [acq.eq(1), bit.eq(NDAC - 1), wait.eq(0), code.eq(0), acc.eq(0), big.eq(0),
                                     locked.eq(0), lockc.eq(0), ranged.eq(0), rsel.eq(2)]
                    with m.Else():
                        m.d.sync += big.eq(big + 1)
                with m.Else():
                    m.d.sync += big.eq(0)
                # lock detection and range selection
                with m.If(~locked & (ea <= LOCK_BAND)):
                    m.d.sync += locked.eq(1)
                with m.If(locked & ~ranged):
                    m.d.sync += lockc.eq(lockc + 1)
                    with m.If(lockc == RANGE_WAIT):
                        m.d.sync += ranged.eq(1)
                        want = Signal(2)
                        m.d.comb += want.eq(Mux(acc[FRAC:] <= RANGE_THR[0], 0, Mux(acc[FRAC:] <= RANGE_THR[1], 1, 2)))
                        with m.If(want != rsel):
                            m.d.sync += [rsel.eq(want), mean.eq(0)]
        # sigma-delta on every clock
        total = Signal(FRAC + 1)
        m.d.comb += total.eq(sd + acc[:FRAC])
        base = Signal(NDAC + 1)
        m.d.comb += base.eq(acc[FRAC:] + total[FRAC])
        m.d.sync += sd.eq(total[:FRAC])
        m.d.comb += [self.dac.eq(Mux(base > (1 << NDAC) - 1, (1 << NDAC) - 1, base)), self.rng.eq(rsel),
                     self.locked.eq(locked), self.code_dbg.eq(acc[FRAC:])]
        return m
