# Codebase Guide — `olefins_ddf` package
### What every file does, how to use it, and how it maps to your action items

---

## How the package fits together

```
config.py        ← cluster IDs, table names, furnace list (the "settings" file)
    ↓
catalog.py       ← discovers all 4119 DCS tags → labels them by role + furnace + pass
    ↓
io_events.py     ← queries the 6.6 B-row Databricks events table → returns a clean wide DataFrame
    ↓
runs.py          ← detects decoke events → segments timeline into individual runs
    ↓
deltadelta.py    ← computes Delta → Delta-Delta → health indicators (dd_abs_max, coking_rate)
    ↓
features.py      ← assembles everything into one tidy 30-min table per furnace (the "feature matrix")
    ↓
correlations.py  ← Spearman/Pearson correlation matrix, driver rankings, lagged cross-correlation
    ↓
plots.py         ← all figures (11 plot types) → saved to output/
    ↓
cli.py           ← command-line entry point: `python -m olefins_ddf furnace|fleet|coverage`
```

---

## File-by-file breakdown

---

### `config.py` — Settings & constants

**What it does:** Single place to set the Databricks cluster ID, catalog name, furnace list, and date ranges. Everything else imports from here.

**Key variables:**

| Variable | Value | What it means |
|---|---|---|
| `CLUSTER_ID` | `"0612-154022-0181931u"` | The running Databricks cluster. **Changes when the cluster restarts** — update with `databricks clusters list` and set `DDF_CLUSTER_ID` env var. |
| `CATALOG` | `indorama_corporate_olefins_paas_azure_weu_dev_bronze` | The Unity Catalog holding all the historian data |
| `FURNACES` | `["1HA".."1HG"]` | All 7 furnaces |
| `HIST_START` | `2019-01-01` | How far back process drivers go |
| `DENSE_TC_START` | `2025-02-05` | When dense per-tube TCs became available |

**Your action items using this file:**
- When Databricks cluster changes, update `DDF_CLUSTER_ID` environment variable (or change the default here).

---

### `catalog.py` — Tag discovery & labelling

**What it does:** Reads the `timeseries.metadata` table (4119 tags) and applies pattern-matching rules to assign each tag a **role** (e.g. `tube_COT`, `feed_flow`, `dil_steam`) and a **furnace** (1HA–1HG or PLANT). Also assigns each tag a **pass** (A–D) where applicable.

**Why it matters:** The tag descriptions are inconsistent (some blank, some with typos like `HIE` instead of `H1E`). The catalog is the decoded translation layer — without it you can't identify which tag is which.

**Key roles it discovers:**

| Role | What it is | Tags / furnace |
|---|---|---|
| `tube_COT` | Per-tube skin TCs (Delta-Delta source) | 192/furnace, 48/pass, from 2025-02 |
| `tube_COT_long` | Sparse 8-tube proxy (longer history) | 8/furnace, from 2019 |
| `feed_flow` | HC feed per pass | 4/furnace (one per pass) |
| `dil_steam` | Dilution steam per pass | 4/furnace |
| `decoke_air` | Decoke-air per pass | 4/furnace |
| `cot_ctrl` | COT controller (severity lever) | 1/furnace |
| `feed_GC` | NGL feed composition | Shared (PLANT) |
| `effluent_GC` | Ethylene/propylene/methane yield | 1/furnace (sparse, A–F only) |

**Key functions:**

| Function | What it does |
|---|---|
| `build_catalog(spark)` | Builds the catalog from metadata (or loads cached CSV from `output/dd_tag_catalog.csv`). Pass `refresh=True` to force re-read. |
| `tags_for(catalog, furnace)` | Get all tags for one furnace |
| `ids_for(catalog, furnace, role)` | Get tag ID list for one role (e.g. `"feed_flow"`) |
| `ids_for_pass(catalog, furnace, role, pass_)` | Same but filtered to one pass (`"A"–"D"`) |
| `tube_pass_map(catalog, furnace)` | `{tube_tag_ID → pass_letter}` — used to compute pass-average Delta |
| `summarize(catalog)` | Count of tags per furnace/role — the instrumentation map |
| `summarize_passes(catalog)` | 48/48/48/48 per furnace/pass — verifies full coverage |

**Your action items using this file:**
- Run `cat.summarize(catalog)` to check which tags are available for a furnace.
- Run `cat.summarize_passes(catalog)` to verify all 48 tubes per pass are present.
- Use `cat.ids_for(catalog, "1HA", "feed_flow")` when you want to inspect feed tags manually.

---

### `io_events.py` — Load data from Databricks

