"""Predictability of the chip sequence: LFSR vs cryptographic generator.

Berlekamp-Massey (BM) finds the shortest LFSR that reproduces an observed bit
stream; for an L-bit LFSR it needs only 2L consecutive bits and then predicts
every future bit. A cryptographic stream has linear complexity ~ n/2, so BM
learns nothing.

The 'crypto' generator here is SHA-256 in counter mode, used ONLY as an ideal
stand-in for an unpredictable keyed generator (it is not a hardware proposal).
usage: python codegen_security.py
"""
import hashlib
import numpy as np


def lfsr_bits(n, seed=0xACE1BEEF, taps=(32, 22, 2, 1)):
    """Fibonacci LFSR, x^32+x^22+x^2+x+1 (maximal length)."""
    state = seed & 0xFFFFFFFF
    out = []
    for _ in range(n):
        out.append(state & 1)
        fb = 0
        for t in taps:
            fb ^= (state >> (32 - t)) & 1
        state = (state >> 1) | (fb << 31)
    return out


def ctr_bits(n, key=b"device-secret"):
    out, ctr = [], 0
    while len(out) < n:
        h = hashlib.sha256(key + ctr.to_bytes(8, "big")).digest()
        for byte in h:
            for b in range(8):
                out.append((byte >> b) & 1)
        ctr += 1
    return out[:n]


def berlekamp_massey(s):
    """Returns (L, C) with C the connection polynomial (list of 0/1, C[0]=1)."""
    n = len(s)
    c = [1] + [0] * n
    b = [1] + [0] * n
    L, m = 0, 1
    for i in range(n):
        d = s[i]
        for j in range(1, L + 1):
            d ^= c[j] & s[i - j]
        if d == 0:
            m += 1
        elif 2 * L <= i:
            t = c[:]
            for j in range(n + 1 - m):
                c[j + m] ^= b[j]
            L, b, m = i + 1 - L, t, 1
        else:
            for j in range(n + 1 - m):
                c[j + m] ^= b[j]
            m += 1
    return L, c[:L + 1]


def predict(seen, c, L, n_future):
    s = list(seen)
    for _ in range(n_future):
        bit = 0
        for j in range(1, L + 1):
            bit ^= c[j] & s[-j]
        s.append(bit)
    return s[len(seen):]


if __name__ == "__main__":
    RATE, N = 480e3, 48
    for name, gen in (("32-bit LFSR", lfsr_bits), ("keyed hash stream (ideal CSPRNG stand-in)", ctr_bits)):
        stream = gen(20000)
        print(name)
        for n_obs in (40, 64, 96, 200, 1000):
            L, c = berlekamp_massey(stream[:n_obs])
            pred = predict(stream[:n_obs], c, L, 5000)
            acc = np.mean(np.array(pred) == np.array(stream[n_obs:n_obs + 5000]))
            print(f"  observed {n_obs:5d} chips ({n_obs/RATE*1e6:6.0f} us): linear complexity {L:4d}, next-5000-chip prediction accuracy {acc*100:6.2f} %")
    print(f"\nOne 48-chip symbol lasts {N/RATE*1e6:.0f} us; 64 chips (2L for L = 32) take {64/RATE*1e6:.0f} us.")
