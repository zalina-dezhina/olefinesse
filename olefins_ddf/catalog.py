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
decoke_air      Per-pass decoke-air flow ("FUR X PASSA DECOKE AIR", NM3/H). Marks
                which pass is being decoked; independent confirmation of 4 passes.

Pass topology  (ground-truth confirmed - see docs/data_dictionary.md)
--------------------------------------------------------------------
Per the KBR "Furnace Control Systems" doc and the Indorama GroundTruth-Tags
spreadsheet: **4 radiant passes (BANKS) per furnace, 48 tubes per pass = 192
tubes per furnace**. Each tube has its own surface-mounted skin TC; the pass
average COT is used for control. Feed and dilution steam are set per pass, so a
pass running lean on steam cokes fastest.

``add_pass_column`` tags every row with its pass (NA for furnace-wide tags such
as the single COT controller, draft, or combined effluent GC):

  * feed_flow / dil_steam / decoke_air   ``#<A-D>`` / ``PASS<A-D>`` in the desc.
  * tube_COT_long                        ``BANK #<A-D>``.
  * tube_COT (dense)                     the tube NUMBER, in blocks of 48:
                                         1-48 -> A(Pass1), 49-96 -> B, 97-144 -> C,
                                         145-192 -> D. The spreadsheet states this
                                         directly ("01TI1001~48 = 1HA Pass1") and
                                         the feed tag for Pass1 (01FC0205) is #A,
                                         so band1<->PassA<->feed#A is aligned, not
                                         guessed. Max observed tube number is 192.

NOTE: ALL 192 tube TCs per furnace (1344 total) are present in the historian with
~1/min data from 2025-02. Only 127 carry the "TUBE CUR COT" description; the other
~1217 have BLANK descriptions, which is why the catalog keys ``tube_COT`` on the ID
pattern, not the description (an earlier description-only rule saw just 127).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import BLOCK_TO_FURNACE, METADATA, OUTPUT_DIR

_CATALOG_CSV = os.path.join(OUTPUT_DIR, "dd_tag_catalog.csv")

# Dense tube-COT numbers run 1-192 in blocks of 48, one block per pass
# (1-48 -> Pass A, ..., 145-192 -> Pass D). Ground-truth confirmed.
TUBES_PER_PASS = 48
N_PASSES = 4
TUBES_PER_FURNACE = TUBES_PER_PASS * N_PASSES   # 192
_PASS_BAND_WIDTH = TUBES_PER_PASS
_PASS_LETTERS = ["A", "B", "C", "D"]
# Roles whose signal is carried per-pass (all others are furnace-/plant-wide).
_PASS_ROLES = {"feed_flow", "dil_steam", "decoke_air", "tube_COT", "tube_COT_long"}

# Dense tube COT IDs are 01TI{F}{NNN}A.PV with F = furnace digit (1->1HA ... 7->1HG)
# and NNN = tube number 001-192. (Most carry a BLANK description, so the catalog
# keys on the ID, not the description text.)
_TUBE_COT_ID = r"^01TI([1-7])(\d{3})A\.PV$"
_FURDIGIT_TO_FURNACE = {i: f"1H{chr(ord('A') + i - 1)}" for i in range(1, 8)}
# Bearing/turbine TIs share the 01TI…A id space; exclude by description keyword.
_NON_TUBE_DESC = r"BRG|TURB|CASNG|\bK[12]\b|GOV|INACT"


def _fur_from_desc(group: int) -> Callable[[pd.Series], pd.Series]:
    def f(m: pd.DataFrame, rx: str) -> pd.Series:
        return "1H" + m["desc"].str.extract(rx, expand=False)
    return f


