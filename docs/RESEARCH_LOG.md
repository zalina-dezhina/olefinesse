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

### 2026-06-22 — Notebook 02 binned correlations by 5-day run phase (1HA)

**Notebook created:** `notebook_02_binned_correlations.ipynb`

**Method — Harry's phase-bin approach:**
Split each run's clean analysis window (from `output/run_analysis_windows.csv`) into consecutive
5-day phase bins. For each bin, compute Spearman rank correlation between every driver and
`dd_abs_max`. Compare trajectories across bins to separate causal from feedback effects.

**Rationale:** Whole-run correlations mix two signals: (1) physics — the causal effect of
operating conditions on coking rate; (2) operator feedback — corrective actions taken *because*
coking is worsening. Early bins (days 0–5, 5–10) capture the causal signal; late bins (15+)
are increasingly dominated by feedback. A driver with stable correlation across phases is causal;
one that strengthens or reverses sign in later phases is partly or wholly a feedback artefact.

**`coil_out_P` excluded throughout** (frozen sensor, see 2026-06-22 tag inspection entry).
**`eff_*` excluded** (unreliable GC). **`dd_p95`, `delta_spread`, `coking_rate`** excluded (collinear with target).

**Expected causal pattern (to verify against actual results):**
- `cot` → positive early (severity drives coking), may weaken/reverse late (operators back off)
- `steam_hc` → negative early (more dilution = less coking), likely reinforces late (operators add steam when DeltaDelta rises)
- `feed_C5p` → positive and stable across all phases (heavier NGL always cokes more; operators cannot change feed composition)
- `run_age_days` → positive throughout (monotonic accumulation); stable within each 5-day window
- `steam_hc_spread` → positive if pass imbalance causes localised coking (pass with least steam cokes first)

**Classification rules (automated, see notebook cell 8):**
- `causal` — |ρ₀| ≥ 0.10, significant (p<0.05), same sign in phases 0 & 1
- `feedback_reinforcement` — |ρ_late| > |ρ_early| + 0.10, same sign
- `spurious_reversal` — sign flips between early and later phases
- `weak` — |ρ| < 0.10 in all phases

**Output files (fill in after running):**
- `output/1HA_02_binned_correlations.csv` — tidy table: phase_bin × driver × rho/pval/n
- `output/1HA_02_driver_classification.csv` — one row per driver with causal/feedback class
- `output/1HA_02_corr_heatmap.png` — main visualization (driver × phase, colored by ρ)
- `output/1HA_02_corr_trajectory_primary.png` — ρ trajectory for key levers (COT, steam/HC, feed, C5+)
- `output/1HA_02_corr_per_pass_steam_hc.png` — per-pass steam/HC trajectories
- `output/1HA_02_driver_classification.png` — colour-coded classification strip

**Actual results (fill in after running the notebook):**
- _(copy from notebook Cell 9 printed output)_

**Implication for notebook_03:** The `causal` driver set from this analysis becomes the clean
feature input for the Delta-Delta forecaster / run-level regression in notebook_03.

---

### 2026-06-22 — Notebook 01 tag inspection + analysis window detection (1HA)

**Notebooks created:**
- `notebook_01_tag_inspection.ipynb` — tag health check + run boundary analysis for one furnace.
  Run per-furnace (change `FURNACE` in cell 2), uses `.venv` kernel in VS Code. Parametrised with
  `parameters` tag for papermill batch runs (`bash run_all_furnaces.sh`).
- `notebook_00_fleet_summary.ipynb` — fleet aggregation; run after all 7 furnaces complete.

**Run windows — 1HA (16 runs, Feb 2025 – Mar 2026):**
- Typical clean window: 17–21 days after warmup/tail trimming. All 16 settled automatically.
- Warmup criteria: feed_total > 95% run median AND rolling std(COT) < 2 °C / 4 h AND t ≥ run.start + 12 h.
- End criterion: last timestamp where feed_total > 95% run median.
- **Suspicious runs requiring DCS verification:**
  - Run 2 (Apr 28–May 17): warmup = 147 h — slow/interrupted startup, check DCS Apr 28–May 4 2025
  - Run 4 (Jun 8–Jun 29): warmup = 145 h — same pattern, check DCS Jun 8–14 2025
  - Run 8 (Sep 8–Oct 2): tail = 45.5 h — 2-day feed reduction before decoke
  - Run 11 (Nov 19–Dec 12): tail = 195 h — major event, likely partial shutdown Nov 20–Dec 4 2025
  - Run 12 (Dec 13–Jan 1): warmup = 41.5 h — slow restart after Run 11 event
- Output: `output/run_analysis_windows.csv` — shared input for all subsequent notebooks.

**Tag health — 1HA (222 tags inspected):**
- **`coil_out_P` (01PI1404, 01PI1401): EXCLUDE from all analysis.** Both sensors flat 93% of
  the time (vmin=0, vmax≈1.9 kg/cm², mean≈0.6). Frozen or offline. Do not use in correlations.
- **2 tube TCs with negative vmin:** `01TI1131A.PV` (−59 °C) and `01TI1157A.PV` (−55 °C).
  Offline-period artefacts. Already dropped by `compute_delta()` (< ONLINE_TEMP_C = 500 °C).
  No code change needed; document for awareness.
- **feed_flow Pass A (01FC0205): 45 gaps** vs 20–21 for passes B/C/D. More data outages on
  Pass A. Monitor when computing feed_total sums.
- All other 218 tags: no systematic zeros, no spikes, no flat lines. Data quality good.

**Spike filter (dd_abs_max):**
- Threshold: > 60 °C AND duration < 3 h → NaN (not deleted). Physical basis: coking builds
  over days, cannot jump 60 °C and recover in a single 30-min bucket.
- **6 transient spikes removed** (Jul, Sep, Nov 2025, Jan 2026) — confirmed single-reading faults.
- **1 spike kept** (~120 °C, Oct/Nov 2025, Run 9) — lasted > 3 h. Needs manual DCS check:
  real coking peak vs sustained TC fault.
- Harry's "don't overclean" principle respected: filter targets physically impossible events only;
  real high-DD periods (lasting days) pass through untouched.

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
