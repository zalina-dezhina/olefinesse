"""Run / decoke cycle detection.

A *decoke* does not cool the furnace - coke is burned off the coils with
steam/air while firing continues, so the tube COTs stay hot. A decoke is
therefore detected from the HYDROCARBON FEED being cut to ~0, not from
temperature. A "run" is one cracking campaign between two decokes - the unit
Delta-Delta is normalised against.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

ONLINE_TEMP_C = 500.0   # median tube COT above this => furnace firing
FEED_FRAC = 0.30        # feed below this fraction of running level => decoke/offline


@dataclass
class Run:
    """One online cracking campaign between two decokes."""
    index: int
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def length_days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0


def online_mask(cot: pd.DataFrame, temp_c: float = ONLINE_TEMP_C) -> pd.Series:
    """True where the furnace is firing (median tube COT hot)."""
    return cot.median(axis=1) > temp_c


def cracking_mask(
    feed_total: Optional[pd.Series],
    cot: Optional[pd.DataFrame] = None,
    feed_frac: float = FEED_FRAC,
    temp_c: float = ONLINE_TEMP_C,
) -> pd.Series:
    """True where the furnace is actively cracking (substantial HC feed AND hot).

    Falls back to the temperature firing mask when feed is unavailable.
    """
    if feed_total is None or feed_total.dropna().empty:
        return online_mask(cot, temp_c) if cot is not None else pd.Series(dtype=bool)
    running = feed_total[feed_total > feed_total.max() * 0.1].median()
    mask = feed_total > feed_frac * running
    if cot is not None:
        mask = mask & online_mask(cot, temp_c).reindex(mask.index, fill_value=False)
    return mask.fillna(False)


def segment_runs(
    mask: pd.Series,
    min_run_days: float = 3.0,
    min_gap_hours: float = 6.0,
) -> List[Run]:
    """Split a cracking mask into runs separated by decoke gaps.

    Short blips are ignored so transient feed trips / TC dropouts don't fragment
    a real run.
    """
    idx = mask.index
    if len(idx) < 2:
        return []
    step = (idx[1] - idx[0]).total_seconds()
    min_gap_steps = max(1, int(min_gap_hours * 3600 / step))

    vals = mask.fillna(False).to_numpy()
    runs: List[Run] = []
    n, i = len(vals), 0
    while i < n:
        if not vals[i]:
            i += 1
            continue
        j, gap, last_true = i, 0, i
        while j < n:
            if vals[j]:
                last_true, gap = j, 0
            else:
                gap += 1
                if gap >= min_gap_steps:
                    break
            j += 1
        runs.append(Run(len(runs), idx[i], idx[last_true]))
        i = j

    runs = [r for r in runs if r.length_days >= min_run_days]
    return [Run(k, r.start, r.end) for k, r in enumerate(runs)]


def run_age_days(index: pd.DatetimeIndex, runs: List[Run]) -> pd.Series:
    """Days since the start of the run each timestamp belongs to (NaN if none)."""
    age = pd.Series(np.nan, index=index)
    for r in runs:
        m = (index >= r.start) & (index <= r.end)
        age.loc[m] = (index[m] - r.start).total_seconds() / 86400.0
    return age


def run_id_series(index: pd.DatetimeIndex, runs: List[Run]) -> pd.Series:
    """Integer run index per timestamp (NaN outside any run)."""
    rid = pd.Series(np.nan, index=index)
    for r in runs:
        rid.loc[(index >= r.start) & (index <= r.end)] = r.index
    return rid


def run_table(runs: List[Run], furnace: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"furnace": furnace, "run": r.index, "start": r.start, "end": r.end,
          "length_days": round(r.length_days, 2)} for r in runs]
    )