def _fur_from_block(m: pd.DataFrame, _rx: str) -> pd.Series:
    """Furnace from the TI/TC/PC hundreds-block (08->A ... 14->G)."""
    num = m["ID"].str.extract(r"01[A-Z]+(\d+)", expand=False).astype(float)
    block = (num // 100).astype("Int64")
    return block.map(BLOCK_TO_FURNACE)


def _fur_from_tube_id(m: pd.DataFrame, _rx: str) -> pd.Series:
    """Dense tube COT furnace from the ID digit after 01TI (1->1HA ... 7->1HG)."""
    digit = m["ID"].str.extract(_TUBE_COT_ID, expand=True)[0].astype("Int64")
    return digit.map(_FURDIGIT_TO_FURNACE)


def _tube_cot_filter(m: pd.DataFrame) -> pd.Series:
    """Keep real tube COTs: id-encoded tube number 1-192 and not a bearing TI."""
    num = m["ID"].str.extract(_TUBE_COT_ID, expand=True)[1].astype("Int64")
    in_range = num.between(1, TUBES_PER_FURNACE)
    not_bearing = ~m["desc"].str.contains(_NON_TUBE_DESC, case=False, na=False, regex=True)
    return (in_range & not_bearing).fillna(False)


def _fur_constant(value: str) -> Callable[[pd.DataFrame, str], pd.Series]:
    def f(m: pd.DataFrame, _rx: str) -> pd.Series:
        return pd.Series(value, index=m.index)
    return f


@dataclass
class Rule:
    role: str
    desc_rx: str                      # match on Description ("" = match all rows)
    fur_rx: str                       # regex to capture furnace letter (desc rules)
    fur_resolver: Callable            # how to assign the furnace
    id_rx: Optional[str] = None       # optional constraint on ID
    row_filter: Optional[Callable] = None  # optional extra mask(m)->bool Series


# Furnace letter is captured by `fur_rx` for desc-based resolvers.
_RULES: List[Rule] = [
    # Dense per-tube COTs: keyed on the ID (most descriptions are BLANK), furnace
    # from the id digit, bogus/bearing rows removed by row_filter. 192 tubes/furnace.
    Rule("tube_COT",      "",                      "",                       _fur_from_tube_id, _TUBE_COT_ID, _tube_cot_filter),
    Rule("tube_COT_long", r"BANK #[A-D] PQE #[58]\b", "",                    _fur_from_block,    r"^01TI"),
    # H[1I]: the digit '1' is rendered as letter 'I' in some descs (e.g. "HIE FD #A").
    # \s* before/around '#': feed descs have variable spacing ("H1C FD  #D PASS").
    Rule("feed_flow",     r"H[1I][A-G]\s+FD\s*#\s*[A-D]", r"H[1I]([A-G])",   _fur_from_desc(1), r"^01FC.*\.PV$"),
    Rule("dil_steam",     r"H[1I][A-G]\s+DS\s*#?\s*[A-D]", r"H[1I]([A-G])",  _fur_from_desc(1), r"^01FC.*\.PV$"),
    Rule("decoke_air",    r"FUR [A-G] PASS\s?[A-D] DE-?COKE AIR", r"FUR ([A-G]) PASS", _fur_from_desc(1), r"^01FC.*\.PV$"),
    Rule("cot_ctrl",      r"H-1[A-G] COT",         r"H-1([A-G]) COT",        _fur_from_desc(1), r"^01TC.*\.PV$"),
    Rule("coil_out_P",    r"EFFL FM\s+1-E-1[56][A-G]", r"1-E-1[56]([A-G])",  _fur_from_desc(1), r"^01PI.*\.PV$"),
    Rule("draft",         r"H1[A-G] CONV\s+DRAFT", r"H1([A-G])",             _fur_from_desc(1), r"^01PC.*\.PV$"),
    Rule("feed_coilT",    r"FD COIL\s+1-H-1[A-G]", r"1-H-1([A-G])",          _fur_from_desc(1), r"^01TI.*\.PV$"),
    Rule("effluent_GC",   r"1-H-1[A-G]\s+(?:CH4|C2H4|C2H6|C3H6|C3H8)", r"1-H-1([A-G])", _fur_from_desc(1), r"^01AI1[4-9]\d\d\.PV$"),
    Rule("feed_GC",       r"FEED (?:TO\s+FUR|FUR)", "",                      _fur_constant("PLANT"), r"^01AI01[12]\d\.PV$"),
]


def _pass_from_tube_num(num: float) -> Optional[str]:
    """Dense tube number -> pass letter in blocks of 48 (1-48 -> A ... 145-192 ->
    D). Ground-truth confirmed (spreadsheet: 01TI1001~48 = Pass1 = feed #A)."""
    if not np.isfinite(num):
        return None
    band = int((num - 1) // _PASS_BAND_WIDTH)
    band = min(max(band, 0), len(_PASS_LETTERS) - 1)
    return _PASS_LETTERS[band]


def add_pass_column(catalog: pd.DataFrame) -> pd.DataFrame:
    """Add a ``pass`` column (A-D, or <NA> for furnace-/plant-wide tags).

    The pass is taken from the explicit ``#<A-D>`` / ``PASS<A-D>`` label
    (feed_flow / dil_steam / decoke_air), the ``BANK #<A-D>`` label (long proxy),
    or the dense tube NUMBER binned in blocks of 48 (1-48 -> A ... 145-192 -> D).
    The last is confirmed by the GroundTruth spreadsheet (01TI1001~48 = Pass1)
    and aligned to the feed pass letters (Pass1's feed tag 01FC0205 is #A); the
    max observed tube number is 192 = 4 x 48.
    """
    cat = catalog.copy()
    desc = cat["Description"].fillna("")
    pas = pd.Series(pd.NA, index=cat.index, dtype="object")

    # feed/steam/decoke-air: explicit pass letter in the description text.
    m = cat["role"].isin({"feed_flow", "dil_steam", "decoke_air"})
    pas.loc[m] = desc[m].str.extract(r"(?:#\s*|PASS\s?)([A-D])\b", expand=False)

    # long proxy: BANK #<A-D> is the (explicitly stated) bank/pass.
    m = cat["role"] == "tube_COT_long"
    pas.loc[m] = desc[m].str.extract(r"BANK #([A-D])", expand=False)

    # dense tube COTs: tube number is in the ID (descriptions are mostly blank);
    # blocks of 48 -> pass (ground-truth mapping).
    m = cat["role"] == "tube_COT"
    nums = cat.loc[m, "ID"].str.extract(_TUBE_COT_ID, expand=True)[1].astype(float)
    pas.loc[m] = nums.map(_pass_from_tube_num)

    cat["pass"] = pas
    return cat


def build_catalog(spark, refresh: bool = False) -> pd.DataFrame:
    """Build (or load cached) the per-furnace Delta-Delta tag catalog."""
    if not refresh and os.path.exists(_CATALOG_CSV):
        cached = pd.read_csv(_CATALOG_CSV)
        if "pass" not in cached.columns:          # backfill older caches
            cached = add_pass_column(cached)
        return cached

    meta = spark.sql(f"SELECT ID, Description, UoM FROM {METADATA}").toPandas()
    meta["desc"] = meta["Description"].fillna("").str.strip()

    frames = []
    for r in _RULES:
        m = meta.copy() if r.desc_rx == "" else \
            meta[meta["desc"].str.contains(r.desc_rx, na=False, regex=True)].copy()
        if r.id_rx:
            m = m[m["ID"].str.match(r.id_rx, na=False)]
        if r.row_filter is not None and not m.empty:
            m = m[r.row_filter(m)]
        if m.empty:
            continue
        m["furnace"] = r.fur_resolver(m, r.fur_rx)
        m["role"] = r.role
        m = m.dropna(subset=["furnace"])
        frames.append(m[["ID", "furnace", "role", "Description", "UoM"]])

    catalog = pd.concat(frames, ignore_index=True).drop_duplicates(["ID", "role"])
    # feed-coilT also matches some effluent species rows; keep TI-only already done.
    catalog = add_pass_column(catalog)
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


def ids_for_pass(catalog: pd.DataFrame, furnace: str, role: str, pass_: str) -> List[str]:
    """Tag IDs for one furnace/role restricted to a single pass (A-D)."""
    sub = tags_for(catalog, furnace, [role])
    if "pass" not in sub:
        return []
    return sub[sub["pass"] == pass_]["ID"].tolist()


def tube_pass_map(catalog: pd.DataFrame, furnace: str, role: str = "tube_COT") -> Dict[str, str]:
    """{tube tag ID -> pass letter} for the chosen tube role of one furnace.

    Drives within-pass Delta and per-pass health aggregation.
    """
    sub = tags_for(catalog, furnace, [role])
    if "pass" not in sub:
        return {}
    sub = sub.dropna(subset=["pass"])
    return dict(zip(sub["ID"], sub["pass"]))


def summarize(catalog: pd.DataFrame) -> pd.DataFrame:
    return catalog.groupby(["furnace", "role"]).size().unstack(fill_value=0).sort_index()


def summarize_passes(catalog: pd.DataFrame, role: str = "tube_COT") -> pd.DataFrame:
    """Tube/tag count per furnace x pass for one role - the instrumentation map."""
    sub = catalog[catalog["role"] == role]
    if "pass" not in sub or sub.empty:
        return pd.DataFrame()
    return (sub.groupby(["furnace", "pass"]).size().unstack(fill_value=0)
            .reindex(columns=_PASS_LETTERS, fill_value=0).sort_index())
