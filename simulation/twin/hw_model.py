"""Bit-accurate Python model of the hardware verifier (correlator + SOS-IIR template + residual accumulators) and its
detection performance versus the twin's floating-point D1.  Writes coefficients for the RTL (rtl/coeffs.json)."""
import json, pathlib, numpy as np
from scipy.signal import lfilter, tf2sos, sosfilt
import trustsense_twin as t
from trustsense_twin import cm, NS, N, L
import iir_residual_fit as fit   # b, a, f

f = fit.f
STEP = 4
FRAC = 12                                  # coefficient fractional bits
TB = 12                                    # template word: t = round(t_float * 2**TB_SC)
Y_LSB = 100e-6; Y_BITS = 8                 # sample quantisation (signed 8 bit, +/-12.7 mV range)
sos = tf2sos(fit.b, fit.a)
LPF = sos[0].copy()                        # low-pass biquad of the channel fit (section 1); the high-pass part is two shift-based stages
FRAC = 12                                  # coefficient fractional bits of the (well-damped) low-pass biquad
EXTRA = 8                                  # fractional bits kept in the state
HPK = 8                                    # high-pass corner = 2^-HPK per sample
def _float_template(c4, b):
    x = sosfilt(np.r_[b, LPF[3:]][None, :], c4, axis=1)
    for _ in range(2):
        x = lfilter([1.0, -1.0], [1.0, -(1 - 2.0 ** -HPK)], x, axis=1)
    return x
from scipy.signal import lfilter
_rng = np.random.default_rng(5)
_c = _rng.choice([-1.0, 1.0], size=(50, 1000))
_peak = np.abs(_float_template(_c, LPF[:3]))[:, 300:].max()
BSC = LPF[:3] * (100.0 / _peak)             # scaled numerator so that |t| peaks near 100
SB = np.round(BSC * 2 ** FRAC).astype(np.int64)
SA = np.round(LPF[4:] * 2 ** FRAC).astype(np.int64)
print("LP biquad integer b:", SB.tolist(), " a1,a2:", SA.tolist())
def template(c4):
    """Integer template: LP biquad (Q12 coefficients, 8 fractional state bits, rounded) then two first-order shift high-pass stages."""
    x = c4.astype(np.int64) << EXTRA
    b0, b1, b2 = SB; a1, a2 = SA
    y = np.zeros_like(x)
    for n in range(x.shape[1]):
        acc = b0 * x[:, n]
        if n >= 1: acc = acc + b1 * x[:, n - 1] - a1 * y[:, n - 1]
        if n >= 2: acc = acc + b2 * x[:, n - 2] - a2 * y[:, n - 2]
        y[:, n] = (acc + (1 << (FRAC - 1))) >> FRAC
    x = y
    for _ in range(2):
        h = np.zeros_like(x)
        for n in range(x.shape[1]):
            xp = x[:, n - 1] if n >= 1 else 0
            hp = h[:, n - 1] if n >= 1 else 0
            h[:, n] = x[:, n] - xp + hp - ((hp + (1 << (HPK - 1))) >> HPK)
        x = h
    return x / 2.0 ** EXTRA
def hw_stats(light, trials=6000):
    Z, R = [], []
    for _ in range(trials // 500):
        codes = f.random_codes(500); cu = cm.upsample(codes)
        sig = f.channel(light(codes)) if light else 0.0
        y = (sig + cm.noise_td(f.rng, f.S_out, 500))[:, f.win][:, ::STEP]
        y = np.clip(np.round(y / Y_LSB), -2 ** (Y_BITS - 1), 2 ** (Y_BITS - 1) - 1)         # signed 8-bit samples
        c4 = cu[:, ::STEP]
        tm_full = template(c4)
        d4 = f.d // STEP
        tm = np.round(tm_full[:, 2 * NS // STEP + d4: 3 * NS // STEP + d4])        # integer template
        c = c4[:, 2 * NS // STEP: 3 * NS // STEP]
        z = (y * c).sum(axis=1)
        yt = (y * tm).sum(axis=1); tt = (tm * tm).sum(axis=1); yy = (y * y).sum(axis=1)
        resid = yy - yt * yt / np.maximum(tt, 1)            # == the compare  yy*tt - yt^2  vs  thr*tt  in hardware
        Z.append(z); R.append(resid)
    return np.concatenate(Z), np.concatenate(R)
if __name__ == "__main__":
    zn, _ = hw_stats(None); eta = cm.ETA_SIGMAS * zn.std()
    zl, rl = hw_stats(f.legit()); thr = np.quantile(rl, 0.999)
    print(f"integer correlator: sigma0 {zn.std():.1f} LSB-units, eta {eta:.0f}; legit mean {zl.mean():.0f}")
    out = [np.mean(zl > eta), np.mean((zl > eta) & (rl < thr))]
    for lt in (f.partial(1, .75), f.partial(1, .9), f.blind(3)):
        z, r = hw_stats(lt); out.append(np.mean((z > eta) & (r < thr)))
    print("legit corr-only %.4f, legit D1 %.4f | partial .75 %.4f  .9 %.4f | blind 3x %.4f" % tuple(out))
    json.dump(dict(lpb=SB.tolist(), lpa=SA.tolist(), frac=FRAC, extra=EXTRA, hpk=HPK, eta=float(eta), thr=float(thr), ybits=Y_BITS, ylsb=Y_LSB),
              open(pathlib.Path(__file__).resolve().parent.parent / "rtl" / "coeffs.json", "w"), indent=1)
