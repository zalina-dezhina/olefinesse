# Research log — olefins Delta-Delta

> **Purpose.** This file is the project's persistent memory. The compute is
> ephemeral (every restart loses the assistant's session memory), so anything
> worth keeping across sessions lives **here, in the repo**. Append a dated entry
> whenever you (or an AI assistant) learn something non-obvious, make a decision,
> or hit a dead end. Newest first. Keep it factual and link to code/docs.

---

## Project in one paragraph

Indorama runs 7 near-identical NGL cracking furnaces (1HA–1HG). The headline KPI
is ethylene yield per ton of feed; the furnace is the high-value control surface.
**Delta-Delta** — the run-normalised per-tube coil-outlet skin-temperature drift
since the last decoke — is the furnace-health / coking signal operators already
use to decide when to decoke. The deliverable (per the KBR/INSITE 3.0 value-prop)
is a **forecaster + what-if tool** for Delta-Delta, mapped to cumulative yield,
with the four severity levers (throughput, steam/HC, COT, coil pressure) as
inputs. Optimisation is a later phase that must respect the Delta-Delta health
margin. Source docs in `context/`.

## Standing facts (verify before relying on; update if wrong)

- **Data lives in Unity Catalog**, not the repo: `…_bronze.timeseries.events`
  (~6.6 B rows, EAV, `Value` is variant) + `…timeseries.metadata` (4119 tags).
  Access via **databricks-connect to the running cluster** (plain pyspark fails).
  Cluster id is ephemeral — `databricks clusters list`. See `docs/data_dictionary.md`.
- **Delta-Delta source tags** = per-tube skin TCs `H-X TUBE CUR COT` (`01TI10xxA.PV`),
  dense (9–29 tubes/furnace) but **2025-02 onward only**. An 8-tube proxy
  (`BANK #x PQE #5/#8`) reaches **back to 2019**.
- **Process drivers reach back to 2019** (feed, steam, COT controller, coil
  pressure, draft, NGL feed GC). So ~7 yr of driver history, ~13 mo of dense
  Delta-Delta.
- **Decoke ≠ cold furnace.** Detect decokes from HC **feed cut to ~0**, not
  temperature. Gives ~17–25 day runs (see `runs.py`).
- **Three DCS numbering schemes**, all decoded in `docs/data_dictionary.md`.
- **Effluent GC is unreliable** (quantised/identical values, zero-dropouts) —
  flagged in the approach note; treat cautiously.

## Open questions / TODO

- [ ] Reconstruct Delta-Delta back to 2019 with `tube_COT_long` and validate the
      8-tube proxy against the dense 2025+ set on the overlap window.
- [ ] Pool the 7 furnaces' run trajectories into a single run-age-indexed model;
      build the actual Delta-Delta **forecaster** (target: trajectory for rest of run).
- [ ] Map forecast Delta-Delta → cumulative ethylene yield (the yield reference).
- [ ] Get DCS alarm/warning Delta thresholds per furnace/pass/tube from Indorama/KBR.
- [ ] Confirm GC reliability vs lab data with KBR.

---

## Log

### 2026-06-12 — Initial data exploration, tag mapping, toolkit, correlations
- Located all data; built `olefins_ddf` package (catalog → load → Delta-Delta →
  runs → features → correlations → plots). Tests in `tests/`.
- Decoded the tag universe (211 core tags across 10 roles) — `docs/data_dictionary.md`.
- **Finding (run length):** runs are **not** clockwork 25 days. Fleet-wide
  median **22.1 d**, spread ~5–31 d; per-furnace means 18.8–24.2 d, std 3.6–7.3 d.
  1HG is most regular (24.2 ± 3.6 d), 1HF most variable (± 7.3 d). Visible
  fleet-synchronised offline period ~Nov 2025. See `output/run_lengths.png`,
  `output/run_summary.csv`.
- **Finding (data depth):** drivers since 2019, dense tube TCs since 2025-02 —
  `output/data_coverage_by_year.png`.
- **Finding (coking drivers, 1HA):** `dd_abs_max` ~ run_age(+0.39), feed_C5+(+0.28),
  CO2(−0.18), COT(+0.18), steam/HC(−0.16) — physically textbook. See
  `output/1HA_08_drivers_of_dd_abs_max.png`, `1HA_07_corr_heatmap.png`.
- Reorganised flat `ddf/` prototype into the `olefins_ddf/` package + docs
  (run with `python -m olefins_ddf` from the repo root; no install needed).
- **Validated long-history reconstruction:** `--long-history` (8-tube BANK proxy,
  hourly, 2019→2026) reconstructs Delta-Delta cleanly across all 7 years for 1HA
  — **104 runs** vs 16 from the dense-TC window alone (~6.5×; ≈700 run trajectories
  fleet-wide). Figures in `output/long_history_1HA/`. This is the training-data
  unlock for the forecaster: prefer the long proxy for run-cycle volume, the dense
  TCs (2025+) for tube-level resolution; cross-validate the two on their overlap.
- **Lagged structure:** COT leads `dd_abs_max` with a ~+17–23 h coking-response
  lag; negative correlation at negative lag = operators backing off severity when
  health degrades (feedback). `output/1HA_09_xcorr_cot_dd_abs_max.png`.
