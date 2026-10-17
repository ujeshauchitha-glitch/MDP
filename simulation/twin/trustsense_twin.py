"""TrustSense Layer-1 digital twin: one behavioural model of the whole chain.

   light (DC + PPG + coded LED + attacker light)
     -> photodiode current
        -> SLOW path:  servo-cancelled 3-range TIA (servo_loop.py: SPICE-fitted plants, SPICE noise PSD,
                       10-bit ADC, SAR acquisition, integrator, 12-bit DAC + sigma-delta, auto-range)
        -> FAST path:  Cc / common-gate / mirror / wideband TIA (SPICE complex H(f) and output noise PSD
                       + photodiode shot noise), 48-chip Trivium code at 480 kchip/s,
                       rectangular correlator + residual goodness-of-fit test (D1)
     -> decision: frame accepted if correlation > eta (Pfa 1e-8) AND residual < threshold.

Everything numeric comes from the ngspice runs in simulation/spice (results_final, servo data*).
Assumptions: Gaussian stationary noise, linear time-invariant channel (clipping of the fast path is
not modelled), Trivium frames drawn from one continuous keystream (numpy random codes are used for the
large Monte-Carlo runs, statistically equivalent for a good cipher).
"""
import os, sys, math, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SIM = HERE.parent
sys.path.insert(0, str(SIM / "detect")); sys.path.insert(0, str(SIM / "servo")); sys.path.insert(0, str(HERE))
_argv = sys.argv; sys.argv = sys.argv[:1]
import coherent_mc as cm      # noqa: E402  (channel loader, noise synthesis, Q functions)
import servo_loop as sl       # noqa: E402
sys.argv = _argv
from codegen import Trivium   # noqa: E402

RES_FINAL = SIM / "spice" / "results_final"
LABEL_I = {"10n": 10e-9, "30n": 30e-9, "100n": 100e-9, "300n": 300e-9, "1u": 1e-6}
SLOW_I = {"5n": 5e-9, "10n": 10e-9, "30n": 30e-9, "100n": 100e-9, "300n": 300e-9, "1u": 1e-6, "2u": 2e-6}
N, NS, NSYM, OS, L = cm.N, cm.NS, cm.NSYM, cm.OS, cm.L