**What it does:** Pulls tag history from the 6.6 billion-row events table via Spark SQL. Buckets data into fixed time intervals (default 15-min), averages, pivots to a wide DataFrame (one column per tag), and fills gaps with NaN.

**Key rule:** Never download raw rows — always filter to specific tags + time window + `Status='Good'` on the Spark side before bringing data across to pandas. This keeps memory manageable.

**Key functions:**

| Function | What it does |
|---|---|
| `get_spark(cluster_id)` | Opens a databricks-connect Spark session |
| `load_wide(spark, tag_ids, start, end, bucket_minutes=15)` | Returns a time-indexed wide DataFrame with one column per tag, bucketed to fixed intervals |
| `coverage(spark, tag_ids, by_year=True)` | Returns sample counts per tag per year — the "how much data do I have?" answer |

**Your action items using this file:**
- Use `io_events.load_wide(spark, ids, "2025-02-05", "2026-03-20", bucket_minutes=30)` to load any set of tags for visual inspection.
- Use `coverage(spark, tag_ids, by_year=True)` to check data availability for a specific tag.

---

### `runs.py` — Decoke detection & run segmentation

**What it does:** Detects when a furnace is in a cracking run vs. a decoke. The critical insight: **a decoke does NOT cool the furnace** (coke is burned with steam/air while firing continues), so temperature alone cannot separate runs from decokes. Instead, decokes are detected by the **HC feed dropping to ~0**.

**Key outputs:**

| Object/function | What it produces |
|---|---|
| `cracking_mask(feed_total, cot)` | Boolean series — True where the furnace is cracking |
| `segment_runs(mask)` | List of `Run` objects, each with `start`, `end`, `length_days` |
| `run_age_days(index, runs)` | Float series — "how many days since start of this run" |
| `run_id_series(index, runs)` | Integer series — which run each timestamp belongs to |
| `run_table(runs, furnace)` | DataFrame summary of all runs with start/end/length |

**Key finding already in the data:** Runs are NOT a fixed 25 days. Fleet median is ~22 days; range is ~5–31 days. This matters for modelling.

**Your action items using this file:**
- Use `runs.segment_runs(cracking_mask)` to produce run boundaries for any furnace.
- Use `run_age_days()` to create the "time since start of run" axis for your binned correlation analysis.
- Inspect `run_table(runs, "1HA")` to see the actual run inventory — start/end dates and lengths.

---

### `deltadelta.py` — Delta and Delta-Delta computation

**What it does:** Reconstructs the health signal that operators use to decide when to decoke.

**The maths:**
```
Delta_i(t)        = COT_i(t) − pass_average_COT(t)        # per-tube deviation
baseline_i        = mean of Delta_i in first 12h of run    # start-of-run reference
DeltaDelta_i(t)   = Delta_i(t) − baseline_i               # drift since run start
```

**Key functions:**

| Function | What it does |
|---|---|
| `compute_delta(cot, active, tube_pass)` | Computes Delta (tube vs pass average). `tube_pass` is the `{tag → pass}` dict from `catalog.tube_pass_map`. Drops dead TCs (below 500 °C). |
| `compute_delta_delta(delta, runs)` | Re-baselines Delta at start of each run → Delta-Delta |
| `health_indicators(delta, dd)` | Returns `dd_abs_max` (worst tube — the decoke trigger), `dd_p95`, `delta_spread` as a DataFrame |
| `per_pass_health(dd, tube_pass)` | `dd_abs_max_A`, `dd_abs_max_B`, `dd_abs_max_C`, `dd_abs_max_D` — worst tube per pass, plus `pass_imbalance` |
| `worst_pass(per_pass)` | Which pass is worst at each timestamp |
| `coking_rate(dd_health, runs)` | Smoothed d(dd_abs_max)/dt in °C/day — the rate of worsening |

**Your action items using this file:**
- `health_indicators` gives you `dd_abs_max` — the signal to correlate with drivers.
- `per_pass_health` tells you which pass is coking fastest — needed for your spatial analysis.
- `coking_rate` is the "rate of change of Delta-Delta" Harry asked you to analyse vs severity parameters.

---

### `features.py` — The feature matrix (your main working table)

**What it does:** Assembles ALL signals — severity levers, feed quality, Delta-Delta health, per-pass breakdowns, run structure — into a single time-indexed DataFrame with one row per 30-min bucket. This is the table you run correlations on.

**Column groups in the feature matrix:**

