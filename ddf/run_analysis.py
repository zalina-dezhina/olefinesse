"""End-to-end Delta-Delta analysis driver.

Usage (from the repo root):

    python -m ddf.run_analysis --furnace 1HA --start 2025-02-05 --end 2026-03-20
    python -m ddf.run_analysis --fleet               # all furnaces, health compare
    python -m ddf.run_analysis --coverage            # just data-availability report

It builds the tag catalog, loads the tube-skin COTs and severity levers, rebuilds
Delta / Delta-Delta, segments the run/decoke cycle, writes a per-furnace summary
table, and renders the figure set into ./output.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from . import config, data, deltadelta as ddmod, plots, tags


def analyse_furnace(spark, catalog, furnace, start, end, bucket=15, make_plots=True):
    sub = tags.tags_for(catalog, furnace)
    cot_ids = sub[sub.role == "tube_COT"].ID.tolist()
    feed_ids = sub[sub.role == "feed_flow"].ID.tolist()
    steam_ids = sub[sub.role == "dil_steam"].ID.tolist()
    gc_ids = sub[sub.role == "effluent_GC"].ID.tolist()

    if not cot_ids:
        print(f"[{furnace}] no tube-COT tags found, skipping")
        return None

    print(f"[{furnace}] loading {len(cot_ids)} COT + {len(feed_ids)} feed + "
          f"{len(steam_ids)} steam + {len(gc_ids)} GC tags @ {bucket}min ...")
    cot = data.load_wide(spark, cot_ids, start, end, bucket)
    feed = data.load_wide(spark, feed_ids, start, end, bucket) if feed_ids else pd.DataFrame()
    steam = data.load_wide(spark, steam_ids, start, end, bucket) if steam_ids else pd.DataFrame()
    gc = data.load_wide(spark, gc_ids, start, end, bucket) if gc_ids else pd.DataFrame()
    if cot.empty:
        print(f"[{furnace}] no COT data in window")
        return None

    feed_total = (feed.sum(axis=1).reindex(cot.index)
                  if not feed.empty else pd.Series(index=cot.index, dtype=float))
    # Runs = cracking campaigns between decokes, detected from the HC feed being
    # cut (the furnace stays hot through a decoke, so temperature alone misses it).
    cracking = ddmod.cracking_mask(feed_total, cot)
    runs = ddmod.segment_runs(cracking)
    delta = ddmod.compute_delta(cot, cracking)
    dd = ddmod.compute_delta_delta(delta, runs)
    age = ddmod.run_age_days(cot.index, runs)
    health = ddmod.health_indicators(delta, dd)
    steam_hc = (ddmod.steam_to_hc(feed, steam)
                if not feed.empty and not steam.empty
                else pd.Series(index=cot.index, dtype=float))
    # Effluent ethylene column (description ...C2H4); robust to missing.
    c2h4 = None
    if not gc.empty:
        c2h4_ids = sub[(sub.role == "effluent_GC") &
                       sub.Description.str.contains("C2H4", na=False)].ID.tolist()
        cols = [c for c in c2h4_ids if c in gc.columns]
        if cols:
            c2h4 = gc[cols[0]]

    print(f"[{furnace}] detected {len(runs)} runs; "
          f"run lengths (d): {[round(r.length_days, 1) for r in runs]}")

    if make_plots:
        for fn, args in [
            (plots.plot_raw_cot, (cot, runs, furnace)),
            (plots.plot_delta, (delta, runs, furnace)),
            (plots.plot_delta_delta, (dd, runs, furnace)),
            (plots.plot_dd_vs_runage, (dd, age, runs, furnace)),
            (plots.plot_health_and_drivers, (health, feed_total, steam_hc, runs, furnace)),
            (plots.plot_yield_vs_dd, (health, c2h4, furnace)),
        ]:
            p = fn(*args)
            if p:
                print(f"   wrote {p}")

    # Per-run summary table.
    rows = []
    for r in runs:
        seg = dd.loc[r.start:r.end]
        rows.append({
            "furnace": furnace, "run": r.index,
            "start": r.start, "end": r.end,
            "length_days": round(r.length_days, 2),
            "dd_abs_max_end": round(float(health["dd_abs_max"].loc[r.start:r.end]
                                          .tail(48).median()), 2),
            "dd_peak": round(float(seg.abs().max().max()), 2),
        })
    summary = pd.DataFrame(rows)
    return {"furnace": furnace, "runs": runs, "dd": dd, "health": health,
            "age": age, "summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--furnace", default="1HA")
    ap.add_argument("--start", default="2025-02-05")
    ap.add_argument("--end", default="2026-03-20")
    ap.add_argument("--bucket", type=int, default=15, help="averaging window (min)")
    ap.add_argument("--fleet", action="store_true", help="run all furnaces + compare")
    ap.add_argument("--coverage", action="store_true", help="data-availability report only")
    ap.add_argument("--refresh-catalog", action="store_true")
    args = ap.parse_args()

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    spark = data.get_spark()
    catalog = tags.build_catalog(spark, refresh=args.refresh_catalog)
    print("Tag catalog (counts per furnace/role):")
    print(tags.summarize(catalog).to_string())

    if args.coverage:
        ids = catalog[catalog.furnace == args.furnace].ID.tolist()
        cov = data.coverage(spark, ids)
        print(cov.to_string(index=False))
        cov.to_csv(os.path.join(config.OUTPUT_DIR, f"{args.furnace}_coverage.csv"), index=False)
        return

    furnaces = config.FURNACES if args.fleet else [args.furnace]
    results, fleet = [], {}
    for f in furnaces:
        res = analyse_furnace(spark, catalog, f, args.start, args.end,
                              bucket=args.bucket, make_plots=not args.fleet or True)
        if res:
            results.append(res["summary"])
            fleet[f] = res["dd"].max(axis=1)

    if results:
        summary = pd.concat(results, ignore_index=True)
        out = os.path.join(config.OUTPUT_DIR, "run_summary.csv")
        summary.to_csv(out, index=False)
        print("\n=== Run summary ===")
        print(summary.to_string(index=False))
        print(f"\nwrote {out}")

    if args.fleet and len(fleet) > 1:
        fleet_df = pd.DataFrame(fleet)
        p = plots.plot_fleet_health(fleet_df)
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
