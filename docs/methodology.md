# Methodology

## 1. Delta-Delta reconstruction

The DCS-calculated Delta tags are not exposed in the historian, so Delta-Delta is
reconstructed from raw per-tube coil-outlet skin thermocouples (the fallback the
KBR/INSITE value-prop note prescribes).

For furnace *f* with tubes *i* and time *t*:

```
Delta_i(t)       = COT_i(t) − ref_i(t)                 # deviation from reference
baseline_i(run)  = mean_{t in first 12 h of run} Delta_i(t)
DeltaDelta_i(t)  = Delta_i(t) − baseline_i(run(t))     # run-normalised drift
```

Tubes reading below 500 °C (offline / dead TC) are dropped from the reference so
they cannot bias Delta. The baseline is re-snapshotted at the start of **every**
run, mirroring the DCS "start-of-run" reset after a decoke.

**Reference = the PASS average** (KBR control doc; and our own
`delta_delta_report-7.pdf`: *"deviation … from its pass average"*). The feature
and CLI pipelines compute `ref_i = mean of tube i's pass` via
`compute_delta(cot, active, tube_pass=…)` — the single definition used
throughout. The tube→pass map is ground-truth-validated (48 tubes/pass) and all
192 tubes/furnace are available, so the pass average is computed over the full
population and matches the DCS pass-average COT to ~0 °C. (The furnace pack mean
is only a fallback when no pass map is supplied — not used in the pipeline.)

Health indicators (operator-facing scalars): `dd_abs_max` (largest |DeltaDelta|
across tubes — the decoke-trigger proxy), `dd_p95`, `delta_spread`, and the
`coking_rate` = smoothed d(`dd_abs_max`)/dt in °C/day.

## 2. Run / decoke segmentation — the key subtlety

A **decoke does not cool the furnace**: coke is burned off the coils with
steam/air while firing continues, so the tube COTs stay hot throughout. A
temperature-only "online" mask therefore merges many runs into one (we observed
43–195 day "runs" this way — wrong).

Decokes are detected from the **hydrocarbon feed being cut to ~0** while the box
stays hot (`cracking_mask`: feed > 30 % of running level AND tubes hot). A *run*
is a contiguous cracking campaign; gaps ≥ 6 h split runs, blips < 6 h do not.
This yields the documented **~17–25 day** runs.

## 3. Feature matrix

`features.build_feature_matrix` time-aligns every role into one 30-min-bucketed
table per furnace: severity levers (`cot`, `feed_total`, `steam_hc`,
`resid_proxy`, `coil_out_P`, `draft`, `feed_coilT`), NGL feed quality
(`feed_C2H6/C3H8/C4H10/C5p/CO2`), furnace response (`tube_cot_mean`,
`dd_abs_max`, `dd_p95`, `delta_spread`, `coking_rate`), effluent yield
(`eff_C2H4/C3H6/CH4/…`), and run structure (`run_id`, `run_age_days`).

**Residence-time proxy.** Absolute coil residence time needs coil geometry we do
not have. We use a monotonic relative proxy: `resid_proxy = 1 / (feed_NM3h +
steam_NM3h)`, with steam converted KG/H→NM3/H via 22.414/18.015. Higher total
volumetric throughput ⇒ shorter residence time.

## 4. Correlation analysis

All correlations are computed over **cracking periods only** (offline/decoke rows
excluded). Three views:

1. **Correlation matrix** — Spearman (robust to the non-linear, monotonic
   relationships typical of coking) across all operating variables.
2. **Driver→target ranking** — Pearson & Spearman of each driver against
   `coking_rate` and `dd_abs_max`, sorted by |Spearman|.
3. **Lagged cross-correlation** — corr of driver(t) vs response(t+lag) to expose
   response/GC latency (a severity move shows up in Delta-Delta after a delay).

### What the data shows (furnace 1HA, 2025-02→2026-03)

`dd_abs_max` (furnace health) is driven, in rank order, by **run age (+)**,
**feed C5+ (+)**, **CO2 (−)**, **COT/severity (+)**, and **steam/HC ratio (−)** —
the textbook coking relationships: ageing, heavier feed and higher severity raise
coking; steam dilution suppresses it. Magnitudes are modest (|ρ| ≲ 0.4) because
operators hold conditions in a narrow band (the "conservative operation" the
workshop noted) and run age dominates within a run.

## 5. Caveats / next steps

- Single-furnace correlations conflate run-age with operating choices; a proper
  forecaster should model DeltaDelta(run_age) **conditioned on** the levers, and
  pool across the 7 furnaces' overlapping trajectories.
- Effluent GC is unreliable (see data dictionary) — prefer it only where it
  varies; weight lab data when available.
- `coking_rate` (instantaneous derivative) is noisy; per-run coking *slope*
  (`features.per_run_summary`) is the more stable response for cross-run analysis.
