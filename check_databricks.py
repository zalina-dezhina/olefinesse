"""
check_databricks.py — verify that databricks-connect is configured correctly
and that the research cluster is reachable.

Run from the repo root:
    python check_databricks.py

What it checks:
  1. Environment variables / ~/.databrickscfg are present
  2. databricks-connect can open a Spark session
  3. The research cluster responds (metadata table query)
  4. Prints available clusters so you can update DDF_CLUSTER_ID if needed
"""
from __future__ import annotations

import os
import sys


def load_dotenv():
    """Load .env from the repo root (if present) without requiring python-dotenv."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def check_env():
    print("── 1. Environment ──────────────────────────────────────────")
    host = os.environ.get("DATABRICKS_HOST", "")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    cluster_id = os.environ.get("DDF_CLUSTER_ID", "0612-154022-0181931u")

    if host:
        print(f"  DATABRICKS_HOST    : {host}")
    else:
        print("  DATABRICKS_HOST    : ⚠  not set — will fall back to ~/.databrickscfg")

    if token:
        print(f"  DATABRICKS_TOKEN   : {'*' * 8}...{token[-4:]} (set)")
    else:
        print("  DATABRICKS_TOKEN   : ⚠  not set — will fall back to ~/.databrickscfg")

    print(f"  DDF_CLUSTER_ID     : {cluster_id}")

    cfg = os.path.expanduser("~/.databrickscfg")
    if os.path.exists(cfg):
        print(f"  ~/.databrickscfg   : found ✓")
    else:
        print("  ~/.databrickscfg   : not found")

    if not host and not token and not os.path.exists(cfg):
        print("\n  ✗ No credentials found.")
        print("  Steps:")
        print("    1. Copy .env.template → .env and fill in DATABRICKS_HOST + DATABRICKS_TOKEN")
        print("    OR run: databricks configure --token")
        sys.exit(1)

    return cluster_id


def check_import():
    print("\n── 2. databricks-connect import ────────────────────────────")
    try:
        from databricks.connect import DatabricksSession
        print("  databricks-connect : installed ✓")
        return DatabricksSession
    except ImportError:
        print("  ✗ databricks-connect is not installed.")
        print("  Run: pip install databricks-connect")
        sys.exit(1)


def check_spark(DatabricksSession, cluster_id):
    print(f"\n── 3. Spark session (cluster {cluster_id}) ──────────────────")
    try:
        spark = DatabricksSession.builder.clusterId(cluster_id).getOrCreate()
        print("  Spark session      : connected ✓")
        return spark
    except Exception as e:
        print(f"  ✗ Could not connect: {e}")
        print("  The cluster may be stopped. Run: databricks clusters start " + cluster_id)
        print("  Or check available clusters below.")
        return None


def check_catalog(spark):
    from olefins_ddf.config import METADATA
    print(f"\n── 4. Metadata table ({METADATA}) ──")
    try:
        n = spark.sql(f"SELECT COUNT(*) n FROM {METADATA}").collect()[0]["n"]
        print(f"  Tag count          : {n:,} ✓")
    except Exception as e:
        print(f"  ✗ Could not query metadata: {e}")


def list_clusters():
    print("\n── 5. Available clusters ────────────────────────────────────")
    try:
        import subprocess
        result = subprocess.run(
            ["databricks", "clusters", "list", "--output", "table"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print(result.stdout)
            print("  → Copy the cluster_id of the running research cluster")
            print("    and set DDF_CLUSTER_ID in your .env file.")
        else:
            print(f"  databricks CLI error: {result.stderr.strip()}")
    except FileNotFoundError:
        print("  databricks CLI not found. Install: pip install databricks-cli")
    except Exception as e:
        print(f"  {e}")


if __name__ == "__main__":
    load_dotenv()
    cluster_id = check_env()
    DatabricksSession = check_import()
    spark = check_spark(DatabricksSession, cluster_id)
    if spark:
        check_catalog(spark)
        print("\n  ✓ All checks passed. You're ready to run the toolkit.")
        print("    python -m olefins_ddf furnace --furnace 1HA")
    else:
        list_clusters()
