"""Reconstruct Delta and Delta-Delta from raw tube-skin thermocouples.

Definitions (from the KBR / INSITE 3.0 Delta-Delta value-prop note):

  Delta_i(t)        = COT_i(t) - mean_j COT_j(t)
                      Per-tube deviation of coil-outlet skin temperature from the
                      furnace pack average at instant t.

  baseline_i        = mean of Delta_i over the first `baseline_hours` of the run,
                      snapshotted just after a fresh decoke (start of run).

  DeltaDelta_i(t)   = Delta_i(t) - baseline_i
                      Run-normalised drift of a tube away from the pack. Rising
                      magnitude => that tube is preferentially coking / losing
                      flow => the furnace-health signal operators decoke on.

Because the calculated Delta tags are not exposed in the historian, we
reconstruct them from the raw per-tube COT thermocouples plus a start-of-run
baseline detected from the run/decoke cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

# A furnace is "firing" when the pack of tube skin TCs is hot. Below this the
# furnace is offline (tube COTs collapse toward ambient/zero).
#
# IMPORTANT: a *decoke* does not cool the furnace — coke is burned off the coils
# with steam/air while firing continues, so the tube COTs stay hot. A decoke is
# therefore detected from the HYDROCARBON FEED being cut, not from temperature.
# A "run" (the unit Delta-Delta is normalised against) is one cracking campaign
# between two decokes, i.e. a contiguous period of substantial HC feed.
ONLINE_TEMP_C = 500.0
FEED_FRAC = 0.30  # feed below this fraction of the running level => decoke/offline


@dataclass
class Run:
    """One online cracking run between two decokes."""
    index: int
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def length_days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0


def online_mask(cot: pd.DataFrame, temp_c: float = ONLINE_TEMP_C) -> pd.Series:
    """Boolean series: True where the furnace is firing (tubes hot).

    Uses the median tube COT across the pack so a single dead/zeroed TC does not
    flip the whole furnace offline.
    """
    med = cot.median(axis=1)
    return med > temp_c


def cracking_mask(
    feed_total: pd.Series,
    cot: pd.DataFrame | None = None,
    feed_frac: float = FEED_FRAC,
    temp_c: float = ONLINE_TEMP_C,
) -> pd.Series:
    """Boolean series: True where the furnace is actively cracking.

    Cracking requires hydrocarbon feed. A decoke cuts the feed (while the box
    stays hot), so feed flow is the decoke discriminator. If feed is missing we
    fall back to the tube-temperature firing mask.
    """
    if feed_total is None or feed_total.dropna().empty:
        return online_mask(cot, temp_c) if cot is not None else pd.Series(dtype=bool)
    running_level = feed_total[feed_total > feed_total.max() * 0.1].median()
    mask = feed_total > feed_frac * running_level
    if cot is not None:
        mask = mask & online_mask(cot, temp_c).reindex(mask.index, fill_value=False)
    return mask.fillna(False)


def segment_runs(
    online: pd.Series,
    min_run_days: float = 3.0,
    min_gap_hours: float = 6.0,
) -> List[Run]:
    """Split the online mask into discrete runs separated by decoke gaps.

    Short online/offline blips are ignored (`min_run_days`, `min_gap_hours`) so
    transient TC dropouts don't fragment a real run.
    """
    idx = online.index
    step = (idx[1] - idx[0]).total_seconds() if len(idx) > 1 else 60.0
    min_gap_steps = max(1, int(min_gap_hours * 3600 / step))

    # Find contiguous True blocks.
    vals = online.fillna(False).to_numpy()
    runs: List[Run] = []
    n = len(vals)
    i = 0
    while i < n:
        if not vals[i]:
            i += 1
            continue
        j = i
        gap = 0
        last_true = i
        while j < n:
            if vals[j]:
                last_true = j
                gap = 0
            else:
                gap += 1
                if gap >= min_gap_steps:
                    break
            j += 1
        runs.append(Run(index=len(runs), start=idx[i], end=idx[last_true]))
        i = j

    runs = [r for r in runs if r.length_days >= min_run_days]
    return [Run(k, r.start, r.end) for k, r in enumerate(runs)]


def compute_delta(cot: pd.DataFrame, online: pd.Series) -> pd.DataFrame:
    """Delta_i(t) = COT_i - pack mean. NaN when the furnace is offline."""
    c = cot.where(online, np.nan)
    # Treat hard-zero / frozen TCs as missing so they don't bias the pack mean.
    c = c.where(c > ONLINE_TEMP_C, np.nan)
    pack_mean = c.mean(axis=1)
    return c.sub(pack_mean, axis=0)


def compute_delta_delta(
    delta: pd.DataFrame,
    runs: List[Run],
    baseline_hours: float = 12.0,
) -> pd.DataFrame:
    """DeltaDelta_i(t) = Delta_i(t) - start-of-run baseline, per run.

    Outside detected runs the result is NaN. The baseline for each run is the
    mean Delta over the first `baseline_hours` of that run.
    """
    dd = pd.DataFrame(np.nan, index=delta.index, columns=delta.columns)
    for r in runs:
        seg = delta.loc[r.start : r.end]
        if seg.empty:
            continue
        base_end = r.start + pd.Timedelta(hours=baseline_hours)
        baseline = seg.loc[r.start:base_end].mean(axis=0)
        dd.loc[r.start : r.end] = seg.sub(baseline, axis=1).values
    return dd


def run_age_days(index: pd.DatetimeIndex, runs: List[Run]) -> pd.Series:
    """Days since the start of the run each timestamp belongs to (NaN if none)."""
    age = pd.Series(np.nan, index=index)
    for r in runs:
        mask = (index >= r.start) & (index <= r.end)
        age.loc[mask] = (index[mask] - r.start).total_seconds() / 86400.0
    return age


def health_indicators(delta: pd.DataFrame, dd: pd.DataFrame) -> pd.DataFrame:
    """Scalar furnace-health series operators would watch.

    - delta_spread   : max-min tube Delta (instantaneous maldistribution)
    - dd_max         : worst (most positive) tube Delta-Delta
    - dd_abs_max     : largest |Delta-Delta| across tubes (decoke trigger proxy)
    - dd_p95         : 95th-percentile tube Delta-Delta (robust hot-tube drift)
    """
    return pd.DataFrame(
        {
            "delta_spread": delta.max(axis=1) - delta.min(axis=1),
            "dd_max": dd.max(axis=1),
            "dd_abs_max": dd.abs().max(axis=1),
            "dd_p95": dd.quantile(0.95, axis=1),
        }
    )


def steam_to_hc(feed: pd.DataFrame, steam: pd.DataFrame,
                feed_floor_frac: float = 0.3) -> pd.Series:
    """Furnace steam-to-hydrocarbon ratio (KG/H steam over NM3/H feed, summed
    across passes). One of the four severity levers.

    Only defined while the furnace is cracking: dividing by the tiny residual
    feed during a decoke would explode the ratio, so we blank it below
    `feed_floor_frac` of the running feed level.
    """
    f = feed.sum(axis=1)
    s = steam.sum(axis=1)
    running = f[f > f.max() * 0.1].median()
    f = f.where(f > feed_floor_frac * running, np.nan)
    return s / f
