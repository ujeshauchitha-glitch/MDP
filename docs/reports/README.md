# Status reports

Easy-to-read summaries of the work, newest first. Technical detail lives in
[`../STATUS.md`](../STATUS.md) and [`../afe-architecture.md`](../afe-architecture.md).

| Report | Date | What it is |
|---|---|---|
| [`2026-10-17-05-digital-twin-and-closure.md`](2026-10-17-05-digital-twin-and-closure.md) | 2026-10-17 | The digital twin, validated; Trivium chosen; relay attack not defendable in Layer 1; converter and digitiser designs; area (~5 tiles) and power (~90 µW) estimates |
| [`2026-10-17-04-segmented-canceller.md`](2026-10-17-04-segmented-canceller.md) | 2026-10-17 | Tested splitting the canceller into many small cells: same noise as one big device, so the split can be chosen for accuracy |
| [`2026-10-17-03-dac-bandwidth-receiver.md`](2026-10-17-03-dac-bandwidth-receiver.md) | 2026-10-17 | A bandwidth correction (63 kHz, not 280 kHz), the best-possible receiver is only 0.5 dB better, how to build the steady-current canceller quietly, pulse SNR 58–63 dB |
| [`2026-10-17-02-audit-and-noise.md`](2026-10-17-02-audit-and-noise.md) | 2026-10-17 | Audit results (what was checked and what was wrong), the main pulse-path noise source and a +13–17 dB fix, how long the code must run for dim signals |
| [`2026-10-17-overview.md`](2026-10-17-overview.md) | 2026-10-17 | Plain-language overview: what is being built, the current design, results in plain words, what went wrong and was fixed, current risks, glossary |
| [`PROGRESS-LOG.md`](PROGRESS-LOG.md) | updated with each report | Chronological list of every milestone with its commit and the lesson learned |

New reports are added after each meaningful batch of work and pushed to git.
