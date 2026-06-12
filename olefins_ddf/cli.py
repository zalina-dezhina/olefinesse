"""Command-line driver for the olefins Delta-Delta analyses.

    python -m olefins_ddf <command> [options]

commands:
  furnace    Full Delta-Delta + correlation analysis for one furnace.
  fleet      All furnaces; fleet health-ranking + pooled run-length stats.
  coverage   Historian data-depth report (samples per year per role).
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from . import catalog as cat
from . import config, correlations, deltadelta as ddm, features, io_events, plots
from . import runs as runsmod


def _analyse(spark, catalog, furnace, start, end, bucket, use_long_tc, do_plots=True):
    feat, runs = features.build_feature_matrix(
        spark, catalog, furnace, start, end, bucket, use_long_tc=use_long_tc)
    if feat.empty:
        print(f"[{furnace}] no data in window"); return None
    print(f"[{furnace}] {len(runs)} runs; lengths(d): "
          f"{[round(r.length_days,1) for r in runs]}")

    # Delta-Delta figures need the raw tube frame; rebuild it cheaply from feat's
    # span via the same loader so we can render the per-tube views.
    if do_plots:
        sub = cat.tags_for(catalog, furnace, ["tube_COT_long" if use_long_tc else "tube_COT"])
        cot = io_events.load_wide(spark, sub.ID.tolist(), start, end, bucket)
        crk = runsmod.cracking_mask(feat["feed_total"], cot)
        delta = ddm.compute_delta(cot, crk)
        dd = ddm.compute_delta_delta(delta, runs)
        age = runsmod.run_age_days(cot.index, runs)
        for p in [
            plots.plot_raw_cot(cot, runs, furnace),
            plots.plot_delta(delta, runs, furnace),
            plots.plot_delta_delta(dd, runs, furnace),
            plots.plot_dd_trajectories(dd, age, runs, furnace),
            plots.plot_health_vs_drivers(feat, runs, furnace),
        ]:
            print("   wrote", p)

        # Correlation suite
        corr = correlations.correlation_matrix(feat, method="spearman")
        print("   wrote", plots.plot_corr_heatmap(corr, furnace))
        for target in ("coking_rate", "dd_abs_max"):
            dtc = correlations.driver_target_corr(feat, target)
            p = plots.plot_driver_target(dtc, target, furnace)
            if p:
                print("   wrote", p)
        # lag: severity (COT) leading the health response
        xc = correlations.lagged_xcorr(feat, "cot", "dd_abs_max")
        print("   wrote", plots.plot_lagged_xcorr(xc, "cot", "dd_abs_max", furnace, bucket))
        pairs = [("run_age_days", "dd_abs_max"), ("cot", "coking_rate"),
                 ("steam_hc", "coking_rate")]
        print("   wrote", plots.plot_pairscatter(feat, pairs, furnace))

    # persist feature matrix + per-run summary
    feat.to_parquet(os.path.join(config.OUTPUT_DIR, f"{furnace}_features.parquet"))
    return feat, runs


def main():
    ap = argparse.ArgumentParser(prog="olefins_ddf")
    ap.add_argument("command", choices=["furnace", "fleet", "coverage"])
    ap.add_argument("--furnace", default="1HA")
    ap.add_argument("--start", default=config.DENSE_TC_START)
    ap.add_argument("--end", default=config.DATA_END)
    ap.add_argument("--bucket", type=int, default=30)
    ap.add_argument("--long-history", action="store_true",
                    help="use the 8-tube BANK proxy (2019+) instead of dense TCs")
    ap.add_argument("--refresh-catalog", action="store_true")
    args = ap.parse_args()

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    spark = io_events.get_spark()
    catalog = cat.build_catalog(spark, refresh=args.refresh_catalog)
    print("Tag catalog (counts per furnace/role):")
    print(cat.summarize(catalog).to_string(), "\n")

    if args.command == "coverage":
        sub = cat.tags_for(catalog, args.furnace)
        roles_map = dict(zip(sub.ID, sub.role))
        cov = io_events.coverage(spark, sub.ID.tolist(), by_year=True)
        print(cov.pivot_table(index="ID", columns="yr", values="n",
                              fill_value=0).to_string())
        print("wrote", plots.plot_data_coverage(cov, roles_map))
        return

    furnaces = config.FURNACES if args.command == "fleet" else [args.furnace]
    run_tables, fleet = [], {}
    for f in furnaces:
        res = _analyse(spark, catalog, f, args.start, args.end, args.bucket,
                       args.long_history, do_plots=(args.command == "furnace"))
        if res:
            feat, runs = res
            run_tables.append(runsmod.run_table(runs, f))
            fleet[f] = feat["dd_abs_max"]

    if run_tables:
        rs = pd.concat(run_tables, ignore_index=True)
        rs.to_csv(os.path.join(config.OUTPUT_DIR, "run_summary.csv"), index=False)
        print("\n=== Run-length stats ===")
        print(rs.groupby("furnace")["length_days"].describe()[["count", "mean", "std", "min", "max"]].round(1).to_string())
        if args.command == "fleet":
            print("wrote", plots.plot_run_lengths(rs))
            print("wrote", plots.plot_fleet_health(pd.DataFrame(fleet)))


if __name__ == "__main__":
    main()
