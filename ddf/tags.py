"""Tag discovery and the per-furnace Delta-Delta tag catalog.

The DCS tag naming is not perfectly systematic, so we identify the relevant tags
by parsing the human-readable Description field of the `timeseries.metadata`
table rather than by tag-number ranges. The tag roles that matter for
Delta-Delta forecasting are:

  tube_COT    Per-tube coil-outlet skin thermocouples ("H-X TUBE CUR COT").
              ~9-29 tubes per furnace, ~1 sample/min. THE Delta-Delta source.
  feed_flow   Hydrocarbon feed flow per pass ("H1X FD #A PASS", NM3/H).
              Severity/throughput lever; also reveals run/decoke cycles.
  dil_steam   Dilution steam per pass ("H1X DS #A PASS", KG/H).
              Sets the steam-to-hydrocarbon ratio lever.
  effluent_GC Furnace-effluent gas-chromatograph composition ("1-H-1X C2H4"
              etc., WT%). Sparse (~hourly). The yield-mapping layer.

`build_catalog(spark)` returns a tidy DataFrame [ID, furnace, role, Description,
UoM] and also caches it to CSV so the rest of the pipeline can run without
re-hitting the metadata table.
"""
from __future__ import annotations

import os
import re

import pandas as pd

from .config import METADATA, OUTPUT_DIR

_CATALOG_CSV = os.path.join(OUTPUT_DIR, "dd_tag_catalog.csv")

# (role, regex on Description, regex capturing the furnace letter, optional ID filter)
_ROLE_RULES = [
    ("tube_COT", r"H-[A-G] TUBE CUR COT", r"H-([A-G]) TUBE CUR COT", r"^01TI"),
    ("feed_flow", r"H1[A-G] FD ?#[A-D]", r"H1([A-G])", r"^01FC.*\.PV$"),
    ("dil_steam", r"H1[A-G] DS ?#?[A-D]", r"H1([A-G])", r"^01FC.*\.PV$"),
    ("effluent_GC", r"1-H-1[A-G]", r"1-H-1([A-G])", r"^01AI1[4-9]\d\d\.PV$"),
]


def build_catalog(spark, refresh: bool = False) -> pd.DataFrame:
    """Build (or load cached) the per-furnace Delta-Delta tag catalog."""
    if not refresh and os.path.exists(_CATALOG_CSV):
        return pd.read_csv(_CATALOG_CSV)

    meta = spark.sql(
        f"SELECT ID, Description, UoM FROM {METADATA}"
    ).toPandas()
    meta["desc"] = meta["Description"].fillna("").str.strip()

    frames = []
    for role, desc_rx, fur_rx, id_rx in _ROLE_RULES:
        m = meta[meta["desc"].str.contains(desc_rx, na=False, regex=True)]
        if id_rx:
            m = m[m["ID"].str.match(id_rx, na=False)]
        m = m.copy()
        m["role"] = role
        m["furnace"] = "1H" + m["desc"].str.extract(fur_rx, expand=False)
        m = m.dropna(subset=["furnace"])
        frames.append(m[["ID", "furnace", "role", "Description", "UoM"]])

    catalog = pd.concat(frames, ignore_index=True).drop_duplicates("ID")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    catalog.to_csv(_CATALOG_CSV, index=False)
    return catalog


def tags_for(catalog: pd.DataFrame, furnace: str, roles=None) -> pd.DataFrame:
    """Subset the catalog to one furnace (and optionally specific roles)."""
    out = catalog[catalog["furnace"] == furnace]
    if roles is not None:
        out = out[out["role"].isin(roles)]
    return out.reset_index(drop=True)


def summarize(catalog: pd.DataFrame) -> pd.DataFrame:
    """Counts of tags per (furnace, role) — handy sanity check."""
    return (
        catalog.groupby(["furnace", "role"]).size().unstack(fill_value=0).sort_index()
    )
