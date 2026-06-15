"""Reconstruct Delta and Delta-Delta from raw tube-skin thermocouples.

  Delta_i(t)      = COT_i(t) - mean_j COT_j(t)              (deviation from pack)
  baseline_i      = mean Delta_i over first `baseline_hours` of the run
  DeltaDelta_i(t) = Delta_i(t) - baseline_i                 (run-normalised drift)

Rising |DeltaDelta| => a tube is preferentially coking / losing flow: the
furnace-health signal operators decoke on.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .runs import ONLINE_TEMP_C, Run


def compute_delta(
    cot: pd.DataFrame,
    active: pd.Series,
    tube_pass: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Delta_i(t) = COT_i - reference mean, only while `active` and the TC is hot.

    The standard reference is each tube's own **PASS average** (the KBR/DCS
    definition) — pass ``tube_pass`` ({tube ID -> pass letter}), which the feature
    and CLI pipelines always do. This removes pass-level operating offsets
    (different feed/steam split per pass) and isolates within-pass coking drift.
    With full 48-tube/pass coverage there is no degeneracy. If ``tube_pass`` is
    omitted it falls back to the furnace pack mean (ad-hoc use only).
    """
    c = cot.where(active, np.nan)
    c = c.where(c > ONLINE_TEMP_C, np.nan)   # drop dead / zeroed TCs from the pack
    if not tube_pass:
        return c.sub(c.mean(axis=1), axis=0)

    out = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
    groups: Dict[str, List[str]] = {}
    for tube, p in tube_pass.items():
        if tube in c.columns:
            groups.setdefault(p, []).append(tube)
    for cols in groups.values():
        sub = c[cols]
        out[cols] = sub.sub(sub.mean(axis=1), axis=0).values
    return out


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


def per_pass_health(dd: pd.DataFrame, tube_pass: Dict[str, str]) -> pd.DataFrame:
    """Worst-tube |Delta-Delta| within each pass: columns dd_abs_max_<A-D>.

    Built from the furnace-referenced ``dd`` (so single-tube passes are still
    meaningful), this localises coking to a pass: the highest column is the pass
    dragging the furnace toward a decoke, and the spread across passes is the
    pass-imbalance the per-pass levers can act on.
    """
    out = {}
    for p in sorted(set(tube_pass.values())):
        cols = [t for t in dd.columns if tube_pass.get(t) == p]
        if cols:
            out[f"dd_abs_max_{p}"] = dd[cols].abs().max(axis=1)
    res = pd.DataFrame(out, index=dd.index)
    if res.shape[1] > 1:
        res["pass_imbalance"] = res.max(axis=1) - res.min(axis=1)
    return res


def worst_pass(per_pass: pd.DataFrame) -> pd.Series:
    """Pass letter with the largest |Delta-Delta| at each timestamp (NA if no
    pass has a reading at that timestamp)."""
    cols = [c for c in per_pass.columns if c.startswith("dd_abs_max_")]
    out = pd.Series(pd.NA, index=per_pass.index, dtype="object")
    if not cols:
        return out
    sub = per_pass[cols]
    valid = sub.notna().any(axis=1)                       # avoid idxmax on all-NA rows
    out.loc[valid] = sub.loc[valid].idxmax(axis=1).str.replace("dd_abs_max_", "", regex=False)
    return out


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
