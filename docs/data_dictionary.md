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

## Furnace topology: furnace → pass → tube

**Ground truth** (KBR *Furnace Control Systems* doc p6; Indorama
*GroundTruth-Tags.xlsx* `Furnace` sheet): each furnace is one radiant firebox
whose feed is split into **four radiant passes / BANKS (`#A–#D` = Pass 1–4), with
48 individual radiant tubes per pass = 192 tubes per furnace.** Every tube has
its own surface-mounted skin thermocouple (the COT); the **pass-average** COT is
used for control, plus 2 duplex TCs/pass on tubes 12 & 25. Feed and dilution
steam are set per pass.

```
FURNACE (1HA–1HG)                       one radiant firebox, 192 tubes
  └── PASS  (#A #B #C #D = Pass1–4)     parallel flow path — the coking lever surface
        ├── feed flow control   (NM3/H)  HC feed into this pass        01FC..05/07/09/11
        ├── dilution-steam ctrl (KG/H)   steam into this pass          01FC..17/20/23/26
        ├── decoke-air flow     (NM3/H)  air during this pass's decoke 01FC..33/34/35/36
        └── 48 radiant TUBES, each with an outlet skin TC (COT)  ← ΔΔ source  01TI….PV
furnace-wide: COT controller ×1, convection draft ×1, coil-outlet P ×2,
              feed-coil/crossover T ×4, effluent GC ×1 (combined effluent).
```

**Delta is per-tube vs its PASS AVERAGE** (KBR doc p23–24; our own
`delta_delta_report-7.pdf`: *"Delta is the deviation of an individual tube's
outlet skin temperature from its pass average"*). This is **the single definition
used throughout** — the feature matrix and CLI compute it via
`compute_delta(..., tube_pass=…)` over the full 48-tube pass population (the
furnace pack mean is only a no-pass-map fallback). Per-pass levers (`feed_<P>`,
`steam_<P>`, `steam_hc_<P>`, `steam_hc_spread`) and per-pass health
(`dd_abs_max_<P>`, `pass_imbalance`, `worst_pass`) are in the feature matrix.

**Confirmed 4 passes on all 7 furnaces** (feed + steam). Two feed tags had been
missed by earlier description parsing — pure formatting quirks, now fixed:

| furnace | pass | tag | description quirk |
|---|---|---|---|
| 1HC | D | `01FC0411.PV` | double space: `H1C FD␣␣#D PASS` |
| 1HE | A | `01FC0605.PV` | digit `1` typed as letter `I`: `HIE FD #A` |

Independent confirmation: the **per-pass decoke-air** tags (`FUR C PASSA DECOKE
AIR`, `01FC0433–0436`; `DEC AIR TO H-1C`, `01FC0441`) — four per furnace.

### Mapping tags to passes

| role | how the pass is recovered |
|---|---|
| `feed_flow`, `dil_steam`, `decoke_air` | explicit `#<A-D>` / `PASS<A-D>` in the description |
| `tube_COT_long` | `BANK #<A-D>` in the description |
| `tube_COT` (dense) | tube number in **blocks of 48**: `1–48→A`, `49–96→B`, `97–144→C`, `145–192→D` |

The block mapping is **stated explicitly** by the spreadsheet (`01TI1001~48 =
1HA Pass1`), Pass1's feed tag (`01FC0205`) is `#A`, and the **max observed tube
number is 192 = 4×48** — so `tube# → pass → feed-letter` is aligned, not guessed.

**Historian coverage is COMPLETE: all 192 tube TCs per furnace (1344 total),
48/48/48/48 per pass, with ~1/min data from 2025-02-05.** The catalog keys
`tube_COT` on the **ID pattern** `01TI{F}{NNN}A.PV` (F = furnace digit 1→1HA …
7→1HG; NNN = tube 001–192). Only 127 of these tags carry the description
`TUBE CUR COT`; **~1217 have BLANK descriptions** — an earlier description-only
rule saw just those 127 and wrongly implied ~9% sparse coverage with empty
passes. Excluded from the role: 24 turbine/casing **bearing** TIs that share the
`01TI…A` id space (sit at tube# > 192), and the duplex `…B.PV` TCs on tubes 12 &
25 (a second TC on an already-covered tube). The 8-tube long proxy
(`tube_COT_long`, `PQE #5/#8`) remains useful only for its longer history (2019→).

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
| `tube_COT` | id `01TI{F}{NNN}A.PV` (desc often blank) | `01TI1001A.PV` | °C | **2025-02 →** | per-tube coil-outlet skin TC — **Delta-Delta source** (all 192/furnace, 48/pass) |
| `tube_COT_long` | `BANK #x PQE #5/#8` | `01TI0802.PV` | °C | **2019 →** | sparse per-tube skin TC, 8/furnace (4 passes × pos 5,8) — long-history Delta-Delta proxy |
| `cot_ctrl` | `H-1X COT` | `01TC0805.PV` | °C | 2019 → | controlled coil-outlet temperature — **severity/temperature lever** |
| `feed_flow` | `H1X FD #A PASS` | `01FC0205.PV` | NM3/H | 2019 → | HC feed per pass — **throughput lever + decoke detector** |
| `dil_steam` | `H1X DS #A PASS` | `01FC0217.PV` | KG/H | 2019 → | dilution steam per pass — **steam/HC ratio lever** |
| `coil_out_P` | `EFFL FM 1-E-15X/16X` | `01PI1401.PV` | KG/CM2 | 2019 → | coil-outlet / effluent pressure — **coil-pressure lever** |
| `draft` | `H1X CONV DRAFT` | `01PC6001.PV` | MMH2O | 2019 → | convection draft — firing lever |
| `feed_coilT` | `FD COIL 1-H-1X` | `01TI0231.PV` | °C | 2019 → | feed-coil / crossover temperature |
| `decoke_air` | `FUR X PASSA DECOKE AIR` | `01FC0433.PV` | NM3/H | 2019 → | per-pass decoke-air flow — marks which pass is being decoked (4/furnace) |
| `feed_GC` | `FEED … C2H6/C3H8/C4H10/C5+/CO2` | `01AI0110.PV` | WT%/PPM | 2019 → | **NGL feed composition** (common to all furnaces, `furnace="PLANT"`) |
| `effluent_GC` | `1-H-1X CH4/C2H4/C2H6/C3H6/C3H8` | `01AI1421.PV` | WT% | 2025 → | furnace-effluent GC — **yield layer** (A–F only; sparse) |

Every row also carries a **`pass`** column (`A`–`D`, or empty for furnace-/plant-wide
tags) — see *Furnace topology* above.

### Per-furnace tube-TC counts (`tube_COT`, dense)

**192 per furnace (1344 total), 48 per pass** — full coverage, ~1/min, 2025-02→.
(127 carry the `TUBE CUR COT` description; the rest are blank-described but live —
the catalog keys on the ID, see *Furnace topology*.) The `tube_COT_long` proxy is
uniformly 8 per furnace (2 per pass), useful for its 2019→ history. Feed / steam /
decoke-air are each exactly 4 per furnace (one per pass).

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
