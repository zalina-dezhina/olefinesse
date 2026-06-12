"""Correlation analysis over the unified feature matrix.

Three complementary views:
  1. correlation_matrix  - Pearson & Spearman across all operating variables,
     restricted to cracking periods (offline rows would dominate spuriously).
  2. driver_target_corr  - ranked correlation of each driver against a chosen
     response (e.g. coking_rate, dd_abs_max), with Spearman for monotonic but
     non-linear relationships.
  3. lagged_xcorr        - cross-correlation vs lag, to expose response/GC
     latency (a severity move shows up in Delta-Delta and in the effluent GC
     only after a delay).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

# Operating variables of interest for the coking story.
DEFAULT_COLS = [
    "cot", "feed_total", "steam_hc", "resid_proxy", "coil_out_P", "draft",
    "feed_coilT", "feed_C2H6", "feed_C3H8", "feed_C5p", "feed_CO2",
    "tube_cot_mean", "dd_abs_max", "coking_rate", "run_age_days",
    "eff_C2H4", "eff_C3H6",
]


def _cracking(feat: pd.DataFrame) -> pd.DataFrame:
    return feat[feat.get("cracking", True) == True] if "cracking" in feat else feat


def correlation_matrix(feat: pd.DataFrame, cols: Optional[List[str]] = None,
                       method: str = "spearman") -> pd.DataFrame:
    cols = [c for c in (cols or DEFAULT_COLS) if c in feat.columns]
    d = _cracking(feat)[cols].apply(pd.to_numeric, errors="coerce")
    # Drop all-NaN / constant columns that would yield NaN correlations.
    d = d.loc[:, d.notna().sum() > 10]
    d = d.loc[:, d.std(numeric_only=True) > 0]
    return d.corr(method=method)


def driver_target_corr(feat: pd.DataFrame, target: str,
                       drivers: Optional[List[str]] = None) -> pd.DataFrame:
    drivers = drivers or [c for c in DEFAULT_COLS if c not in (target,)]
    d = _cracking(feat)
    rows = []
    for col in drivers:
        if col not in d or col == target:
            continue
        sub = d[[col, target]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 30 or sub[col].std() == 0:
            continue
        rows.append({
            "driver": col, "n": len(sub),
            "pearson": sub[col].corr(sub[target], method="pearson"),
            "spearman": sub[col].corr(sub[target], method="spearman"),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.reindex(out["spearman"].abs().sort_values(ascending=False).index)
    return out.reset_index(drop=True)


def lagged_xcorr(feat: pd.DataFrame, x: str, y: str,
                 max_lag_steps: int = 96) -> pd.DataFrame:
    """Pearson corr of x(t) vs y(t+lag) over a range of lags (in buckets).

    Positive lag => x leads y (x changes, y responds `lag` buckets later).
    """
    d = _cracking(feat)[[x, y]].apply(pd.to_numeric, errors="coerce")
    rows = []
    for lag in range(-max_lag_steps, max_lag_steps + 1):
        s = d[x].corr(d[y].shift(-lag))
        rows.append({"lag_steps": lag, "corr": s})
    return pd.DataFrame(rows)


def best_lag(xc: pd.DataFrame) -> dict:
    i = xc["corr"].abs().idxmax()
    return {"lag_steps": int(xc.loc[i, "lag_steps"]), "corr": float(xc.loc[i, "corr"])}
