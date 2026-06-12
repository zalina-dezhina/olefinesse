"""Assemble a unified, time-aligned feature matrix per furnace.

One row per time bucket, columns = the physically-meaningful drivers and
responses of furnace coking, so that correlations and (later) a forecaster can
be built on a single tidy table:

  Severity / operating levers
    cot              controlled coil-outlet temperature (degC)        [temperature]
    feed_total       total hydrocarbon feed across passes (NM3/H)     [throughput]
    steam_total      total dilution steam across passes (KG/H)
    steam_hc         steam-to-HC ratio (KG steam / NM3 feed)          [steam ratio]
    resid_proxy      relative residence-time proxy = 1/total vol flow [residence time]
    coil_out_P       coil-outlet / effluent pressure (KG/CM2)         [coil pressure]
    draft            convection draft (MMH2O)
    feed_coilT       mean feed-coil/crossover temperature (degC)

  Feed quality (NGL feed GC, common to all furnaces)
    feed_C2H6, feed_C3H8, feed_C4H10, feed_C5p (WT%), feed_CO2 (PPM)

  Furnace response
    tube_cot_mean    pack-mean tube skin temperature (degC)
    dd_abs_max, dd_p95, delta_spread   furnace-health (Delta-Delta) signals
    coking_rate      dDeltaDelta/dt (degC/day) - the coking rate
    eff_C2H4, eff_C3H6, eff_CH4, eff_C2H6, eff_C3H8   effluent GC (WT%)  [yield]

  Run structure
    run_id, run_age_days
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import catalog as cat
from . import deltadelta as ddm
from . import runs as runsmod
from .io_events import load_wide

# kg/h dilution steam -> Nm3/h (ideal gas, MW water 18.015, molar vol 22.414)
_STEAM_KGH_TO_NM3H = 22.414 / 18.015


def _species_col(sub: pd.DataFrame, wide: pd.DataFrame, role: str, token: str):
    """First loaded column for a role whose Description contains `token`."""
    ids = sub[(sub.role == role) & sub.Description.str.contains(token, na=False)].ID.tolist()
    for i in ids:
        if i in wide.columns:
            return wide[i]
    return pd.Series(np.nan, index=wide.index)


def build_feature_matrix(spark, catalog, furnace, start, end, bucket=30,
                         use_long_tc=False):
    """Return (features_df, runs). `use_long_tc` selects the 8-tube 2019+ proxy."""
    sub = cat.tags_for(catalog, furnace)
    tc_role = "tube_COT_long" if use_long_tc else "tube_COT"
    cot_ids = sub[sub.role == tc_role].ID.tolist()
    if not cot_ids:                       # fall back to whichever TC set exists
        tc_role = "tube_COT_long" if tc_role == "tube_COT" else "tube_COT"
        cot_ids = sub[sub.role == tc_role].ID.tolist()

    roles = {
        "cot": cat.ids_for(catalog, furnace, "cot_ctrl"),
        "feed": cat.ids_for(catalog, furnace, "feed_flow"),
        "steam": cat.ids_for(catalog, furnace, "dil_steam"),
        "coilP": cat.ids_for(catalog, furnace, "coil_out_P"),
        "draft": cat.ids_for(catalog, furnace, "draft"),
        "fcoilT": cat.ids_for(catalog, furnace, "feed_coilT"),
        "feedgc": cat.ids_for(catalog, furnace, "feed_GC"),
        "effgc": cat.ids_for(catalog, furnace, "effluent_GC"),
    }
    all_ids = sorted(set(cot_ids + sum(roles.values(), [])))
    wide = load_wide(spark, all_ids, start, end, bucket)
    if wide.empty or not any(c in wide.columns for c in cot_ids):
        return pd.DataFrame(), []

    cot = wide.reindex(columns=[c for c in cot_ids if c in wide.columns])
    feed = wide.reindex(columns=[c for c in roles["feed"] if c in wide.columns])
    steam = wide.reindex(columns=[c for c in roles["steam"] if c in wide.columns])

    feed_total = feed.sum(axis=1) if feed.shape[1] else pd.Series(np.nan, index=wide.index)
    steam_total = steam.sum(axis=1) if steam.shape[1] else pd.Series(np.nan, index=wide.index)

    cracking = runsmod.cracking_mask(feed_total, cot)
    runs = runsmod.segment_runs(cracking)
    delta = ddm.compute_delta(cot, cracking)
    dd = ddm.compute_delta_delta(delta, runs)
    health = ddm.health_indicators(delta, dd)
    rate = ddm.coking_rate(health["dd_abs_max"], runs)

    # Residence-time proxy: inverse total volumetric throughput (feed + steam-eq).
    total_vol = feed_total.add(steam_total * _STEAM_KGH_TO_NM3H, fill_value=0)
    resid_proxy = 1.0 / total_vol.where(total_vol > 0)

    feat = pd.DataFrame(index=wide.index)
    feat["cot"] = wide.reindex(columns=roles["cot"]).mean(axis=1) if roles["cot"] else np.nan
    feat["feed_total"] = feed_total
    feat["steam_total"] = steam_total
    feat["steam_hc"] = steam_total / feed_total.where(feed_total > 0)
    feat["resid_proxy"] = resid_proxy
    feat["coil_out_P"] = wide.reindex(columns=roles["coilP"]).mean(axis=1) if roles["coilP"] else np.nan
    feat["draft"] = wide.reindex(columns=roles["draft"]).mean(axis=1) if roles["draft"] else np.nan
    feat["feed_coilT"] = wide.reindex(columns=roles["fcoilT"]).mean(axis=1) if roles["fcoilT"] else np.nan
    # Feed quality (NGL feed GC)
    feat["feed_C2H6"] = _species_col(sub, wide, "feed_GC", "C2H6")
    feat["feed_C3H8"] = _species_col(sub, wide, "feed_GC", "C3H8")
    feat["feed_C4H10"] = _species_col(sub, wide, "feed_GC", "C4H10")
    feat["feed_C5p"] = _species_col(sub, wide, "feed_GC", "C5+")
    feat["feed_CO2"] = _species_col(sub, wide, "feed_GC", "CO2")
    # Furnace response
    feat["tube_cot_mean"] = cot.where(cot > runsmod.ONLINE_TEMP_C).mean(axis=1)
    feat["dd_abs_max"] = health["dd_abs_max"]
    feat["dd_p95"] = health["dd_p95"]
    feat["delta_spread"] = health["delta_spread"]
    feat["coking_rate"] = rate
    # Effluent GC (yield)
    feat["eff_C2H4"] = _species_col(sub, wide, "effluent_GC", "C2H4")
    feat["eff_C3H6"] = _species_col(sub, wide, "effluent_GC", "C3H6")
    feat["eff_CH4"] = _species_col(sub, wide, "effluent_GC", "CH4")
    feat["eff_C2H6"] = _species_col(sub, wide, "effluent_GC", "C2H6")
    feat["eff_C3H8"] = _species_col(sub, wide, "effluent_GC", "C3H8")
    # Run structure
    feat["run_id"] = runsmod.run_id_series(wide.index, runs)
    feat["run_age_days"] = runsmod.run_age_days(wide.index, runs)
    feat["furnace"] = furnace
    feat["cracking"] = cracking.reindex(feat.index, fill_value=False)
    return feat, runs


def per_run_summary(feat: pd.DataFrame, runs) -> pd.DataFrame:
    """One row per run: mean drivers + coking outcome. The table that answers
    'what operating conditions drive coking / run length'."""
    rows = []
    for r in runs:
        seg = feat.loc[r.start:r.end]
        crk = seg[seg["cracking"]]
        if crk.empty:
            continue
        # coking slope: robust linear fit of dd_abs_max vs run age over the run
        x = crk["run_age_days"].to_numpy()
        y = crk["dd_abs_max"].to_numpy()
        ok = np.isfinite(x) & np.isfinite(y)
        slope = np.polyfit(x[ok], y[ok], 1)[0] if ok.sum() > 5 else np.nan
        rows.append({
            "furnace": feat["furnace"].iloc[0], "run": r.index,
            "start": r.start, "length_days": round(r.length_days, 2),
            "cot": crk["cot"].mean(), "feed_total": crk["feed_total"].mean(),
            "steam_hc": crk["steam_hc"].mean(), "resid_proxy": crk["resid_proxy"].mean(),
            "coil_out_P": crk["coil_out_P"].mean(), "draft": crk["draft"].mean(),
            "feed_C2H6": crk["feed_C2H6"].mean(), "feed_C3H8": crk["feed_C3H8"].mean(),
            "feed_C5p": crk["feed_C5p"].mean(),
            "eff_C2H4": crk["eff_C2H4"].mean(),
            "dd_end": crk["dd_abs_max"].tail(48).median(),
            "coking_slope_Cpd": round(float(slope), 3) if np.isfinite(slope) else np.nan,
        })
    return pd.DataFrame(rows)
