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
FRAC = 16                                  # coefficient fractional bits (poles at 0.9973 need >= 14)
EXTRA = 10                                 # fractional bits kept in the section outputs / state
# scale the template so that |t| peaks near 100 (integer units) for +/-1 chips
_rng = np.random.default_rng(5)
_c = _rng.choice([-1.0, 1.0], size=(50, 400))
_peak = np.abs(sosfilt(sos, _c, axis=1))[:, 100:].max()
sos[0, :3] *= 100.0 / _peak
qi = lambda x: np.round(np.asarray(x) * 2 ** FRAC).astype(np.int64)
SB = qi(sos[:, :3]); SA = qi(sos[:, 4:])        # integer coefficients (Q16)
print("integer SOS  b:", SB.tolist(), " a1,a2:", SA.tolist(), " template scale", 100.0 / _peak)
def template(c4):
    """Fixed-point cascade of two direct-form-I biquads (all integer arithmetic, Q16 coefficients, EXTRA fractional state bits)."""
    x = c4.astype(np.int64) << EXTRA                   # chip +/-1 in Q(EXTRA)
    for k in range(2):
        b0, b1, b2 = SB[k]; a1, a2 = SA[k]
        y = np.zeros_like(x)
        for n in range(x.shape[1]):
            acc = b0 * x[:, n]
            if n >= 1: acc = acc + b1 * x[:, n - 1] - a1 * y[:, n - 1]
            if n >= 2: acc = acc + b2 * x[:, n - 2] - a2 * y[:, n - 2]
            y[:, n] = (acc + (1 << (FRAC - 1))) >> FRAC       # round to nearest, arithmetic shift
        x = y
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
    json.dump(dict(sosb=SB.tolist(), sosa=SA.tolist(), frac=FRAC, extra=EXTRA, eta=float(eta), thr=float(thr), ybits=Y_BITS, ylsb=Y_LSB),
              open(pathlib.Path(__file__).resolve().parent.parent / "rtl" / "coeffs.json", "w"), indent=1)
