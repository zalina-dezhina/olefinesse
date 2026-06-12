"""Reconstruct Delta and Delta-Delta from raw tube-skin thermocouples.

  Delta_i(t)      = COT_i(t) - mean_j COT_j(t)              (deviation from pack)
  baseline_i      = mean Delta_i over first `baseline_hours` of the run
  DeltaDelta_i(t) = Delta_i(t) - baseline_i                 (run-normalised drift)

Rising |DeltaDelta| => a tube is preferentially coking / losing flow: the
furnace-health signal operators decoke on.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from .runs import ONLINE_TEMP_C, Run


def compute_delta(cot: pd.DataFrame, active: pd.Series) -> pd.DataFrame:
    """Delta_i(t) = COT_i - pack mean, only while `active` and the TC is hot."""
    c = cot.where(active, np.nan)
    c = c.where(c > ONLINE_TEMP_C, np.nan)   # drop dead / zeroed TCs from the pack
    return c.sub(c.mean(axis=1), axis=0)


def compute_delta_delta(
    delta: pd.DataFrame, runs: List[Run], baseline_hours: float = 12.0
) -> pd.DataFrame:
    """Per-run start-of-run-referenced drift. NaN outside detected runs."""
    dd = pd.DataFrame(np.nan, index=delta.index, columns=delta.columns)
    for r in runs:
        seg = delta.loc[r.start:r.end]
        if seg.empty:
            continue
        base = seg.loc[r.start:r.start + pd.Timedelta(hours=baseline_hours)].mean(axis=0)
        dd.loc[r.start:r.end] = seg.sub(base, axis=1).values
    return dd


def health_indicators(delta: pd.DataFrame, dd: pd.DataFrame) -> pd.DataFrame:
    """Scalar furnace-health series an operator would watch."""
    return pd.DataFrame(
        {
            "delta_spread": delta.max(axis=1) - delta.min(axis=1),
            "dd_max": dd.max(axis=1),
            "dd_abs_max": dd.abs().max(axis=1),
            "dd_p95": dd.quantile(0.95, axis=1),
        }
    )


def coking_rate(dd_health: pd.Series, runs: List[Run], window_hours: float = 24.0,
                index: pd.DatetimeIndex = None) -> pd.Series:
    """Smoothed time-derivative of the health signal (°C/day), reset per run.

    This is the operational coking *rate* - the quantity a forecaster ultimately
    predicts and the optimiser constrains.
    """
    idx = dd_health.index
    step_h = (idx[1] - idx[0]).total_seconds() / 3600.0
    win = max(2, int(window_hours / step_h))
    rate = pd.Series(np.nan, index=idx)
    for r in runs:
        seg = dd_health.loc[r.start:r.end]
        sm = seg.rolling(win, min_periods=max(2, win // 3), center=True).median()
        rate.loc[r.start:r.end] = sm.diff() / step_h * 24.0   # per day
    return rate