class FastPath:
    """Wideband coherent verifier at one operating point (channel chosen by I_DC)."""

    def __init__(self, i_dc, m=0.02, seed=1, res=RES_FINAL, calib_trials=4000):
        lab = min(LABEL_I, key=lambda k: abs(math.log(LABEL_I[k] / i_dc)))
        cm.RES = pathlib.Path(res)
        self.label, self.i_dc, self.m = lab, i_dc, m
        self.rng = np.random.default_rng(seed)
        self.fg, self.Hg, Sn = cm.channel_on_grid(lab)
        self.S_out = Sn ** 2 + 2 * cm.Q_E * i_dc * np.abs(self.Hg) ** 2   # SPICE noise + shot noise at the real I_DC
        self.d = cm.best_delay(self.Hg)
        self.mid = slice(2 * NS, 3 * NS)
        self.win = slice(2 * NS + self.d, 3 * NS + self.d)
        self.calibrate(calib_trials)

    # ---- signal chain -------------------------------------------------------------------
    def channel(self, x):
        return np.fft.irfft(np.fft.rfft(x, axis=1) * self.Hg, n=L, axis=1)

    def frames(self, codes, light):
        """codes: (B,NSYM,N) true chips (middle symbol is scored). light: callable(codes)->current
        waveform (B,L) [A] added at the photodiode (legit LED, attacker, or None).
        Returns (z correlator output [V], residual energy [V^2])."""
        B = codes.shape[0]
        cu = cm.upsample(codes)
        tmpl = self.channel(cu)[:, self.win]
        sig = self.channel(light(codes)) if light else 0.0
        y = (sig + cm.noise_td(self.rng, self.S_out, B))[:, self.win]
        z = (y * cu[:, self.mid]).sum(axis=1) / NS
        mu = (y * tmpl).sum(axis=1) / (tmpl * tmpl).sum(axis=1)
        res = ((y - mu[:, None] * tmpl) ** 2).sum(axis=1) / NS
        return z, res

    def random_codes(self, B):
        return cm.make_codes(self.rng, B)

    # ---- light sources -------------------------------------------------------------------
    def legit(self, scale=1.0):
        return lambda c: scale * self.m * self.i_dc * cm.upsample(c)

    def blind(self, A):
        """attacker injects random chips, amplitude A x the legitimate perturbation."""
        return lambda c: A * self.m * self.i_dc * cm.upsample(cm.make_codes(self.rng, c.shape[0]))

    def partial(self, A, f):
        """attacker knows a fraction f of the chips (leaked / guessed), rest random."""
        def g(c):
            a = cm.make_codes(self.rng, c.shape[0])
            keep = self.rng.random(c.shape) < f
            return A * self.m * self.i_dc * cm.upsample(np.where(keep, c, a))
        return g

    def relay(self, A, tau):
        """attacker observes each chip perfectly and re-emits it tau seconds late."""
        fr = np.fft.rfftfreq(L, 1 / cm.FS)
        ph = np.exp(-2j * np.pi * fr * tau)
        return lambda c: np.fft.irfft(np.fft.rfft(A * self.m * self.i_dc * cm.upsample(c), axis=1) * ph, n=L, axis=1)

    # ---- decision ------------------------------------------------------------------------
    def calibrate(self, trials):
        """Thresholds from the twin itself: eta from the noise-only sigma (Pfa 1e-8 for AWGN),
        residual threshold at the 99.9 % quantile of legitimate frames."""
        zn = np.concatenate([self.frames(self.random_codes(500), None)[0] for _ in range(trials // 500)])
        self.s0 = zn.std()
        self.eta = cm.ETA_SIGMAS * self.s0
        zl, rl = self._collect(self.legit(), trials)
        self.r_thr = np.quantile(rl, 0.999)
        self.mu = zl.mean()

    def _collect(self, light, trials):
        zs, rs = [], []
        for _ in range(max(1, trials // 500)):
            z, r = self.frames(self.random_codes(500), light)
            zs.append(z); rs.append(r)
        return np.concatenate(zs), np.concatenate(rs)

    def accept(self, z, r, residual_test=True):
        a = z > self.eta
        return a & (r < self.r_thr) if residual_test else a

    def rate(self, light, trials=6000, residual_test=True):
        z, r = self._collect(light, trials)
        return float(np.mean(self.accept(z, r, residual_test)))

    def pd_gauss(self):
        """Pd at Pfa 1e-8 from the Gaussian tail, as in coherent_mc.py (comparable to detect_results.txt)."""
        zs, _ = self._collect(self.legit(), 8000)
        return cm.Q((self.eta - zs.mean()) / zs.std()), zs.mean() / self.s0

    def min_idc(self):
        """d is linear in I_DC for a fixed channel; scale to the I_DC giving d = D_REQ (Pd 99.9 % at Pfa 1e-8)."""
        d = self.mu / self.s0
        return self.i_dc * cm.D_REQ / d if d > 0 else float("nan")


class SlowPath:
    """Servo-cancelled PPG path with auto-ranging (servo_loop.simulate)."""

    def __init__(self, psd_dir="data_sd"):
        os.environ["SERVO_PSD_DIR"] = psd_dir   # degenerated cancel sink noise (final design, docs s36)

    def run(self, i_dc, ppg_pct=2.0, tstop=2.5, seed=3):
        lab = min(SLOW_I, key=lambda k: abs(math.log(SLOW_I[k] / i_dc)))
        r = sl.simulate(lab, tstop, i_dc, ppg=(ppg_pct / 100 * i_dc, 1.2), psd_idc=lab, gain_sched=False, auto=True, seed=seed)
        t, out, z0 = r["t"], r["out"], r["z0"]
        m = t >= tstop - 1.5
        y = (sl.VCM - out[m]) / z0
        tt = t[m]
        G = np.c_[np.sin(2 * math.pi * 1.2 * tt), np.cos(2 * math.pi * 1.2 * tt), np.ones_like(tt), tt - tt.mean()]
        c, *_ = np.linalg.lstsq(G, y, rcond=None)
        amp = ppg_pct / 100 * i_dc
        res = y - G @ c                               # same 0.5-100 Hz Hann-window band-limited rms as servo/study.py
        w = np.hanning(len(res))
        Y = np.fft.rfft(res * w)
        fr = np.fft.rfftfreq(len(res), sl.DT)
        band = (fr >= 0.5) & (fr <= 100)
        rms = math.sqrt(2 * np.sum(np.abs(Y[band]) ** 2) / (len(res) * np.sum(w ** 2)))
        return dict(lock_s=r["srv"].t_lock, range=r["cur"], range_switch_s=r["switch_t"],
                    ppg_gain=math.hypot(c[0], c[1]) / amp, resid_rms_pA=float(rms * 1e12),
                    reacq=r["srv"].reacq, clip_max_mV=float(np.abs(out[m] - sl.VCM).max() * 1e3))


class TrustSenseTwin:
    def __init__(self, i_dc, m=0.02, key=bytes(range(10)), iv=bytes(10), seed=7):
        self.i_dc, self.m = i_dc, m
        self.fast = FastPath(i_dc, m, seed)
        self.slow = SlowPath()
        self.cipher = Trivium(key, iv)

    def next_codes(self, nframes):
        """Frames of N chips from the continuous Trivium keystream; the neighbouring symbols come from the same stream."""
        chips = self.cipher.chips((nframes + NSYM - 1) * N)
        return np.stack([chips[i * N:(i + NSYM) * N].reshape(NSYM, N) for i in range(nframes)])

    def session(self, nframes=40, ppg_pct=2.0, attack=None, tstop=2.5):
        """attack: None (genuine) | ('blind',A) | ('partial',A,f) | ('relay',A,tau)."""
        p = self.slow.run(self.i_dc, ppg_pct, tstop)
        if attack is None:
            lt = self.fast.legit()
        elif attack[0] == "blind":
            lt = self.fast.blind(attack[1])
        elif attack[0] == "partial":
            lt = self.fast.partial(attack[1], attack[2])
        else:
            lt = self.fast.relay(attack[1], attack[2])
        z, r = self.fast.frames(self.next_codes(nframes), lt)
        ok = self.fast.accept(z, r)
        return dict(slow=p, accepted=int(ok.sum()), frames=nframes, mean_z_over_sigma=float(z.mean() / self.fast.s0),
                    verdict="PPG TRUSTED" if ok.mean() > 0.5 else "PPG REJECTED")
