# olefinesse — Claude Code project brief

This repo is the `olefins_ddf` Python package for NGL cracking furnace health analysis at Indorama Eleme.
It connects to Databricks, reads a 6.6 billion-row historian events table, and produces a feature matrix
of operating conditions + Delta-Delta health signals across 7 furnaces (1HA–1HG).

## Pipeline order

```
config.py → catalog.py → io_events.py → runs.py → deltadelta.py → features.py → correlations.py → plots.py
```

CLI entry point: `python -m olefins_ddf furnace|fleet|coverage`

## Environment variables

| Variable | What it is | Action needed |
|---|---|---|
| `DDF_CLUSTER_ID` | Databricks cluster ID | Update when cluster restarts (`databricks clusters list`) |

Current default cluster: `0612-154022-0181931u` — hardcoded in `config.py` as fallback only.
Always prefer the env var. The cluster ID changes every restart.

## Critical domain rules (always apply these)

1. **Filter to cracking periods before any correlation or analysis.**
   Use `feat[feat["cracking"]]` or `feat_crk = feat[feat["cracking"]]`.
   Decoke periods are noise — they will corrupt correlations if included.

2. **Decoke detection uses HC feed drop, not temperature.**
   A decoke does NOT cool the furnace. Do not use temperature to identify decoking periods.
   `runs.cracking_mask(feed_total, cot)` is the authoritative filter.

3. **Delta-Delta is pass-referenced, not furnace-referenced.**
   `Delta_i(t) = COT_i(t) − mean(pass-mates)` — within-pass deviation only.
   The furnace mean is NOT used. This removes pass-level operating offsets.

4. **Never download raw rows from the events table.**
   Always filter to specific tag IDs + time window + `Status='Good'` on the Spark side
   before pulling to pandas. The table has 6.6 billion rows.

5. **Run lengths are NOT a fixed 25 days.**
   Fleet median ~22 days, range ~5–31 days. Do not assume fixed run duration.

## Known data quality issues

- **Effluent GC (`eff_C2H4`, `eff_C3H6`, etc.) is unreliable.** Treat yield columns with caution.
  Do not draw conclusions from them without manual verification.
- **Tube TC value = 0 means the sensor is offline, not 0 °C.** `compute_delta` drops these automatically
  (`c > ONLINE_TEMP_C` filter), but watch for them in raw data.
- **Tag descriptions in DCS are inconsistent** — some blank, some with typos (e.g. `HIE` instead of `H1E`).
  Always use `catalog.py` as the translation layer. Do not parse tag names directly.
- **Dense per-tube TCs (192/furnace) only available from 2025-02-05.**
  Before that date, use `--long-history` flag (8-tube proxy, available from 2019-01-01).

## Key findings already established (do not re-derive)

- COT leads `dd_abs_max` by **~17–23 hours** (confirmed via lagged cross-correlation).
- Coking drivers: `run_age` (+), `feed_C5p` (+), `COT` (+), `steam_hc` (−) — textbook pattern.
- All 192 tubes/furnace ARE in the historian (early catalog bug previously showed only 127).
- Pass-average COT reconstruction matches DCS to ~0 °C bias, 0.996 correlation.
- The negative correlation between `steam_hc` and `dd_abs_max` at negative lag is a **confounder**:
  operators increase steam when health degrades. Restrict to run-start windows to isolate causal effect.

## Output files

All figures and data saved to `output/`. Key files:
- `output/dd_tag_catalog.csv` — cached tag catalog (pass `refresh=True` to rebuild)
- `output/1HA_features.parquet` — cached feature matrix for furnace 1HA
- `output/run_summary.csv` — per-run summary table
- `output/1HA_04_dd_trajectories.png` — run trajectory library (look here first)
- `output/1HA_09_xcorr_cot_dd_abs_max.png` — the COT→ΔΔ lag plot

## Recommended first steps in any new session

```python
from olefins_ddf.io_events import get_spark
from olefins_ddf import catalog as cat, features, correlations

spark = get_spark()                          # uses DDF_CLUSTER_ID env var
catalog = cat.build_catalog(spark)           # loads from cache unless refresh=True
feat, runs = features.build_feature_matrix(spark, catalog, "1HA",
                 start="2025-02-05", end="2026-03-20", bucket=30)
feat_crk = feat[feat["cracking"]]            # ALWAYS filter first
```

## Project log

Non-obvious findings, decisions, and dead ends are tracked in `docs/RESEARCH_LOG.md`.
Add a dated entry there after any new discovery or modelling decision.
