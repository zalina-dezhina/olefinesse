"""Environment & domain configuration for the olefins Delta-Delta toolkit."""
from __future__ import annotations

import os

# --- Compute / data access ---------------------------------------------------
# The historian is exposed through a running Databricks cluster reached via
# databricks-connect (plain pyspark fails with MASTER_URL_NOT_SET). The research
# cluster id is ephemeral; override with DDF_CLUSTER_ID or look it up with
# `databricks clusters list`.
CLUSTER_ID = os.environ.get("DDF_CLUSTER_ID", "0612-154022-0181931u")

CATALOG = os.environ.get(
    "DDF_CATALOG", "indorama_corporate_olefins_paas_azure_weu_dev_bronze"
)
EVENTS = f"{CATALOG}.timeseries.events"      # long EAV: ID, EventTime, Status, Value(variant)
METADATA = f"{CATALOG}.timeseries.metadata"  # tag dictionary: ID, Description, UoM, ...

# --- Plant topology ----------------------------------------------------------
# Seven near-identical cracking furnaces (KBR: first six identical, 7th
# nominally identical). Canonical labels used throughout the codebase.
FURNACES = ["1HA", "1HB", "1HC", "1HD", "1HE", "1HF", "1HG"]

# The DCS uses several internal numbering schemes; each is internally consistent.
# Hundreds-block -> furnace for the TI tube thermocouples / TC COT controllers /
# PC convection-draft tags.
BLOCK_TO_FURNACE = {8: "1HA", 9: "1HB", 10: "1HC", 11: "1HD",
                    12: "1HE", 13: "1HF", 14: "1HG"}

# --- Data availability (discovered, see docs/data_dictionary.md) -------------
# Process drivers (feed, steam, COT, pressure, draft, feed GC) reach back to 2019.
# The dense per-tube skin TCs (Delta-Delta source) only start 2025-02; an 8-tube
# proxy (BANK PQE TCs) reaches back to 2019.
HIST_START = "2019-01-01"
DENSE_TC_START = "2025-02-05"
DATA_END = "2026-03-20"

OUTPUT_DIR = os.environ.get(
    "DDF_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "output"),
)
