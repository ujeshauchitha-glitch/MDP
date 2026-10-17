"""Fast-path verifier datapath (Amaranth HDL), one ADC sample per clock (1.92 MS/s = 4 samples/chip).

  y  : signed 8-bit ADC sample (LSB 100 uV at the output)
  c  : chip of the NEWEST sample's code (1 -> +1, 0 -> -1), same clock
  Template = two cascaded direct-form-I biquads with hard-wired Q16 coefficients (coeffs.json) fed with the chip stream;
  correlator partner chip = chip delayed by D4 samples (receiver delay).
  Per 192-sample frame: z = sum y*c, yt = sum y*t, tt = sum t*t, yy = sum y*y; then (sequential 24x24 multiplier, 3 products):
      accept = (z > eta) AND (yy*tt - yt*yt < thr*tt)        # residual energy = yy - yt^2/tt  <  thr
Bit-exact against twin/hw_model.py (see selftest)."""
import json, pathlib
from amaranth.hdl import Elaboratable, Module, Signal, Cat, Const, signed, unsigned, Array

COEF = json.loads((pathlib.Path(__file__).resolve().parent / "coeffs.json").read_text())
SB, SA = COEF["lpb"], COEF["lpa"]
FRAC, EXTRA, HPK = COEF["frac"], COEF["extra"], COEF["hpk"]
NSAMP = 192
D4 = 2
ZW, RW, TTW, YTW, YYW, PW = 15, 18, 22, 22, 18, 44
YW, TW = 6, 9          # sample width, template width (t = round(y2 / 2^EXTRA))
SW = 17                # section output word (Q8)
AW = 29                # biquad accumulator


def csd(c):
    """canonical signed-digit recoding: list of (sign, shift) with c = sum(sign * 2**shift)"""
    out, sh = [], 0
    while c != 0:
        if c & 1:
            d = 2 - (c & 3)            # +1 or -1
            out.append((d, sh)); c -= d
        c >>= 1; sh += 1
    return out


def cmul(x, c):
    """x * constant c as a shift-add network (no general multiplier)."""
    terms = csd(abs(c))
    e = 0
    for sgn, sh in terms:
        e = e + (sgn * (-1 if c < 0 else 1)) * (x << sh)
    return e if terms else x * 0


class LPBiquad(Elaboratable):
    """Low-pass biquad fed by the chip bit: y[n] = round((b0 x[n] + b1 x[n-1] + b2 x[n-2] - a1 y[n-1] - a2 y[n-2]) / 2^FRAC),
    x = +/-2^EXTRA so the b*x terms are selected constants; a1, a2 are shift-add networks."""
    def __init__(self):
        self.en = Signal()
        self.chipbit = Signal()
        self.y = Signal(signed(SW))

    def elaborate(self, platform):
        from amaranth.hdl import Mux
        m = Module()
        b0, b1, b2 = SB
        a1, a2 = SA
        y1 = Signal(signed(SW), reset_less=True)
        y2 = Signal(signed(SW), reset_less=True)
        c1 = Signal(reset_less=True)
        c2 = Signal(reset_less=True)
        acc = Signal(signed(AW))
        ct = lambda bit, b: Mux(bit, b << EXTRA, -(b << EXTRA))
        m.d.comb += acc.eq(ct(self.chipbit, b0) + ct(c1, b1) + ct(c2, b2) - cmul(y1, a1) - cmul(y2, a2) + (1 << (FRAC - 1)))
        m.d.comb += self.y.eq(acc >> FRAC)
        with m.If(self.en):
            m.d.sync += [c1.eq(self.chipbit), c2.eq(c1), y1.eq(self.y), y2.eq(y1)]
        return m


class HPStage(Elaboratable):
    """First-order high-pass: h[n] = x[n] - x[n-1] + h[n-1] - round(h[n-1] / 2^HPK) (corner 2^-HPK per sample)."""
    def __init__(self):
        self.x = Signal(signed(SW))
        self.en = Signal()
        self.h = Signal(signed(SW))

    def elaborate(self, platform):
        m = Module()
        xp = Signal(signed(SW), reset_less=True)
        hp = Signal(signed(SW), reset_less=True)
        m.d.comb += self.h.eq(self.x - xp + hp - ((hp + (1 << (HPK - 1))) >> HPK))
        with m.If(self.en):
            m.d.sync += [xp.eq(self.x), hp.eq(self.h)]
        return m


