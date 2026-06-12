"""Discover and label the furnace tags relevant to Delta-Delta forecasting.

The DCS tag names are not systematic, so tags are identified by parsing the
human-readable ``Description`` field of ``timeseries.metadata``. Several distinct
numbering schemes coexist (see ``docs/data_dictionary.md``); each role rule below
knows how to resolve the furnace either from the description text or from the
tag-number hundreds-block.

Roles
-----
tube_COT        Dense per-tube coil-outlet skin TCs ("H-X TUBE CUR COT",
                ``01TI10xxA.PV``). THE Delta-Delta source. ~9-29 tubes/furnace,
                ~1/min, but only 2025-02 onward.
tube_COT_long   Sparse per-tube skin TCs ("BANK #x PQE #5/#8"), 8 tubes/furnace
                (4 passes x 2 positions), furnace from number block. Reaches back
                to 2019 -> lets Delta-Delta be reconstructed over 7 years.
feed_flow       Hydrocarbon feed per pass ("H1X FD #A PASS", NM3/H). Throughput
                lever and decoke detector.
dil_steam       Dilution steam per pass ("H1X DS #A PASS", KG/H). Steam/HC lever.
cot_ctrl        Coil-outlet-temperature controller ("H-1X COT", ``01TC..05.PV``,
                degC). The severity/temperature lever; 2019 onward.
coil_out_P      Furnace effluent / coil-outlet pressure ("EFFL FM 1-E-15X/16X",
                KG/CM2). Coil pressure lever; 2019 onward.
draft           Convection-zone draft ("H1X CONV DRAFT", MMH2O). Firing lever.
feed_coilT      Feed-coil / crossover temperature ("FD COIL 1-H-1X", degC).
feed_GC         NGL feed composition ("FEED ... C2H6/C3H8/C4H10/C5+/CO2",
                WT%/PPM). Common plant feed (not per furnace) -> furnace="PLANT".
effluent_GC     Furnace-effluent GC composition ("1-H-1X C2H4" etc, WT%). Yield
                layer; sparse (~hourly), furnaces A-F only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import pandas as pd

from .config import BLOCK_TO_FURNACE, METADATA, OUTPUT_DIR

_CATALOG_CSV = os.path.join(OUTPUT_DIR, "dd_tag_catalog.csv")


def _fur_from_desc(group: int) -> Callable[[pd.Series], pd.Series]:
    def f(m: pd.DataFrame, rx: str) -> pd.Series:
        return "1H" + m["desc"].str.extract(rx, expand=False)
    return f


def _fur_from_block(m: pd.DataFrame, _rx: str) -> pd.Series:
    """Furnace from the TI/TC/PC hundreds-block (08->A ... 14->G)."""
    num = m["ID"].str.extract(r"01[A-Z]+(\d+)", expand=False).astype(float)
    block = (num // 100).astype("Int64")
    return block.map(BLOCK_TO_FURNACE)


def _fur_constant(value: str) -> Callable[[pd.DataFrame, str], pd.Series]:
    def f(m: pd.DataFrame, _rx: str) -> pd.Series:
        return pd.Series(value, index=m.index)
    return f


@dataclass
class Rule:
    role: str
    desc_rx: str                      # match on Description
    fur_rx: str                       # regex to capture furnace letter (desc rules)
    fur_resolver: Callable            # how to assign the furnace
    id_rx: Optional[str] = None       # optional constraint on ID


# Furnace letter is captured by `fur_rx` for desc-based resolvers.
_RULES: List[Rule] = [
    Rule("tube_COT",      r"H-[A-G] TUBE CUR COT", r"H-([A-G]) TUBE CUR COT", _fur_from_desc(1), r"^01TI"),
    Rule("tube_COT_long", r"BANK #[A-D] PQE #[58]\b", "",                    _fur_from_block,    r"^01TI"),
    Rule("feed_flow",     r"H1[A-G] FD ?#[A-D]",   r"H1([A-G])",             _fur_from_desc(1), r"^01FC.*\.PV$"),
    Rule("dil_steam",     r"H1[A-G] DS ?#?[A-D]",  r"H1([A-G])",             _fur_from_desc(1), r"^01FC.*\.PV$"),
    Rule("cot_ctrl",      r"H-1[A-G] COT",         r"H-1([A-G]) COT",        _fur_from_desc(1), r"^01TC.*\.PV$"),
    Rule("coil_out_P",    r"EFFL FM\s+1-E-1[56][A-G]", r"1-E-1[56]([A-G])",  _fur_from_desc(1), r"^01PI.*\.PV$"),
    Rule("draft",         r"H1[A-G] CONV\s+DRAFT", r"H1([A-G])",             _fur_from_desc(1), r"^01PC.*\.PV$"),
    Rule("feed_coilT",    r"FD COIL\s+1-H-1[A-G]", r"1-H-1([A-G])",          _fur_from_desc(1), r"^01TI.*\.PV$"),
    Rule("effluent_GC",   r"1-H-1[A-G]\s+(CH4|C2H4|C2H6|C3H6|C3H8)", r"1-H-1([A-G])", _fur_from_desc(1), r"^01AI1[4-9]\d\d\.PV$"),
    Rule("feed_GC",       r"FEED (TO\s+FUR|FUR)",  "",                       _fur_constant("PLANT"), r"^01AI01[12]\d\.PV$"),
]


def build_catalog(spark, refresh: bool = False) -> pd.DataFrame:
    """Build (or load cached) the per-furnace Delta-Delta tag catalog."""
    if not refresh and os.path.exists(_CATALOG_CSV):
        return pd.read_csv(_CATALOG_CSV)

    meta = spark.sql(f"SELECT ID, Description, UoM FROM {METADATA}").toPandas()
    meta["desc"] = meta["Description"].fillna("").str.strip()

    frames = []
    for r in _RULES:
        m = meta[meta["desc"].str.contains(r.desc_rx, na=False, regex=True)].copy()
        if r.id_rx:
            m = m[m["ID"].str.match(r.id_rx, na=False)]
        if m.empty:
            continue
        m["furnace"] = r.fur_resolver(m, r.fur_rx)
        m["role"] = r.role
        m = m.dropna(subset=["furnace"])
        frames.append(m[["ID", "furnace", "role", "Description", "UoM"]])

    catalog = pd.concat(frames, ignore_index=True).drop_duplicates(["ID", "role"])
    # feed-coilT also matches some effluent species rows; keep TI-only already done.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    catalog.to_csv(_CATALOG_CSV, index=False)
    return catalog


def tags_for(catalog: pd.DataFrame, furnace: str, roles=None) -> pd.DataFrame:
    """Subset to one furnace (PLANT-level roles such as feed_GC are always
    included since the NGL feed is common to all furnaces)."""
    out = catalog[(catalog["furnace"] == furnace) | (catalog["furnace"] == "PLANT")]
    if roles is not None:
        out = out[out["role"].isin(roles)]
    return out.reset_index(drop=True)


def ids_for(catalog: pd.DataFrame, furnace: str, role: str) -> List[str]:
    sub = tags_for(catalog, furnace, [role])
    return sub["ID"].tolist()


def summarize(catalog: pd.DataFrame) -> pd.DataFrame:
    return catalog.groupby(["furnace", "role"]).size().unstack(fill_value=0).sort_index()
