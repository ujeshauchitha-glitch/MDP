"""Key / IV / synchronisation protocol checks on the twin (I_DC = 100 nA, m = 2 %, full D1 detector).

Protocol (specification, section 46 of afe-architecture.md):
  * 80-bit device key in OTP; per-session 80-bit IV = 48-bit non-volatile monotonic session counter || 32 random bits (ring-oscillator TRNG).
  * the SAME on-chip Trivium feeds the LED driver and the verifier, so there is no inter-chip frame synchronisation; the verifier only needs the fixed
    receive delay (a sample count) -> tolerance tested below.
Tests: (1) genuine session, (2) replay of a recorded earlier session (new IV), (3) replay when the IV is wrongly reused, (4) wrong key,
       (5) receive-delay error of +/-k samples (1.92 MS/s), (6) TRNG-free fallback (counter only)."""
import numpy as np
import trustsense_twin as t
from trustsense_twin import cm, N, NSYM, NS
from codegen import Trivium

f = t.FastPath(100e-9, seed=77)
def session_codes(key, iv, nframes):
    tv = Trivium(key, iv)
    chips = tv.chips((nframes + NSYM - 1) * N)
    return np.stack([chips[i * N:(i + NSYM) * N].reshape(NSYM, N) for i in range(nframes)])
KEY = bytes(range(10)); KEY2 = bytes(range(10, 20))
def iv_of(counter, rnd): return counter.to_bytes(6, "little") + rnd.to_bytes(4, "little")
NF = 400                                    # frames per test
A = session_codes(KEY, iv_of(1, 0x1234ABCD), NF)         # recorded session
B = session_codes(KEY, iv_of(2, 0x9E3779B9), NF)         # later session, new IV
Bsame = session_codes(KEY, iv_of(1, 0x1234ABCD), NF)     # IV reuse
C = session_codes(KEY2, iv_of(2, 0x9E3779B9), NF)        # other device
def rate(true_codes, tx_codes, delay=0):
    """verifier expects true_codes; the optical signal carries tx_codes (genuine: same). delay shifts the receive window (samples @16/chip grid)."""
    light = lambda c, tx=tx_codes: f.m * f.i_dc * cm.upsample(tx[:c.shape[0]])
    old_win = f.win
    if delay:
        f.win = slice(old_win.start + delay, old_win.stop + delay)
    z, r = f.frames(true_codes, light)
    f.win = old_win
    return np.mean(f.accept(z, r)), np.mean(z > f.eta)
out = []
def line(s): print(s, flush=True); out.append(s)
line("test                                            D1 accept   corr-only accept")
for name, (tc, tx) in {"genuine (verifier and LED use session B)": (B, B),
                       "replay of recorded session A against session B": (B, A),
                       "replay with REUSED IV (same keystream)": (Bsame, A),
                       "attacker device with another key": (B, C)}.items():
    d1, d0 = rate(tc, tx); line(f"{name:48s} {d1:9.3f}   {d0:9.3f}")
line("")
line("receive-delay error (samples at 16/chip = 1/8 chip steps; 4 samples/chip hardware step = 4 of these)")
for dl in (-32, -16, -8, 0, 8, 16, 32, 64):
    d1, d0 = rate(B, B, dl); line(f"delay error {dl:+3d} (={dl/16:+.2f} chip)               genuine D1 accept {d1:6.3f}  corr-only {d0:6.3f}")
open("protocol_results.txt", "w").write("\n".join(out) + "\n")
