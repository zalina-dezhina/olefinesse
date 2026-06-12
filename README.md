# olefinesse — Delta-Delta furnace-health research

R&D for the Indorama / KBR olefins engagement: data validation and model
development around **Delta-Delta**, the run-normalised tube-skin-temperature
drift operators use as the cracking-furnace health / coking signal.

The headline KPI is ethylene yield per ton of feed. The route to it runs through
the seven cracking furnaces (1HA–1HG). Delta-Delta is the operational observable
of furnace coking that bounds severity, throughput and run length; forecasting it
is the project's first deliverable (a forecaster + what-if tool), with yield
optimisation as a later phase constrained by the forecast. Background docs are in
[`context/`](context/); the argument is summarised in
[`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

## Repository layout

```
olefins_ddf/            the package (run with `python -m olefins_ddf` from repo root)
  config.py             cluster / catalog / furnace topology
  catalog.py            discover & label furnace tags from the historian metadata
  io_events.py          load tag history from the 6.6 B-row events table (databricks-connect)
  runs.py               run / decoke segmentation (feed-cut based)
  deltadelta.py         Delta, Delta-Delta, health indicators, coking rate
  features.py           unified per-furnace feature matrix + per-run summary
  correlations.py       correlation matrix, driver→target ranking, lagged x-corr
  plots.py              all figures
  cli.py                `python -m olefins_ddf {furnace|fleet|coverage}`
docs/                   methodology, data dictionary, RESEARCH LOG (persistent memory)
output/                 generated figures + tables (gitignored)
context/                source PDFs / spreadsheet / approach notes
```

## Quickstart

Run from the repo root (needs `databricks-connect`, `pandas`, `matplotlib`,
`pyarrow`; no install step). Set `DDF_CLUSTER_ID` if the research cluster changed.

```bash
# one furnace: Delta-Delta + correlation figure set + feature matrix
python -m olefins_ddf furnace --furnace 1HA

# all seven: fleet health ranking, run-length distribution & timeline
python -m olefins_ddf fleet

# historian data-depth report (samples/year/role)
python -m olefins_ddf coverage --furnace 1HA

# reconstruct from the 8-tube proxy back to 2019 instead of dense 2025+ TCs
python -m olefins_ddf furnace --furnace 1HA --long-history --start 2019-01-01
```

If the research cluster id has changed: `databricks clusters list`, then set
`DDF_CLUSTER_ID`.

## Key findings so far

- **Delta-Delta reconstructs cleanly** from raw per-tube skin TCs; each run resets
  to ~0 at decoke then tubes drift apart — the coking signal.
- **Runs are ~17–25 days, not a clockwork 25** (see `output/run_lengths.png`).
- **7 years of driver history (2019+)**; dense tube TCs only from 2025-02, with an
  8-tube proxy extending Delta-Delta back to 2019.
- **Coking drivers are textbook:** furnace health worsens with run age, heavier
  feed (C5+) and severity (COT), and improves with steam dilution.

See [`docs/methodology.md`](docs/methodology.md) and
[`docs/data_dictionary.md`](docs/data_dictionary.md) for detail.
