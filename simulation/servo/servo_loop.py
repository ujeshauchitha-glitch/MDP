"""Digital DC-cancellation servo for the slow (PPG) path: closed-loop co-simulation.

Analog side (from ngspice, tt/27C, VDD 3.3 V, VCM 1.4 V, T-network slow TIA):
  * Iph -> s_out transimpedance, fitted by a 2nd-order low-pass (data/slow_plant_*.txt)
  * input-referred slow-path noise PSD incl. the real NMOS cancel device
    (data/slow_psd_<I_DC>.txt), used as the analog noise floor
Digital side modelled here:
  * ADC: N_ADC bits over +/-0.5 V around VCM, sampled at FS_ADC, + input noise
  * controller: SAR ACQUISITION (binary search of the DAC code) -> TRACK
    integrator (gain scheduled on |error|) -> re-ACQUISITION on a large step
  * DAC: 12-bit coarse current DAC (LSB_C) + first-order sigma-delta fine path
    clocked every plant step (1/DT), error feedback from a 24-bit accumulator

Sign convention (inverting TIA): s_out = VCM + Z*(I_dac - I_ph). s_out > VCM
means too much cancel current.

Run as a script for the sizing study; see docs/afe-architecture.md s23.
"""
import pathlib, math
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import cont2discrete

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

DT = 10e-6                  # plant / sigma-delta step [s]
VCM = 1.4
CLIP = 0.45                 # usable output swing around VCM [V]
FS_ADC = 2000.0             # ADC sample rate [Hz]
N_ADC = 10
ADC_FS = 1.0                # +/-0.5 V full scale
ADC_NOISE = 0.5             # LSB rms
N_DAC = 12
LSB_C = 0.5e-9              # coarse DAC LSB [A]; full scale ~2.05 uA
BOOST_THR = 0.03           # |2 s mean error| above this speeds up the integrator [V]
BOOST_GAIN = 20.0
SAR_WAIT = 3                # ADC samples to wait after each SAR decision


def fit_plant(idc="100n"):
    p = np.loadtxt(DATA / f"slow_plant_{idc}.txt")
    f, mag = p[:, 0], p[:, 1]
    m = (f >= 1) & (f <= 1e5)

    def res(x):
        z0, f0, q = x
        w = (f[m] / f0) ** 2
        h = z0 / np.sqrt((1 - w) ** 2 + w / q ** 2)
        return np.log(h) - np.log(mag[m])
    r = least_squares(res, [1e9, 3e3, 0.8], bounds=([1e8, 300, 0.2], [1e10, 3e4, 5]))
    return r.x, float(np.sqrt(np.mean(r.fun ** 2)))


def make_plant(z0, f0, q):
    w0 = 2 * math.pi * f0
    A = np.array([[0, 1], [-w0 ** 2, -w0 / q]]); B = np.array([[0], [w0 ** 2]])
    C = np.array([[z0, 0]]); D = np.array([[0.0]])
    Ad, Bd, Cd, _, _ = cont2discrete((A, B, C, D), DT)[:5]
    return Ad, Bd.ravel(), Cd.ravel()


def noise_current(n, idc, seed):
    """Input-referred analog noise [A] from the SPICE PSD (nearest I_DC file)."""
    d = np.loadtxt(DATA / f"slow_psd_{idc}.txt")
    f, a = d[:, 0], d[:, 1]
    fr = np.fft.rfftfreq(n, DT)
    lf = np.log(np.maximum(fr, 1e-3))
    s = np.exp(np.interp(lf, np.log(f), np.log(a), left=np.nan, right=np.nan))
    lo = fr < f[0]
    s[lo] = a[0] * (np.maximum(fr[lo], 1e-3) / f[0]) ** -0.5          # 1/f extrapolation below 0.1 Hz
    s[fr > f[-1]] = a[-1]
    s[0] = 0.0
    rng = np.random.default_rng(seed)
    X = s * np.sqrt(n / (2 * DT) / 2) * (rng.standard_normal(len(fr)) + 1j * rng.standard_normal(len(fr)))
    return np.fft.irfft(X, n)