class Verifier(Elaboratable):
    def __init__(self):
        self.y = Signal(signed(YW))
        self.c = Signal()                       # chip bit
        self.en = Signal()                      # sample strobe (clock enable)
        self.frame_start = Signal()             # first sample of a frame window (aligned with y)
        self.eta = Signal(signed(ZW))           # correlation threshold (same units as z)
        self.thr = Signal(RW)                   # residual threshold
        self.done = Signal()                    # pulses when a frame decision is ready
        self.accept = Signal()
        self.z_out = Signal(signed(ZW))
        self.t_dbg = Signal(signed(TW))         # template sample (for verification)

    def elaborate(self, platform):
        m = Module()
        # ---- template filter chain ---------------------------------------------------------------
        lp = LPBiquad(); hp1 = HPStage(); hp2 = HPStage()
        m.submodules += [lp, hp1, hp2]
        m.d.comb += [lp.chipbit.eq(self.c), lp.en.eq(self.en), hp1.x.eq(lp.y), hp1.en.eq(self.en), hp2.x.eq(hp1.h), hp2.en.eq(self.en)]
        t = Signal(signed(TW))
        m.d.comb += t.eq((hp2.h + (1 << (EXTRA - 1))) >> EXTRA)
        m.d.comb += self.t_dbg.eq(t)
        # ---- delayed chip for the correlator ----------------------------------------------------
        dly = Signal(D4, reset_less=True)
        with m.If(self.en):
            m.d.sync += dly.eq(Cat(self.c, dly[:D4 - 1]))
        cd = dly[D4 - 1]
        # ---- frame accumulators ---------------------------------------------------------------------
        cnt = Signal(8, reset_less=True)
        run = Signal(reset_less=True)
        z = Signal(signed(ZW), reset_less=True)
        yt = Signal(signed(YTW), reset_less=True)
        tt = Signal(unsigned(TTW), reset_less=True)
        yy = Signal(unsigned(YYW), reset_less=True)
        zs = Signal(signed(ZW), reset_less=True)
        yts = Signal(signed(YTW), reset_less=True)
        tts = Signal(unsigned(TTW), reset_less=True)
        yys = Signal(unsigned(YYW), reset_less=True)
        last = Signal()
        m.d.comb += last.eq(run & (cnt == NSAMP - 1) & self.en)
        sample_in = self.en & (run | self.frame_start)
        z0 = Mux_zero(self.frame_start, z)
        yt0 = Mux_zero(self.frame_start, yt)
        tt0 = Mux_zero(self.frame_start, tt)
        yy0 = Mux_zero(self.frame_start, yy)
        with m.If(sample_in):
            m.d.sync += [
                z.eq(z0 + Mux_sign(cd, self.y)),
                yt.eq(yt0 + self.y * t),
                tt.eq(tt0 + t * t),
                yy.eq(yy0 + self.y * self.y),
                cnt.eq(Mux_zero(self.frame_start, cnt) + 1),
            ]
        with m.If(self.frame_start & self.en):
            m.d.sync += run.eq(1)
        with m.Elif(last):
            m.d.sync += run.eq(0)
        # ---- end of frame: snapshot and sequential compare ----------------------------------------
        st = Signal(3, reset_less=True)         # 0 idle, 1 yy*tt, 2 yt*yt, 3 thr*tt, 4 compare
        mcnt = Signal(5, reset_less=True)
        mplier = Signal(TTW, reset_less=True)
        mcand = Signal(PW, reset_less=True)
        prod = Signal(PW, reset_less=True)
        p1 = Signal(PW, reset_less=True)
        p2 = Signal(PW, reset_less=True)
        zok = Signal(reset_less=True)
        self.state = st
        m.d.comb += self.done.eq(0)
        with m.If(last):
            # accumulators complete after this sample: capture the updated values next cycle
            m.d.sync += st.eq(7)
        with m.Elif(st == 7):
            m.d.sync += [zs.eq(z), yts.eq(yt), tts.eq(tt), yys.eq(yy), st.eq(1), mcnt.eq(0), prod.eq(0),
                         mplier.eq(yy), mcand.eq(tt), zok.eq(z > self.eta)]
        with m.Elif(st == 1):                       # shift-add: prod = yy * tt
            m.d.sync += [prod.eq(prod + Mux_bit(mplier[0], mcand)), mcand.eq(mcand << 1), mplier.eq(mplier >> 1), mcnt.eq(mcnt + 1)]
            with m.If(mcnt == (TTW - 1)):
                m.d.sync += [st.eq(2), mcnt.eq(0)]
        with m.Elif(st == 2):
            m.d.sync += [p1.eq(prod), prod.eq(0), mplier.eq(Abs24(yts)), mcand.eq(Abs24(yts)), st.eq(3), mcnt.eq(0)]
        with m.Elif(st == 3):                       # prod = yt*yt
            m.d.sync += [prod.eq(prod + Mux_bit(mplier[0], mcand)), mcand.eq(mcand << 1), mplier.eq(mplier >> 1), mcnt.eq(mcnt + 1)]
            with m.If(mcnt == (TTW - 1)):
                m.d.sync += [st.eq(4), mcnt.eq(0), p2.eq(0)]
        with m.Elif(st == 4):
            m.d.sync += [p2.eq(prod), prod.eq(0), mplier.eq(self.thr), mcand.eq(tts), st.eq(5), mcnt.eq(0)]
        with m.Elif(st == 5):                       # prod = thr*tt
            m.d.sync += [prod.eq(prod + Mux_bit(mplier[0], mcand)), mcand.eq(mcand << 1), mplier.eq(mplier >> 1), mcnt.eq(mcnt + 1)]
            with m.If(mcnt == (TTW - 1)):
                m.d.sync += [st.eq(6), mcnt.eq(0)]
        with m.Elif(st == 6):
            m.d.comb += self.done.eq(1)
            m.d.sync += st.eq(0)
        m.d.comb += self.accept.eq(zok & ((p1 - p2) < prod))
        m.d.comb += self.z_out.eq(zs)
        return m


# small helpers (kept as functions so the arithmetic reads like the model)
def Mux_chip(c):
    from amaranth.hdl import Mux
    return Mux(c, Const(1 << EXTRA, signed(EXTRA + 2)), Const(-(1 << EXTRA), signed(EXTRA + 2)))


def Mux_zero(sel, v):
    from amaranth.hdl import Mux
    return Mux(sel, 0, v)


def Mux_sign(c, y):
    from amaranth.hdl import Mux
    return Mux(c, y, -y)


def Mux_bit(b, v):
    from amaranth.hdl import Mux
    return Mux(b, v, 0)


def Abs24(v):
    from amaranth.hdl import Mux
    return Mux(v < 0, -v, v)[:YTW]
