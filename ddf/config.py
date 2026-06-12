"""Environment configuration for the Delta-Delta toolkit.

Everything that is environment- or deployment-specific lives here so the rest of
the code stays portable.
"""
import os

# Running Databricks cluster used via databricks-connect. Override with the
# DDF_CLUSTER_ID env var if you run this against a different cluster.
CLUSTER_ID = os.environ.get("DDF_CLUSTER_ID", "0612-154022-0181931u")

# Unity Catalog locations of the historian data.
CATALOG = os.environ.get(
    "DDF_CATALOG", "indorama_corporate_olefins_paas_azure_weu_dev_bronze"
)
EVENTS = f"{CATALOG}.timeseries.events"      # long/EAV table: ID, EventTime, Value, Status
METADATA = f"{CATALOG}.timeseries.metadata"  # tag dictionary: ID, Description, UoM, ...

# The seven near-identical cracking furnaces (KBR: first six identical, 7th
# nominally identical). Letter is the furnace suffix used throughout the DCS.
FURNACES = ["1HA", "1HB", "1HC", "1HD", "1HE", "1HF", "1HG"]

# Default output directory for figures / derived tables.
OUTPUT_DIR = os.environ.get(
    "DDF_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "output"),
)