| Group | Columns | What they represent |
|---|---|---|
| Severity levers | `cot`, `feed_total`, `steam_total`, `steam_hc`, `resid_proxy`, `coil_out_P`, `draft`, `feed_coilT` | What operators control |
| Feed quality | `feed_C2H6`, `feed_C3H8`, `feed_C4H10`, `feed_C5p`, `feed_CO2` | What comes in from the NGL plant |
| Health signals | `dd_abs_max`, `dd_p95`, `delta_spread`, `coking_rate`, `tube_cot_mean` | How the furnace is doing |
| Yield | `eff_C2H4`, `eff_C3H6`, `eff_CH4`, `eff_C2H6`, `eff_C3H8` | What comes out (treat cautiously — GC is unreliable) |
| Per-pass levers | `feed_A/B/C/D`, `steam_A/B/C/D`, `steam_hc_A/B/C/D`, `steam_hc_spread` | Per-pass breakdown of throughput and steam |
| Per-pass health | `dd_abs_max_A/B/C/D`, `pass_imbalance`, `worst_pass` | Which pass is coking fastest |
| Run structure | `run_id`, `run_age_days`, `cracking`, `furnace` | Time-within-run labelling |

**Key functions:**

| Function | What it does |
|---|---|
| `build_feature_matrix(spark, catalog, furnace, start, end, bucket=30)` | Returns `(feat_df, runs)` — the full feature matrix + run list |
| `per_run_summary(feat, runs)` | One row per run: mean operating conditions + coking outcome (slope). The cross-run table for answering "which feed quality leads to faster coking?" |