class Servo:
    def __init__(self, fc=0.05, adc_noise=ADC_NOISE, gain_sched=True, seed=1, boost=True):
        self.ki = 2 * math.pi * fc / FS_ADC              # integrator gain per ADC sample
        self.gain_sched = gain_sched
        self.rng = np.random.default_rng(seed)
        self.adc_noise = adc_noise
        self.reacq = 0
        self.boost = boost
        self.reset()

    def reset(self):
        self.acc = 0.0                  # DAC command [A] (24-bit accumulator emulated by float)
        self.mode = "ACQ"
        self.bit = N_DAC - 1
        self.wait = 0
        self.sd_err = 0.0
        self.big = 0
        self.t_lock = None
        self.code = 0
        self.m = 0.0                    # 2 s signed average of the ADC error (PPG averages out, a DC offset does not)

    def adc(self, v):
        lsb = ADC_FS / 2 ** N_ADC
        x = (v - VCM) + self.rng.standard_normal() * self.adc_noise * lsb
        return float(np.clip(np.round(x / lsb) * lsb, -ADC_FS / 2, ADC_FS / 2 - lsb))

    def sample(self, v, z_nom):
        """One ADC sample -> update the command (called every 1/FS_ADC)."""
        e_v = self.adc(v)                       # >0: too much cancel current
        if self.mode == "ACQ":
            if self.wait > 0:
                self.wait -= 1
                return
            # SAR: trial bit was set last time; keep it if output is not above VCM
            if self.code and e_v > 0:
                self.code &= ~(1 << (self.bit + 1)) if self.bit + 1 < N_DAC else self.code
            if self.bit < 0:
                self.mode = "TRACK"; self.acc = self.code * LSB_C; return
            self.code |= (1 << self.bit)
            self.acc = self.code * LSB_C
            self.bit -= 1
            self.wait = SAR_WAIT
            return
        # TRACK
        err_a = -e_v / z_nom                    # [A]: positive -> raise cancel current
        # note: e_v>0 means too much cancel -> acc should go down
        self.m += (e_v - self.m) / (2.0 * FS_ADC)
        k = self.ki * (100.0 if (self.gain_sched and abs(e_v) > 0.02) else 1.0)
        if self.boost and abs(self.m) > BOOST_THR:
            k *= BOOST_GAIN                      # persistent DC offset -> faster tracking until it is gone
        self.acc = min(max(self.acc + k * err_a, 0.0), (2 ** N_DAC - 1) * LSB_C)
        if abs(e_v) > 0.30:
            self.big += 1
            if self.big > 10:                   # 5 ms beyond range -> re-acquire
                self.reset(); self.reacq += 1
        else:
            self.big = 0

    def dac(self):
        """Sigma-delta fine path: returns the instantaneous DAC current [A]."""
        c = self.acc / LSB_C
        base = math.floor(c)
        self.sd_err += c - base
        if self.sd_err >= 1.0:
            self.sd_err -= 1.0
            base += 1
        return min(max(base, 0), 2 ** N_DAC - 1) * LSB_C


def simulate(idc, tstop, i_dc, ppg=None, steps=(), fc=0.05, seed=3, noise=True, gain_sched=True,
             adc_noise=ADC_NOISE, plant_idc="100n", psd_idc=None, ideal=False, boost=True):
    """i_dc: DC photocurrent [A]; ppg=(amp,freq); steps=[(t, dI)].  Returns time series."""
    n = int(round(tstop / DT))
    (z0, f0, q), _ = fit_plant(plant_idc)
    Ad, Bd, Cd = make_plant(z0, f0, q)
    x = np.zeros(2)
    srv = Servo(fc=fc, gain_sched=gain_sched, seed=seed + 1, boost=boost)
    nz = noise_current(n, psd_idc or idc, seed) if noise else np.zeros(n)
    t = np.arange(n) * DT
    i_ph = i_dc + nz
    if ppg:
        i_ph = i_ph + ppg[0] * np.sin(2 * math.pi * ppg[1] * t)
    for ts, di in steps:
        i_ph = i_ph + di * (t >= ts)
    out = np.empty(n); idac = np.empty(n)
    adc_every = int(round(1 / FS_ADC / DT))
    v = VCM
    for k in range(n):
        d = i_dc if ideal else srv.dac()          # ideal=True: static noiseless cancel (baseline)
        u = d - i_ph[k]                          # net current into the TIA [A], sign: + -> output up
        x = Ad @ x + Bd * u
        y = float(Cd @ x)
        v = VCM + min(max(y, -CLIP), CLIP)
        out[k] = v; idac[k] = d
        if (not ideal) and k % adc_every == adc_every - 1:
            srv.sample(v, z0)
            if srv.mode == "TRACK" and srv.t_lock is None and abs(v - VCM) < 0.005:
                srv.t_lock = t[k]
    return dict(t=t, out=out, idac=idac, i_ph=i_ph, srv=srv, z0=z0, fit=(z0, f0, q))


def lock_time(r, tol=0.005, hold=0.05):
    """First time after which |out - VCM| < tol for `hold` seconds."""
    ok = np.abs(r["out"] - VCM) < tol
    w = int(hold / DT)
    cs = np.cumsum(np.concatenate([[0], ok.astype(int)]))
    good = (cs[w:] - cs[:-w]) == w
    idx = np.argmax(good) if good.any() else None
    return None if idx is None else r["t"][idx]


if __name__ == "__main__":
    for idc in ("100n",):
        (z0, f0, q), rms = fit_plant(idc)
        print(f"plant fit {idc}: Z0={z0:.3g} f0={f0:.0f} Hz Q={q:.2f}  (log-mag rms err {rms:.3f})")
    r = simulate("100n", 0.2, 100e-9, noise=False)
    print("lock time (noiseless, 100 nA): %.1f ms; final DAC %.2f nA vs I_DC 100 nA" % (
        (lock_time(r) or float('nan')) * 1e3, r["idac"][-1] * 1e9))
