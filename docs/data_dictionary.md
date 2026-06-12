# Data dictionary — olefins historian

## Source

| | |
|---|---|
| Catalog | `indorama_corporate_olefins_paas_azure_weu_dev_bronze` |
| Events | `…timeseries.events` — ~6.6 B rows, EAV: `ID, Source, EventTime, Status, Value (variant), Properties` |
| Metadata | `…timeseries.metadata` — 4119 tags: `ID, Name, UoM, Description, Properties` |
| Access | databricks-connect to the **running cluster** (`DatabricksSession.builder.clusterId(...)`). Plain `pyspark` → `MASTER_URL_NOT_SET`. |

`Value` is a `variant`; always `CAST(Value AS DOUBLE)`. Filter `Status = 'Good'`.
Tube COTs sample ~1/min; the GC analysers ~hourly.

## Furnaces

Seven near-identical crackers **1HA–1HG** (`H-A…H-G`, `H1A…H1G`, `1-H-1A…1-H-1G`
in different description styles). ~17–25 day cracking runs separated by ~1-day
decokes (see methodology — decoke detection).

## DCS numbering schemes (decoded)

The plant uses **three** internal numbering schemes; each is internally
consistent. The furnace is recovered differently per scheme:

| Scheme | Hundreds-block → furnace | Applies to |
|---|---|---|
| A | `08→A 09→B 10→C 11→D 12→E 13→F 14→G` | TI tube TCs (`01TI08xx…14xx`), COT controllers (`01TC0805…1405`), convection draft (`01PC6001/6021/…/6101`) |
| B | `02→A 03→B 04→C 05→D 06→E 07→F 08→G` | feed/steam flow (`01FC02xx…08xx`) |
| C | `14→A 15→B 16→C 17→D 18→E 19→F` | effluent GC (`01AI14xx…19xx`), effluent temp (`01TI1406/1506/…`), effluent/coil-outlet pressure (`01PI1401/1404…`) |

Where the description embeds the furnace (e.g. `H1A FD #A PASS`, `H-1A COT`,
`1-H-1A C2H4`, `FD COIL 1-H-1A`, `EFFL FM 1-E-15A`) the catalog parses it
directly; for the `BANK #x PQE #n` tube TCs the description has no furnace, so
scheme A (number block) is used.

## Tag roles (built by `olefins_ddf.catalog`)

| role | description pattern | example | UoM | history | meaning |
|---|---|---|---|---|---|
| `tube_COT` | `H-X TUBE CUR COT NNN` | `01TI1001A.PV` | °C | **2025-02 →** | dense per-tube coil-outlet skin TC — **Delta-Delta source** (9–29 tubes/furnace) |
| `tube_COT_long` | `BANK #x PQE #5/#8` | `01TI0802.PV` | °C | **2019 →** | sparse per-tube skin TC, 8/furnace (4 passes × pos 5,8) — long-history Delta-Delta proxy |
| `cot_ctrl` | `H-1X COT` | `01TC0805.PV` | °C | 2019 → | controlled coil-outlet temperature — **severity/temperature lever** |
| `feed_flow` | `H1X FD #A PASS` | `01FC0205.PV` | NM3/H | 2019 → | HC feed per pass — **throughput lever + decoke detector** |
| `dil_steam` | `H1X DS #A PASS` | `01FC0217.PV` | KG/H | 2019 → | dilution steam per pass — **steam/HC ratio lever** |
| `coil_out_P` | `EFFL FM 1-E-15X/16X` | `01PI1401.PV` | KG/CM2 | 2019 → | coil-outlet / effluent pressure — **coil-pressure lever** |
| `draft` | `H1X CONV DRAFT` | `01PC6001.PV` | MMH2O | 2019 → | convection draft — firing lever |
| `feed_coilT` | `FD COIL 1-H-1X` | `01TI0231.PV` | °C | 2019 → | feed-coil / crossover temperature |
| `feed_GC` | `FEED … C2H6/C3H8/C4H10/C5+/CO2` | `01AI0110.PV` | WT%/PPM | 2019 → | **NGL feed composition** (common to all furnaces, `furnace="PLANT"`) |
| `effluent_GC` | `1-H-1X CH4/C2H4/C2H6/C3H6/C3H8` | `01AI1421.PV` | WT% | 2025 → | furnace-effluent GC — **yield layer** (A–F only; sparse) |

### Per-furnace tube-TC counts (`tube_COT`, dense)

`1HA 29 · 1HB 22 · 1HC 14 · 1HD 12 · 1HE 9 · 1HF 16 · 1HG 25`. The `tube_COT_long`
proxy is uniformly 8 per furnace.

## Data depth (the "how far back" answer)

- **Process drivers** (feed, steam, COT, pressure, draft, feed GC, feed-coil T)
  reach back to **2019** → ~7 years, ~0.5 M samples/tag/year.
- **Dense per-tube skin TCs** (`tube_COT`) and **effluent GC** start **2025-02**.
- ⇒ Delta-Delta can be reconstructed **densely 2025-02→present**, or as an
  **8-tube proxy back to 2019** via `tube_COT_long` (`--long-history`).

## Known data-quality caveats

- Effluent GC readings are **suspect**: several furnaces report identical /
  quantised values (e.g. 1HA C2H4 pinned at 32.7 WT% through mid-2025), and
  there are zero-dropouts. The modelling-approach note flags GC reliability as
  an open question vs lab data. Treat `effluent_GC` cautiously.
- `Value=0` on a tube TC means offline/decoke, not 0 °C — masked out in
  `compute_delta` (tubes below 500 °C dropped from the pack mean).
