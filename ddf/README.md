# Delta-Delta analysis toolkit (`ddf`)

Locates the furnace tags relevant to **Delta-Delta forecasting**, pulls their
high-frequency history from the Unity Catalog historian, reconstructs Delta and
Delta-Delta, segments the run/decoke cycle, and plots everything.

## What Delta-Delta is

From the KBR / INSITE 3.0 value-prop note (`context/delta_delta_report-7.pdf`)
and the modelling-approach note (`context/olefins-furnace-approach_revised.docx`):

- **Delta** — deviation of an individual coil's *outlet skin temperature* from
  the furnace pack average at an instant.
- **Delta-Delta** — how that per-tube deviation has *drifted since the start of
  the current run* (the post-decoke baseline). It is the run-normalised
  furnace-health signal operators already use to decide when to decoke. Rising
  |Delta-Delta| ⇒ a tube is preferentially coking / losing flow.

The calculated Delta tags are **not exposed** in the historian (a known open
item with Indorama/KBR), so we reconstruct Delta-Delta from the **raw per-tube
coil-outlet skin thermocouples** plus a start-of-run baseline detected from the
run/decoke cycle — exactly the fallback the note prescribes.

## The data

- Catalog: `indorama_corporate_olefins_paas_azure_weu_dev_bronze`
- `timeseries.events` — ~6.6 B rows, `ID | EventTime | Status | Value (variant)`
- `timeseries.metadata` — 4119-tag dictionary (`ID | Description | UoM | …`)
- Seven furnaces **1HA–1HG** (`H-A … H-G` in the DCS descriptions).

## The tag catalog (per furnace, built by `tags.py`)

Tags are identified by parsing the `Description` field, not tag-number ranges.

| role | description pattern | example | units | what it is |
|------|--------------------|---------|-------|------------|
| `tube_COT` | `H-X TUBE CUR COT` | `01TI1001A.PV` | °C | **per-tube coil-outlet skin TC — the Delta-Delta source** (9–29 tubes/furnace, ~1/min, 2025-02→2026-03) |
| `feed_flow` | `H1X FD #A PASS` | `01FC0205.PV` | NM3/H | hydrocarbon feed per pass — throughput lever + **decoke detector** |
| `dil_steam` | `H1X DS #A PASS` | `01FC0217.PV` | KG/H | dilution steam per pass — sets steam/HC ratio lever |
| `effluent_GC` | `1-H-1X C2H4` | `01AI1421.PV` | WT% | furnace-effluent GC composition — yield-mapping layer (~hourly, 1HA–1HF only) |

The four severity levers from the note (throughput, steam/HC ratio, coil-outlet
temperature, coil pressure) are covered by `feed_flow`, `dil_steam`, and the
tube COTs themselves; coil-outlet pressure tags can be added to `tags.py` if
needed for a what-if model.

## Run/decoke detection — the key subtlety

A decoke does **not** cool the furnace (coke is burned off the coils with
steam/air while firing continues), so the tube COTs stay hot. A decoke is
detected from the **hydrocarbon feed being cut to ~0**, not from temperature.
`cracking_mask()` keys off feed; `segment_runs()` splits into ~17–25-day
campaigns per furnace — matching the documented ~25-day cycle. Delta-Delta
baselines reset at the start of every detected run.

## Usage

```bash
# one furnace, full figure set + per-run summary
python -m ddf.run_analysis --furnace 1HA --start 2025-02-05 --end 2026-03-20

# all seven furnaces + fleet health-ranking plot
python -m ddf.run_analysis --fleet

# data-availability report for a furnace's tags
python -m ddf.run_analysis --coverage --furnace 1HA
```

Outputs land in `../output/`:

- `<F>_01_raw_cot.png` — raw per-tube COTs, decoke gaps shaded
- `<F>_02_delta.png` — per-tube deviation from pack mean
- `<F>_03_delta_delta.png` — per-tube drift since start of run (the health signal)
- `<F>_04_dd_trajectories.png` — every run on a common run-age axis (the
  "trajectory library" a forecaster trains on)
- `<F>_05_health_vs_drivers.png` — health signal vs feed + steam/HC levers
- `<F>_06_yield_vs_dd.png` — effluent ethylene vs health
- `fleet_health_comparison.png` — worst-tube Delta-Delta for all furnaces
- `run_summary.csv`, `dd_tag_catalog.csv`

## Module map

- `config.py` — cluster id, catalog names, furnace list, output dir
- `tags.py` — build the per-furnace tag catalog from `metadata`
- `data.py` — `get_spark`, `load_wide` (server-side bucketed load), `coverage`
- `deltadelta.py` — masks, run segmentation, Delta / Delta-Delta, health indicators
- `plots.py` — the figures
- `run_analysis.py` — CLI driver
