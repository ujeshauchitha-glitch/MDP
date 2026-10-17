# TrustSense Layer-1 digital twin

`trustsense_twin.py`: one behavioural model of light -> photodiode -> slow (PPG) path with servo +
auto-range, and fast path with Trivium-coded flicker -> correlator + residual test -> verdict.
All numbers come from the SPICE runs (`simulation/spice/results_final`, `simulation/servo/data*`).

| File | Purpose |
|---|---|
| `codegen.py` | Trivium keyed stream cipher (matches the eSTREAM test vector) = chip generator |
| `trustsense_twin.py` | the twin (`FastPath`, `SlowPath`, `TrustSenseTwin`) |
| `validate.py`, `validation.txt` | twin vs the stand-alone SPICE-based studies (fast path within 1.2 % on d; slow path range, lock, PPG gain, noise match) |
| `scenarios.py`, `scenarios.txt` | genuine contact and attacks end to end |

Run: `python validate.py`, `python scenarios.py` (no ngspice needed; uses stored SPICE data).
Known artefact: the slow-path "lock time" (5 mV criterion) can read ~380 ms at 300 nA in some noise seeds; the DAC itself locks in ~25 ms.