**Your action items using this file:**
- `build_feature_matrix` is your main entry point. Run it for one furnace first (1HA).
- Use `feat[feat["cracking"]]` to filter to cracking-only periods before any correlation.
- Use `feat.groupby(pd.cut(feat["run_age_days"], bins=[0,5,10,15,20,25]))` to bin by run phase (Harry's 5-day bin suggestion).
- `per_run_summary(feat, runs)` gives you the cross-run table to check if any parameters correlate with total run length.

---

### `correlations.py` — Spearman correlations and lag analysis

**What it does:** Three types of correlation analysis, all restricted to cracking periods (offline/decoke rows excluded automatically).

**Key functions:**

| Function | What it does |
|---|---|
| `correlation_matrix(feat, method="spearman")` | Full Spearman correlation matrix across all operating variables. Drops NaN/constant columns. |
| `driver_target_corr(feat, target)` | Ranks all drivers by |Spearman| against a chosen target (e.g. `"dd_abs_max"` or `"coking_rate"`). Returns Pearson + Spearman side by side. |
| `lagged_xcorr(feat, x, y, max_lag_steps=96)` | Cross-correlation of `x(t)` vs `y(t+lag)` across a range of lags. Positive lag = x leads y. |
| `best_lag(xc)` | Finds the peak lag from `lagged_xcorr` output |

**Known finding:** COT leads `dd_abs_max` by **~17–23 hours** (positive lag). The negative correlation at negative lag = operators backing off severity when health degrades (operator feedback loop — a confounder!).

**Your action items using this file:**
- Run `driver_target_corr(feat, "dd_abs_max")` and `driver_target_corr(feat, "coking_rate")` to rank which variables matter most.
- Run `lagged_xcorr(feat, "steam_hc", "dd_abs_max")` to investigate the steam confounder Harry discussed — is steam increasing *because* delta is high (at end-of-run), or *causing* delta to decrease?
- Run the correlation matrix on binned sub-frames (`feat[feat["run_age_days"] < 5]`, etc.) to separate spurious from real correlations.

---

### `plots.py` — All figures

**What it does:** Generates and saves 11 types of figures to `output/`. All figures save automatically — call the function and it returns the file path.

**Figure inventory:**

| File produced | Plot function | What it shows |
|---|---|---|
| `{furnace}_01_raw_cot.png` | `plot_raw_cot` | All 192 raw tube skin temperatures over time |
| `{furnace}_02_delta.png` | `plot_delta` | Per-tube Delta (deviation from pass average) |
| `{furnace}_03_delta_delta.png` | `plot_delta_delta` | Per-tube Delta-Delta (drift since run start) — the coking signal |
| `{furnace}_04_dd_trajectories.png` | `plot_dd_trajectories` | One line per run: worst-tube Delta-Delta vs run age. Your "trajectory library". |
| `{furnace}_05_health_vs_drivers.png` | `plot_health_vs_drivers` | `dd_abs_max` + `coking_rate` vs COT, feed, steam/HC |
| `{furnace}_06_pass_health.png` | `plot_pass_health` | Per-pass worst-tube Delta-Delta + per-pass steam/HC |
| `{furnace}_07_corr_heatmap.png` | `plot_corr_heatmap` | Spearman correlation heatmap |
| `{furnace}_08_drivers_of_{target}.png` | `plot_driver_target` | Horizontal bar chart of driver rankings |
| `{furnace}_09_xcorr_cot_dd_abs_max.png` | `plot_lagged_xcorr` | Lag plot: COT vs Delta-Delta (shows the ~20h response lag) |
| `{furnace}_10_pairscatter.png` | `plot_pairscatter` | Scatter plots coloured by run age |
| `{furnace}_11_pass_dd_distribution.png` | `plot_pass_dd_distribution` | Per-pass IQR band of Delta-Delta across all 48 tubes |
| `fleet_health_comparison.png` | `plot_fleet_health` | All 7 furnaces' health on one chart |
| `run_lengths.png` | `plot_run_lengths` | Histogram + Gantt of run lengths (shows runs are NOT 25 days) |
| `data_coverage_by_year.png` | `plot_data_coverage` | Samples/year per tag role — data depth answer |

**Your action items using this file:**
- Look at `_04_dd_trajectories.png` to understand what the trajectory library looks like — this is the shape of the problem you're forecasting.
- Look at `_06_pass_health.png` to see if pass D or another pass consistently cokes faster.
- Look at `_09_xcorr_cot_dd_abs_max.png` to see the lagged correlation Harry discussed.

---

### `cli.py` — Command-line entry point

**What it does:** Wires together catalog → data load → feature matrix → plots → save. Three commands:

| Command | What it runs |
|---|---|
| `python -m olefins_ddf furnace --furnace 1HA` | Full analysis + all 11 plots for one furnace |
| `python -m olefins_ddf fleet` | All 7 furnaces: health ranking + run-length stats + fleet plots |
| `python -m olefins_ddf coverage --furnace 1HA` | Data depth report (samples/year per tag) |

**Useful flags:**

| Flag | Effect |
|---|---|
| `--start 2025-02-05 --end 2026-03-20` | Date window (defaults already set) |
| `--bucket 30` | Time bucket in minutes (default 30) |
| `--long-history` | Use the 8-tube 2019+ proxy instead of dense TCs → 104 runs vs 16 |
| `--refresh-catalog` | Force re-read of metadata (needed if tags change) |

---

### Documents

---

### `docs/data_dictionary.md` — Tag reference

Your go-to when you see a tag ID and want to know what it measures. Covers:
- The full DCS numbering schemes (3 different systems decoded)
- Every tag role with example IDs, units, and history start dates
- The topology: furnace → 4 passes → 48 tubes → 192 tubes/furnace
- Known data quality caveats (effluent GC is unreliable; Value=0 on a tube TC means offline, not 0 °C)

**Use it when:** A tag ID appears in the data and you don't know what it is.

---

### `docs/methodology.md` — How the maths works

Explains: how Delta-Delta is reconstructed (formula + why pass average, not furnace mean), how decokes are detected (feed cut, not temperature), how the feature matrix is built, and what the correlation analysis has found so far.

**Use it when:** You need to justify a modelling decision or explain the approach to Harry or a customer.

---

### `docs/RESEARCH_LOG.md` — Running project memory

This is the most important document for day-to-day work. It records every non-obvious finding, decision, and dead end — with dates. Because every Databricks session starts fresh with no memory, this is the "what did we already learn" file.

**Key findings already logged:**
- Run lengths are 17–25 days, NOT a fixed 25 (confirmed June 12)
- All 192 tubes/furnace ARE in the historian (a catalog bug previously made it look like only 127 were available)
- Pass-average reconstruction matches DCS to ~0 °C bias, 0.996 correlation
- COT leads Delta-Delta by ~17–23 hours (discovered via lagged cross-correlation)
- Coking drivers confirmed: run_age (+), C5+ feed (+), COT (+), steam/HC (−) — textbook

**Use it when:** Starting a new Databricks session, or before a meeting with Harry, to remind yourself what's already known.

**Important:** Add a dated entry here whenever you discover something new, make a decision, or hit a dead end.

---

## How to map all of this to your action items

| Your action item | Which file(s) to use | Specific function / command |
|---|---|---|
| **Understand each tag, find flat lines and spikes** | `catalog.py` + `io_events.py` | `build_catalog(spark)` → `ids_for(catalog, "1HA", "tube_COT")` → `load_wide(spark, ids, start, end)` → plot each tag |
| **Check data coverage for each tag** | `io_events.py` + `cli.py` | `python -m olefins_ddf coverage --furnace 1HA` or `io_events.coverage(spark, tag_ids, by_year=True)` |
| **Remove decoking periods** | `runs.py` | `cracking_mask(feed_total, cot)` → use as filter in any analysis |
| **Bin correlations by run phase (5-day windows)** | `features.py` + `correlations.py` | `build_feature_matrix(...)` → `feat.groupby(pd.cut(feat["run_age_days"], bins=[0,5,10,15,20]))` → `correlation_matrix()` within each bin |
| **Investigate steam ratio as confounder** | `correlations.py` | `lagged_xcorr(feat, "steam_hc", "dd_abs_max")` + restrict to first 5-day bin |
| **Identify which drivers matter most** | `correlations.py` + `plots.py` | `driver_target_corr(feat, "dd_abs_max")` → `plot_driver_target(dtc, "dd_abs_max", "1HA")` |
| **Analyse rate of change of Delta-Delta** | `deltadelta.py` + `correlations.py` | `coking_rate(health["dd_abs_max"], runs)` already in feature matrix as `coking_rate` → `driver_target_corr(feat, "coking_rate")` |
| **Check which pass cokes fastest (spatial analysis)** | `features.py` + `plots.py` | `dd_abs_max_A/B/C/D` columns already in feature matrix → `plot_pass_health(feat, runs, furnace)` |
| **Run length sanity check** | `features.py` + `runs.py` | `per_run_summary(feat, runs)` → correlate `length_days` with mean `cot`, `steam_hc`, `feed_C5p` |
| **Run analysis for all 7 furnaces** | `cli.py` | `python -m olefins_ddf fleet` |
| **Use long history (2019+) for more run examples** | `cli.py` | `python -m olefins_ddf furnace --furnace 1HA --long-history --start 2019-01-01` |
| **Prepare for Thursday whiteboard** | `docs/RESEARCH_LOG.md` + `docs/methodology.md` | Read both; also look at `_04_dd_trajectories.png` and `_09_xcorr_cot_dd_abs_max.png` |
| **Update project memory after each session** | `docs/RESEARCH_LOG.md` | Add a dated entry with any new finding or decision |

---

## Quick-start sequence (recommended order for your EDA)

```python
# 1. Connect to Databricks
from olefins_ddf.io_events import get_spark
from olefins_ddf import catalog as cat, features, correlations, plots

spark = get_spark()   # set DDF_CLUSTER_ID if cluster changed

# 2. Build (or load cached) tag catalog
catalog = cat.build_catalog(spark)
print(cat.summarize(catalog))           # tag counts per furnace/role
print(cat.summarize_passes(catalog))    # should show 48/48/48/48 per pass

# 3. Build feature matrix for one furnace
feat, runs = features.build_feature_matrix(
    spark, catalog, "1HA",
    start="2025-02-05", end="2026-03-20", bucket=30
)

# 4. Filter to cracking-only periods
feat_crk = feat[feat["cracking"]]

# 5. Inspect raw data for a single tag to check for anomalies
from olefins_ddf.io_events import load_wide
tube_ids = cat.ids_for(catalog, "1HA", "tube_COT")[:5]  # first 5 tubes
raw = load_wide(spark, tube_ids, "2025-02-05", "2026-03-20", bucket_minutes=15)
raw.plot(figsize=(14, 4), lw=0.4, alpha=0.7)             # look for flat lines / spikes

# 6. Run correlation analysis
corr = correlations.correlation_matrix(feat_crk)
plots.plot_corr_heatmap(corr, "1HA")

dtc = correlations.driver_target_corr(feat_crk, "dd_abs_max")
plots.plot_driver_target(dtc, "dd_abs_max", "1HA")

# 7. Binned correlation (5-day windows)
import pandas as pd
feat_crk["run_phase"] = pd.cut(feat_crk["run_age_days"], bins=[0,5,10,15,20,25,35])
for phase, g in feat_crk.groupby("run_phase"):
    if len(g) > 50:
        c = correlations.driver_target_corr(g, "dd_abs_max")
        print(f"\n--- Run phase {phase} ---")
        print(c[["driver","spearman"]].head(5))

# 8. Lagged cross-correlation (steam confounder check)
xc = correlations.lagged_xcorr(feat_crk, "steam_hc", "dd_abs_max")
plots.plot_lagged_xcorr(xc, "steam_hc", "dd_abs_max", "1HA", step_min=30)

# 9. Run length sanity check
run_sum = features.per_run_summary(feat, runs)
print(run_sum[["run","length_days","cot","steam_hc","feed_C5p","coking_slope_Cpd"]])
```
