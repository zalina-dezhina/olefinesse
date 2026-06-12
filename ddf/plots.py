"""Plotting for the Delta-Delta tags.

Every figure is saved to OUTPUT_DIR. Plots are intentionally operator-facing:
the same family of numbers the control room already watches, shown forward and
in trend form rather than as a matrix of instantaneous values.
"""
from __future__ import annotations

import os
from typing import List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import OUTPUT_DIR
from .deltadelta import Run

plt.rcParams.update({"figure.dpi": 120, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3})


def _save(fig, name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _shade_decokes(ax, runs: List[Run], index):
    """Lightly shade offline/decoke gaps between runs."""
    for a, b in zip(runs[:-1], runs[1:]):
        ax.axvspan(a.end, b.start, color="0.85", alpha=0.6, lw=0)


def plot_raw_cot(cot: pd.DataFrame, runs: List[Run], furnace: str) -> str:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for col in cot.columns:
        ax.plot(cot.index, cot[col], lw=0.4, alpha=0.7)
    _shade_decokes(ax, runs, cot.index)
    ax.set_title(f"{furnace} — raw per-tube coil-outlet skin temperatures "
                 f"({len(cot.columns)} tubes); grey = decoke/offline")
    ax.set_ylabel("Tube COT (°C)")
    ax.set_ylim(bottom=max(400, ax.get_ylim()[0]))
    return _save(fig, f"{furnace}_01_raw_cot.png")


def plot_delta(delta: pd.DataFrame, runs: List[Run], furnace: str) -> str:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for col in delta.columns:
        ax.plot(delta.index, delta[col], lw=0.4, alpha=0.7)
    _shade_decokes(ax, runs, delta.index)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"{furnace} — Delta: per-tube deviation from pack mean COT")
    ax.set_ylabel("Delta (°C)")
    return _save(fig, f"{furnace}_02_delta.png")


def plot_delta_delta(dd: pd.DataFrame, runs: List[Run], furnace: str) -> str:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for col in dd.columns:
        ax.plot(dd.index, dd[col], lw=0.5, alpha=0.75)
    _shade_decokes(ax, runs, dd.index)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"{furnace} — Delta-Delta: per-tube drift since start of run "
                 "(furnace-health signal)")
    ax.set_ylabel("Delta-Delta (°C)")
    return _save(fig, f"{furnace}_03_delta_delta.png")


def plot_dd_vs_runage(
    dd: pd.DataFrame, run_age: pd.Series, runs: List[Run], furnace: str
) -> str:
    """Overlay every run's worst-tube Delta-Delta on a common run-age axis.

    This is the 'library of overlapping trajectories' the value-prop note calls
    the core asset for a time-series forecaster.
    """
    fig, ax = plt.subplots(figsize=(11, 5))
    dd_max = dd.max(axis=1)
    cmap = plt.cm.viridis(np.linspace(0, 1, max(1, len(runs))))
    for r, c in zip(runs, cmap):
        seg_age = run_age.loc[r.start : r.end]
        seg_dd = dd_max.loc[r.start : r.end]
        ax.plot(seg_age, seg_dd, lw=1.1, color=c,
                label=f"run {r.index} ({r.length_days:.0f}d)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("Run age (days since decoke)")
    ax.set_ylabel("Worst-tube Delta-Delta (°C)")
    ax.set_title(f"{furnace} — Delta-Delta trajectory library (one line per run)")
    ax.legend(fontsize=7, ncol=2)
    return _save(fig, f"{furnace}_04_dd_trajectories.png")


def plot_health_and_drivers(
    health: pd.DataFrame,
    feed_total: pd.Series,
    steam_hc: pd.Series,
    runs: List[Run],
    furnace: str,
) -> str:
    """Stacked panel: health signal against the severity levers that drive it."""
    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
    ax0, ax1, ax2 = axes

    ax0.plot(health.index, health["dd_abs_max"], color="crimson", lw=0.8,
             label="|Delta-Delta| max")
    ax0.plot(health.index, health["dd_p95"], color="darkorange", lw=0.8,
             label="Delta-Delta p95")
    ax0.set_ylabel("Health (°C)")
    ax0.legend(fontsize=7)
    ax0.set_title(f"{furnace} — furnace-health signal vs severity levers")

    ax1.plot(feed_total.index, feed_total, color="navy", lw=0.7)
    ax1.set_ylabel("Total HC feed\n(NM3/H)")

    ax2.plot(steam_hc.index, steam_hc, color="teal", lw=0.7)
    ax2.set_ylabel("Steam/HC\n(KG per NM3)")

    for ax in axes:
        _shade_decokes(ax, runs, health.index)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return _save(fig, f"{furnace}_05_health_vs_drivers.png")


def plot_yield_vs_dd(
    health: pd.DataFrame, c2h4: Optional[pd.Series], furnace: str
) -> Optional[str]:
    """Effluent ethylene (GC) against the health signal — the yield-mapping view."""
    if c2h4 is None or c2h4.dropna().empty:
        return None
    df = pd.concat([health["dd_abs_max"], c2h4.rename("C2H4")], axis=1).dropna()
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(7, 5.5))
    sc = ax.scatter(df["dd_abs_max"], df["C2H4"], c=mdates.date2num(df.index),
                    cmap="plasma", s=8, alpha=0.6)
    ax.set_xlabel("|Delta-Delta| max (°C)  —  furnace health")
    ax.set_ylabel("Effluent C2H4 (WT%)")
    ax.set_title(f"{furnace} — ethylene yield vs furnace health")
    cb = fig.colorbar(sc, ax=ax)
    cb.ax.yaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return _save(fig, f"{furnace}_06_yield_vs_dd.png")


def plot_fleet_health(fleet: pd.DataFrame, smooth_hours: float = 24.0) -> str:
    """Worst-tube Delta-Delta for every furnace on one axis — the health ranking
    that enables load allocation across furnaces.

    Raw 15-20 min data is noisy across seven furnaces, so we overlay a rolling
    median (default 1 day) which is the legible health-ranking an operator would
    read: lower line = healthier furnace = preferred destination for feed.
    """
    fig, ax = plt.subplots(figsize=(13, 5.5))
    if isinstance(fleet.index, pd.DatetimeIndex) and len(fleet.index) > 1:
        step = (fleet.index[1] - fleet.index[0]).total_seconds() / 3600.0
        win = max(1, int(smooth_hours / max(step, 1e-9)))
    else:
        win = 1
    for col in fleet.columns:
        sm = fleet[col].rolling(win, min_periods=max(1, win // 3)).median()
        ax.plot(fleet.index, fleet[col], lw=0.4, alpha=0.18)
        ax.plot(sm.index, sm, lw=1.3, label=col)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Worst-tube Delta-Delta (°C)")
    ax.set_title(f"Fleet furnace-health comparison "
                 f"(worst-tube Delta-Delta, {smooth_hours:.0f}h rolling median)")
    ax.legend(fontsize=8, ncol=4)
    return _save(fig, "fleet_health_comparison.png")
