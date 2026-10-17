"""Chip-code generator for the twin: Trivium (eSTREAM hardware portfolio, 288-bit state,
80-bit key + 80-bit IV, 1 keystream bit per clock = 1 chip per chip clock).

Why Trivium: smallest standard keyed stream cipher (288 flip-flops, ~3 AND + 11 XOR per clock),
no known practical attack on the full cipher, one bit per clock matches one chip per 2.08 us clock.
A frame = one 48-chip symbol; the IV carries the frame counter (80 bits) so any frame can be
re-derived after the 1152-clock warm-up, or the cipher is simply run continuously (the
twin uses the continuous mode: 1 bit per chip, no re-keying per frame).
"""
import numpy as np


def _bits(b, n):
    return [(b[i // 8] >> (i % 8)) & 1 for i in range(n)]


class Trivium:
    def __init__(self, key: bytes, iv: bytes):
        k, v = _bits(key, 80), _bits(iv, 80)
        # state s[1..288] stored 0-based
        s = k + [0] * 13 + v + [0] * 4 + [0] * 108 + [1, 1, 1]
        self.s = s
        for _ in range(4 * 288):
            self._step()

    def _step(self):
        s = self.s
        t1 = s[65] ^ s[92]
        t2 = s[161] ^ s[176]
        t3 = s[242] ^ s[287]
        z = t1 ^ t2 ^ t3
        t1 ^= (s[90] & s[91]) ^ s[170]
        t2 ^= (s[174] & s[175]) ^ s[263]
        t3 ^= (s[285] & s[286]) ^ s[68]
        self.s = [t3] + s[0:92] + [t1] + s[93:176] + [t2] + s[177:287]
        return z

    def bits(self, n):
        return np.array([self._step() for _ in range(n)], dtype=np.uint8)

    def chips(self, n):
        """+/-1 chips."""
        return 2.0 * self.bits(n) - 1.0


def keystream_bytes(key, iv, n):
    t = Trivium(key, iv)
    out = bytearray()
    for _ in range(n):
        x = 0
        for i in range(8):
            x |= t._step() << i
        out.append(x)
    return bytes(out)


if __name__ == "__main__":
    # eSTREAM Trivium test vector: key = 0, iv = 0 -> FBE0BF265859051B517A2E4E239FC97F...
    ks = keystream_bytes(bytes(10), bytes(10), 8)
    print(ks.hex().upper(), "OK" if ks.hex().upper() == "FBE0BF265859051B" else "MISMATCH")
