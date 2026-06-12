"""Load high-frequency tag history from the time-series events table.

The events table is an ~6.6-billion-row EAV store (one row per tag-sample):
    ID (tag) | EventTime | Status | Value (variant)

We never pull raw rows for plotting. Instead we let Spark do the heavy lifting:
filter to the requested tag IDs and date window, keep Status='Good', cast the
variant Value to double, and average into fixed time buckets (default 15 min).
That collapses ~1/min data ~15x before it crosses the wire, then we pivot to a
wide, time-indexed pandas frame (one column per tag).
"""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from .config import EVENTS


def get_spark(cluster_id: Optional[str] = None):
    """Return a databricks-connect Spark session bound to the cluster."""
    from databricks.connect import DatabricksSession

    from .config import CLUSTER_ID

    builder = DatabricksSession.builder
    builder = builder.clusterId(cluster_id or CLUSTER_ID)
    return builder.getOrCreate()


def load_wide(
    spark,
    tag_ids: Iterable[str],
    start: str,
    end: str,
    bucket_minutes: int = 15,
) -> pd.DataFrame:
    """Load tags as a wide, time-bucketed, time-indexed DataFrame.

    Parameters
    ----------
    tag_ids : tag IDs (e.g. ['01TI1001A.PV', ...]).
    start, end : ISO date/timestamp strings bounding EventTime (inclusive start).
    bucket_minutes : averaging window in minutes.

    Returns a DataFrame indexed by bucket start time, columns = tag IDs.
    """
    tag_ids = list(tag_ids)
    inlist = ",".join(f"'{t}'" for t in tag_ids)
    secs = bucket_minutes * 60
    q = f"""
        SELECT
            ID,
            timestamp_seconds(
                floor(unix_timestamp(EventTime) / {secs}) * {secs}
            ) AS ts,
            AVG(CAST(Value AS DOUBLE)) AS value
        FROM {EVENTS}
        WHERE ID IN ({inlist})
          AND Status = 'Good'
          AND EventTime >= '{start}' AND EventTime < '{end}'
          AND CAST(Value AS DOUBLE) IS NOT NULL
        GROUP BY ID, ts
    """
    long = spark.sql(q).toPandas()
    if long.empty:
        return pd.DataFrame()
    wide = (
        long.pivot(index="ts", columns="ID", values="value")
        .sort_index()
    )
    wide.index = pd.to_datetime(wide.index)
    # Stable, regular grid so downstream diffing/run-detection is well defined.
    full = pd.date_range(wide.index.min(), wide.index.max(), freq=f"{bucket_minutes}min")
    wide = wide.reindex(full)
    wide.index.name = "ts"
    # Keep tag column order deterministic.
    return wide.reindex(columns=[t for t in tag_ids if t in wide.columns])


def coverage(spark, tag_ids: Iterable[str]) -> pd.DataFrame:
    """Per-tag count and EventTime span — quick data-availability check."""
    inlist = ",".join(f"'{t}'" for t in tag_ids)
    q = f"""
        SELECT ID, COUNT(*) AS n,
               MIN(EventTime) AS t0, MAX(EventTime) AS t1,
               MIN(CAST(Value AS DOUBLE)) AS vmin,
               MAX(CAST(Value AS DOUBLE)) AS vmax
        FROM {EVENTS} WHERE ID IN ({inlist})
        GROUP BY ID ORDER BY ID
    """
    return spark.sql(q).toPandas()
