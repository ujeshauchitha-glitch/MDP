"""Sizing studies for the digital servo (see servo_loop.py)."""
import sys, time, math
import numpy as np
import servo_loop as sl

Z0 = None


def dac_lock(r, target, tol=50e-12, hold=0.05):
    """First time after which the DAC command stays within +/-tol of the target for `hold` s."""
    k = int(0.01 / sl.DT)                                  # 10 ms mean removes the sigma-delta toggling
    ma = np.convolve(r["idac"], np.ones(k) / k, mode="same")
    ok = np.abs(ma - target) < tol
    w = int(hold / sl.DT)
    cs = np.cumsum(np.concatenate([[0], ok.astype(int)]))
    good = (cs[w:] - cs[:-w]) == w
    return r["t"][np.argmax(good)] if good.any() else None


def ppg_metrics(r, f_ppg, amp, t0):
    """Recover PPG from the output; return (gain, phase_deg, noise_rms_0.5-100Hz [A], dc_offset_V)."""
    t, out = r["t"], r["out"]
    m = t >= t0
    y = (sl.VCM - out[m]) / r["z0"]               # input-referred current estimate (inverting TIA)
    tt = t[m]
    G = np.c_[np.sin(2 * math.pi * f_ppg * tt), np.cos(2 * math.pi * f_ppg * tt), np.ones_like(tt)]
    # remove slow drift: add linear term
    G = np.c_[G, tt - tt.mean()]
    c, *_ = np.linalg.lstsq(G, y, rcond=None)
    a = math.hypot(c[0], c[1]) / amp
    ph = math.degrees(math.atan2(c[1], c[0]))
    resid = y - G @ c
    # band-limit 0.5-100 Hz
    Y = np.fft.rfft(resid * np.hanning(len(resid)))
    fr = np.fft.rfftfreq(len(resid), sl.DT)
    band = (fr >= 0.5) & (fr <= 100)
    enbw = 1.5
    rms = math.sqrt(np.sum(np.abs(Y[band]) ** 2) * 2 / (np.sum(np.hanning(len(resid)) ** 2) * len(resid))) if False else \
        math.sqrt(2 * np.sum(np.abs(Y[band]) ** 2) / (len(resid) * np.sum(np.hanning(len(resid)) ** 2)))
    return a, ph, rms, float(np.mean(out[m]) - sl.VCM)


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "lock":
        print("I_DC    lock time [ms]  DAC error [pA]  acquisition mode")
        for idc, val in (("10n", 10e-9), ("30n", 30e-9), ("100n", 100e-9), ("300n", 300e-9), ("1u", 1e-6), ("2u", 2e-6)):
            r = sl.simulate(idc, 0.3, val, noise=True, psd_idc=idc)
            lt = dac_lock(r, val)
            print(f"{idc:5s}   {('%.1f' % (lt*1e3)) if lt else 'no lock':>10}     {(r['idac'][-3000:].mean()-val)*1e12:10.1f}      {r['srv'].mode}")
    elif what == "ppg":
        idc, val = sys.argv[2], {"10n": 10e-9, "30n": 30e-9, "100n": 100e-9, "300n": 300e-9, "1u": 1e-6}[sys.argv[2]]
        fc = float(sys.argv[3]); tstop = float(sys.argv[4])
        amp = min(0.01 * val, float(sys.argv[5]) * 1e-12 if len(sys.argv) > 5 else 150e-12)   # 1 GOhm clips beyond ~+/-300 pA
        t0 = time.time()
        r = sl.simulate(idc, tstop, val, ppg=(amp, 1.2), fc=fc, psd_idc=idc, gain_sched=False)
        a, ph, rms, off = ppg_metrics(r, 1.2, amp, 1.5)
        print(f"I_DC={idc} fc={fc} Hz PPG amp {amp*1e12:.0f} pA ({time.time()-t0:.0f}s): gain {a:.4f} phase {ph:+.1f} deg, "
              f"noise {rms*1e12:.1f} pA (0.5-100 Hz), DC offset {off*1e3:+.1f} mV, re-acquisitions {r['srv'].reacq}", flush=True)
    elif what == "step":
        idc, val = sys.argv[2], {"10n": 10e-9, "100n": 100e-9, "300n": 300e-9}[sys.argv[2]]
        dI = float(sys.argv[3]) * 1e-12; tstep = 2.0; tstop = float(sys.argv[4])
        r = sl.simulate(idc, tstop, val, steps=[(tstep, dI)], fc=0.05, psd_idc=idc, gain_sched=False)
        k = int(0.05 / sl.DT)
        err = np.convolve(np.abs(r["out"] - sl.VCM), np.ones(k) / k, mode="same")
        post = r["t"] >= tstep
        peak = np.abs(r["out"][post] - sl.VCM).max()
        bad = np.where((err > 0.03) & post)[0]
        tset = (r["t"][bad[-1]] - tstep) if len(bad) else 0.0
        fin = (r["idac"][-int(0.5 / sl.DT):].mean() - (val + dI)) * 1e12
        print(f"I_DC={idc} step +{dI*1e12:.0f} pA at t=2 s: peak |out-VCM| {peak*1e3:.0f} mV, settles (50 ms mean < 30 mV) after {tset*1e3:.0f} ms, "
              f"re-acquisitions {r['srv'].reacq}, final DAC error {fin:.1f} pA", flush=True)
