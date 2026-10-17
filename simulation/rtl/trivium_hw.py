"""Trivium keystream generator in Amaranth HDL (one chip bit per clock after a 1152-clock warm-up).
Registers: 288-bit state + 80-bit key + 80-bit IV (key/IV held so a new session/frame counter can restart the cipher)."""
from amaranth.hdl import Elaboratable, Module, Signal, Cat, Const, Mux, Array
from amaranth.sim import Simulator


class Trivium(Elaboratable):
    """State is one 288-bit shift chain; it is loaded SERIALLY (288 cycles) from the key/IV rings, then 1152 warm-up cycles.
    Serial load keeps the state flops free of parallel-load multiplexers (3 muxes in total)."""
    def __init__(self):
        self.key = Signal(80)          # static key (e.g. from OTP / fuses); IV = session counter
        self.iv = Signal(80)
        self.start = Signal()          # pulse: begin load + warm-up
        self.en = Signal()             # advance one chip (chip clock enable; clock-gated in silicon)
        self.ready = Signal()          # warm-up done, `chip` valid
        self.chip = Signal()           # current keystream bit (1 -> +1, 0 -> -1)

    def elaborate(self, platform):
        m = Module()
        s = Signal(288, reset_less=True)
        cnt = Signal(11, reset_less=True)
        busy = Signal(reset_less=True)
        loading = Signal(reset_less=True)
        t1 = s[65] ^ s[92]
        t2 = s[161] ^ s[176]
        t3 = s[242] ^ s[287]
        z = t1 ^ t2 ^ t3
        n1 = t1 ^ (s[90] & s[91]) ^ s[170]
        n2 = t2 ^ (s[174] & s[175]) ^ s[263]
        n3 = t3 ^ (s[285] & s[286]) ^ s[68]
        # serial bit to shift in while loading (order: three 1s, 108+4 zeros, IV[79..0], 13 zeros, key[79..0])
        c = cnt
        ser = Signal()
        with m.If(c < 3):
            m.d.comb += ser.eq(1)
        with m.Elif(c < 3 + 108 + 4):
            m.d.comb += ser.eq(0)
        with m.Elif(c < 3 + 108 + 4 + 80):
            m.d.comb += ser.eq(Array(self.iv[i] for i in range(80))[79 - (c - 115)[:7]])
        with m.Elif(c < 3 + 108 + 4 + 80 + 13):
            m.d.comb += ser.eq(0)
        with m.Else():
            m.d.comb += ser.eq(Array(self.key[i] for i in range(80))[79 - (c - 208)[:7]])
        run = busy | self.en
        # shifting chain; the three segment heads take the cipher feedback only when not loading
        chain = Cat(Mux(loading, ser, n3), s[0:92],
                    Mux(loading, s[92], n1), s[93:176],
                    Mux(loading, s[176], n2), s[177:287])
        with m.If(run):
            m.d.sync += s.eq(chain)         # single enable for all 288 state flops (one clock gate in silicon)
        with m.If(self.start):
            m.d.sync += [cnt.eq(0), busy.eq(1), loading.eq(1)]
        with m.Elif(busy):
            m.d.sync += cnt.eq(cnt + 1)
            with m.If(loading):
                with m.If(c == 287):
                    m.d.sync += [loading.eq(0), cnt.eq(0)]
            with m.Else():
                with m.If(cnt == 4 * 288 - 1):
                    m.d.sync += busy.eq(0)
        m.d.comb += [self.chip.eq(z), self.ready.eq(~busy)]
        return m


def _bits(b, n):
    return [(b[i // 8] >> (i % 8)) & 1 for i in range(n)]


def selftest():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "twin"))
    from codegen import Trivium as Ref
    key = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0, 0x11, 0x22]); iv = bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    ref = Ref(key, iv).bits(500)
    dut = Trivium()
    out = []
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    async def tb(ctx):
        kv = sum(b << i for i, b in enumerate(_bits(key, 80)))
        iv_ = sum(b << i for i, b in enumerate(_bits(iv, 80)))
        ctx.set(dut.key, kv); ctx.set(dut.iv, iv_)
        ctx.set(dut.start, 1)
        await ctx.tick()
        ctx.set(dut.start, 0)
        while not ctx.get(dut.ready):
            await ctx.tick()
        ctx.set(dut.en, 1)
        for _ in range(500):
            out.append(ctx.get(dut.chip))
            await ctx.tick()
    sim.add_testbench(tb)
    sim.run()
    ok = list(ref) == out
    print("Trivium RTL vs Python reference (500 chips):", "MATCH" if ok else "MISMATCH")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
