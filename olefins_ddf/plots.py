"""Figures for the Delta-Delta and correlation analyses. All saved to OUTPUT_DIR."""
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
from .runs import Run

plt.rcParams.update({"figure.dpi": 120, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3})


def _save(fig, name: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _shade(ax, runs: List[Run]):
    for a, b in zip(runs[:-1], runs[1:]):
        ax.axvspan(a.end, b.start, color="0.85", alpha=0.6, lw=0)


# --- Delta-Delta figures -----------------------------------------------------

def plot_raw_cot(cot, runs, furnace):
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for c in cot.columns:
        ax.plot(cot.index, cot[c], lw=0.4, alpha=0.7)
    _shade(ax, runs)
    ax.set_title(f"{furnace} - raw per-tube coil-outlet skin temperatures "
                 f"({len(cot.columns)} tubes); grey = decoke/offline")
    ax.set_ylabel("Tube COT (°C)")
    ax.set_ylim(bottom=max(400, ax.get_ylim()[0]))
    return _save(fig, f"{furnace}_01_raw_cot.png")


def plot_delta(delta, runs, furnace):
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for c in delta.columns:
        ax.plot(delta.index, delta[c], lw=0.4, alpha=0.7)
    _shade(ax, runs); ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"{furnace} - Delta: per-tube deviation from pack-mean COT")
    ax.set_ylabel("Delta (°C)")
    return _save(fig, f"{furnace}_02_delta.png")


def plot_delta_delta(dd, runs, furnace):
    fig, ax = plt.subplots(figsize=(13, 4.5))
    for c in dd.columns:
        ax.plot(dd.index, dd[c], lw=0.5, alpha=0.75)
    _shade(ax, runs); ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"{furnace} - Delta-Delta: per-tube drift since start of run "
                 "(furnace-health signal)")
    ax.set_ylabel("Delta-Delta (°C)")
    return _save(fig, f"{furnace}_03_delta_delta.png")


def plot_dd_trajectories(dd, run_age, runs, furnace):
    fig, ax = plt.subplots(figsize=(11, 5))
    dd_max = dd.max(axis=1)
    cmap = plt.cm.viridis(np.linspace(0, 1, max(1, len(runs))))
    for r, c in zip(runs, cmap):
        ax.plot(run_age.loc[r.start:r.end], dd_max.loc[r.start:r.end], lw=1.0,
                color=c, label=f"run {r.index} ({r.length_days:.0f}d)")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("Run age (days since decoke)")
    ax.set_ylabel("Worst-tube Delta-Delta (°C)")
    ax.set_title(f"{furnace} - Delta-Delta trajectory library (one line per run)")
    ax.legend(fontsize=7, ncol=2)
    return _save(fig, f"{furnace}_04_dd_trajectories.png")


def plot_health_vs_drivers(feat, runs, furnace):
    fig, axes = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
    a, b, c, d = axes
    a.plot(feat.index, feat["dd_abs_max"], color="crimson", lw=0.7, label="|ΔΔ| max")
    a.plot(feat.index, feat["coking_rate"], color="purple", lw=0.6, label="coking rate (°C/d)")
    a.set_ylabel("health"); a.legend(fontsize=7)
    a.set_title(f"{furnace} - furnace health vs severity levers")
    b.plot(feat.index, feat["cot"], color="firebrick", lw=0.7)
    b.set_ylabel("COT (°C)")
    c.plot(feat.index, feat["feed_total"], color="navy", lw=0.7)
    c.set_ylabel("HC feed\n(NM3/H)")
    d.plot(feat.index, feat["steam_hc"], color="teal", lw=0.7)
    d.set_ylabel("Steam/HC")
    for ax in axes:
        _shade(ax, runs)
    d.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    return _save(fig, f"{furnace}_05_health_vs_drivers.png")


def plot_fleet_health(fleet: pd.DataFrame, smooth_hours: float = 24.0):
    fig, ax = plt.subplots(figsize=(13, 5.5))
    step = (fleet.index[1] - fleet.index[0]).total_seconds() / 3600.0
    win = max(1, int(smooth_hours / max(step, 1e-9)))
    for col in fleet.columns:
        sm = fleet[col].rolling(win, min_periods=max(1, win // 3)).median()
        ax.plot(fleet.index, fleet[col], lw=0.4, alpha=0.15)
        ax.plot(sm.index, sm, lw=1.3, label=col)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("Worst-tube Delta-Delta (°C)")
    ax.set_title(f"Fleet furnace-health comparison ({smooth_hours:.0f}h rolling median)")
    ax.legend(fontsize=8, ncol=4)
    return _save(fig, "fleet_health_comparison.png")


# --- Correlation figures -----------------------------------------------------

def plot_corr_heatmap(corr: pd.DataFrame, furnace: str, method: str = "spearman"):
    fig, ax = plt.subplots(figsize=(0.6 * len(corr) + 3, 0.6 * len(corr) + 2))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index, fontsize=7)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if abs(v) > 0.6 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(f"{furnace} - {method} correlation (cracking periods)")
    return _save(fig, f"{furnace}_07_corr_heatmap.png")


def plot_driver_target(dtc: pd.DataFrame, target: str, furnace: str):
    if dtc.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(dtc) + 1.5))
    y = np.arange(len(dtc))
    ax.barh(y, dtc["spearman"], color=["crimson" if v > 0 else "steelblue" for v in dtc["spearman"]])
    ax.set_yticks(y); ax.set_yticklabels(dtc["driver"], fontsize=8)
    ax.invert_yaxis(); ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("Spearman correlation"); ax.set_xlim(-1, 1)
    ax.set_title(f"{furnace} - drivers of {target}")
    return _save(fig, f"{furnace}_08_drivers_of_{target}.png")


