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
- **Delta-Delta source tags** = per-tube skin TCs `01TI{F}{NNN}A.PV` (F=furnace
  1–7, NNN=tube 001–192). **All 192/furnace (48/pass), ~1/min, 2025-02 onward**
  (most have blank descriptions — key on the ID, not "TUBE CUR COT"). An 8-tube
  proxy (`BANK #x PQE #5/#8`) reaches **back to 2019**.
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

### 2026-06-15 — Pass topology decoded & threaded through the toolkit
- **Topology confirmed: furnace → 4 passes (#A–#D) → bank of parallel tubes.**
  Each pass is independently feed- and dilution-steam-controlled; tubes (each with
  a COT TC) are where coking happens. Documented in `docs/data_dictionary.md`
  (*Furnace topology*).
- **All 7 furnaces have exactly 4 feed + 4 steam passes** (verified on cluster).
  Two feed tags were previously missed by description parsing — formatting quirks,
  now fixed in `catalog.py`: `01FC0411` (1HC-D, double space `FD␣␣#D`) and
  `01FC0605` (1HE-A, `HIE` — digit `1` typed as letter `I`). feed_flow 26→28.
- **New `decoke_air` role** (`FUR X PASS<A-D> DECOKE AIR`, 4/furnace, all 7) —
  independent confirmation of 4 passes and a cleaner future decoke detector.
- **GROUND TRUTH (context files): 48 tubes per pass, 192 per furnace.** KBR
  *Furnace Control Systems* p6: "four(4) radiant passes (BANKS) per furnace. Each
  pass has 48 individual radiant tubes…". GroundTruth-Tags.xlsx states the tag
  mapping directly: `1HA Pass1 = 01TI1001~48`, and Pass1's feed = `01FC0205` = #A.
- **Dense tube→pass = tube number in blocks of 48** (1–48→A … 145–192→D), aligned
  to feed letters. Validated three ways: spreadsheet statement, feed-tag #A=Pass1,
  and **max observed tube number = 192 = 4×48**. (Earlier draft used width 50 and
  flagged the mapping unverified — corrected: width is 48 and it's confirmed.)
- **CORRECTION — coverage is COMPLETE, not 9%.** An intermediate claim here said
  only 127/1344 tube TCs are historized with some passes empty. That was a
  **catalog bug**: the `tube_COT` rule keyed on the description text `TUBE CUR COT`
  (127 tags), but **1217 more tube tags have BLANK descriptions**. Sweeping by ID
  pattern `01TI{F}{NNN}A.PV` + checking the events table shows **all 192 tubes ×
  7 furnaces = 1344, with ~1/min Good data from 2025-02-05**, value range
  ~620–960 °C. Fixed: catalog now keys `tube_COT` on the ID (furnace = id digit,
  tube = NNN), excluding 24 bearing TIs (share the id space, tube#>192) and the
  duplex `…B.PV` TCs (tubes 12 & 25). `summarize_passes` now shows 48/48/48/48.
- **Validation — we can reproduce the DCS pass-average.** There is **no DCS
  Delta/Delta-Delta tag** in the historian (searched all 4119 tags; KBR data-ask),
  but the DCS **pass-average COT** is (`TIC{100/200/300/400}{A–G}`, 4/furnace).
  Our reconstructed pass-average (mean of the 48 tubes) vs the DCS tag:
  **bias ≈ 0.0 °C, std ~0.5 °C, corr 0.996–1.000** across 1HA/1HB/1HC passes
  (one mild outlier 1HB-D +4.8 °C constant offset). With the earlier 127-subset
  the bias was ±2–20 °C — purely sampling. So Delta/Delta-Delta can be
  reconstructed to match the DCS definition exactly.
- **Methodology — Delta reference = PASS AVERAGE (decided & implemented).** KBR
  (and our `delta_delta_report-7.pdf`) define Delta vs the pass average; this is
  now the **single definition used throughout** — `features` and `cli` always
  call `compute_delta(.., tube_pass=…)`; the furnace pack mean is only a
  no-pass-map fallback. All 7 furnaces regenerated on this definition.
- **DCS thresholds (from KBR doc, closes a TODO):** Delta-Delta pre-alarm 30 °C,
  alarm 45–50 °C; +20 °C no further duty increase; +30 °C raise S/O & drop COT
  5 °C on the affected pass; +45 °C steam-air decoke; single tube >10 °C = fouling.
- **Threaded pass through the code:** catalog gains a `pass` column +
  `ids_for_pass`/`tube_pass_map`/`summarize_passes`; `deltadelta.compute_delta`
  takes an optional pass-average reference + `per_pass_health`/`worst_pass`;
  `features` adds `feed_<P>`,`steam_<P>`,`steam_hc_<P>`,`steam_hc_spread`,
  `dd_abs_max_<P>`,`pass_imbalance`,`worst_pass`; new `plots.plot_pass_health`
  (`*_06_pass_health.png`).

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