def plot_lagged_xcorr(xc: pd.DataFrame, x: str, y: str, furnace: str, step_min: int):
    fig, ax = plt.subplots(figsize=(8, 4))
    hrs = xc["lag_steps"] * step_min / 60.0
    ax.plot(hrs, xc["corr"], lw=1.2)
    i = xc["corr"].abs().idxmax()
    ax.axvline(hrs.loc[i], color="crimson", ls="--", lw=0.8,
               label=f"peak @ {hrs.loc[i]:.1f} h (r={xc['corr'].loc[i]:.2f})")
    ax.axhline(0, color="k", lw=0.6); ax.axvline(0, color="0.6", lw=0.6)
    ax.set_xlabel(f"lag (hours): {x} leads {y} ->"); ax.set_ylabel("Pearson r")
    ax.set_title(f"{furnace} - lagged cross-correlation {x} vs {y}")
    ax.legend(fontsize=8)
    return _save(fig, f"{furnace}_09_xcorr_{x}_{y}.png")


def plot_pairscatter(feat, pairs, furnace):
    """Scatter grid of key driver/response pairs, coloured by run age."""
    d = feat[feat.get("cracking", True) == True]
    n = len(pairs)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 4))
    if n == 1:
        axes = [axes]
    sc = None
    for ax, (x, y) in zip(axes, pairs):
        cols = list(dict.fromkeys([x, y, "run_age_days"]))  # unique, preserve order
        sub = d[cols].apply(pd.to_numeric, errors="coerce").dropna()
        if sub.empty:
            ax.set_visible(False); continue
        sc = ax.scatter(sub[x], sub[y], c=sub["run_age_days"], cmap="viridis", s=5, alpha=0.4)
        ax.set_xlabel(x); ax.set_ylabel(y)
        r = sub[x].corr(sub[y], method="spearman")
        ax.set_title(f"{x} vs {y}  (ρ={r:.2f})", fontsize=9)
    if sc is not None:
        fig.colorbar(sc, ax=axes, fraction=0.025, pad=0.02, label="run age (d)")
    fig.suptitle(f"{furnace} - key driver/response relationships", y=1.02)
    return _save(fig, f"{furnace}_10_pairscatter.png")


# --- Run-structure figures ---------------------------------------------------

def plot_run_lengths(run_summary: pd.DataFrame):
    """Run-length distribution + per-furnace timeline - shows runs are NOT a
    clockwork 25 days."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5),
                             gridspec_kw={"width_ratios": [1, 2]})
    rs = run_summary.dropna(subset=["length_days"])
    # left: histogram
    axes[0].hist(rs["length_days"], bins=range(0, 40, 2), color="steelblue", edgecolor="w")
    axes[0].axvline(25, color="crimson", ls="--", label="nominal 25 d")
    axes[0].axvline(rs["length_days"].median(), color="k", ls=":",
                    label=f"median {rs['length_days'].median():.1f} d")
    axes[0].set_xlabel("Run length (days)"); axes[0].set_ylabel("count")
    axes[0].set_title("Run-length distribution (all furnaces)")
    axes[0].legend(fontsize=8)
    # right: timeline (gantt-ish) per furnace
    furs = sorted(rs["furnace"].unique())
    ymap = {f: i for i, f in enumerate(furs)}
    cmap = plt.cm.tab20(np.linspace(0, 1, len(rs)))
    for k, (_, row) in enumerate(rs.iterrows()):
        y = ymap[row["furnace"]]
        axes[1].barh(y, row["length_days"], left=row["start"], height=0.6,
                     color=cmap[k % len(cmap)], edgecolor="w")
    axes[1].set_yticks(range(len(furs))); axes[1].set_yticklabels(furs)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[1].set_title("Run/decoke timeline per furnace (bar = run, gap = decoke/offline)")
    return _save(fig, "run_lengths.png")


def plot_data_coverage(cov_by_year: pd.DataFrame, roles_map: dict):
    """Year-by-year sample counts per role - the data-depth answer."""
    df = cov_by_year.copy()
    df["role"] = df["ID"].map(roles_map)
    pivot = df.groupby(["role", "yr"])["n"].sum().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 5))
    bottom = np.zeros(pivot.shape[1])
    for role in pivot.index:
        ax.bar(pivot.columns.astype(str), pivot.loc[role], bottom=bottom, label=role)
        bottom += pivot.loc[role].values
    ax.set_ylabel("samples / year"); ax.set_xlabel("year")
    ax.set_title("Historian data depth by role (samples per year)")
    ax.legend(fontsize=7, ncol=2)
    return _save(fig, "data_coverage_by_year.png")
