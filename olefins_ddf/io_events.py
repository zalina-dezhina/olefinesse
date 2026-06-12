"""Load high-frequency tag history from the time-series events table.

The events table is an ~6.6-billion-row EAV store (one row per tag-sample):
``ID | EventTime | Status | Value (variant)``. We never pull raw rows; Spark
filters to the requested IDs + window, keeps Status='Good', casts the variant
Value to double, and averages into fixed time buckets before the data crosses
the wire. The result is pivoted to a wide, regularly-gridded pandas frame.
"""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

from .config import CLUSTER_ID, EVENTS


def get_spark(cluster_id: Optional[str] = None):
    """databricks-connect Spark session bound to the (running) cluster."""
    from databricks.connect import DatabricksSession

    return DatabricksSession.builder.clusterId(cluster_id or CLUSTER_ID).getOrCreate()


def load_wide(
    spark,
    tag_ids: Iterable[str],
    start: str,
    end: str,
    bucket_minutes: int = 15,
) -> pd.DataFrame:
    """Wide, time-bucketed, regularly-gridded frame; one column per tag."""
    tag_ids = list(tag_ids)
    if not tag_ids:
        return pd.DataFrame()
    inlist = ",".join(f"'{t}'" for t in tag_ids)
    secs = bucket_minutes * 60
    q = f"""
        SELECT ID,
               timestamp_seconds(floor(unix_timestamp(EventTime)/{secs})*{secs}) AS ts,
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
    wide = long.pivot(index="ts", columns="ID", values="value").sort_index()
    wide.index = pd.to_datetime(wide.index)
    full = pd.date_range(wide.index.min(), wide.index.max(), freq=f"{bucket_minutes}min")
    wide = wide.reindex(full)
    wide.index.name = "ts"
    return wide.reindex(columns=[t for t in tag_ids if t in wide.columns])


def coverage(spark, tag_ids: Iterable[str], by_year: bool = False) -> pd.DataFrame:
    """Per-tag count / EventTime span (optionally broken out by year)."""
    inlist = ",".join(f"'{t}'" for t in tag_ids)
    if by_year:
        q = f"""SELECT ID, YEAR(EventTime) yr, COUNT(*) n
                FROM {EVENTS} WHERE ID IN ({inlist})
                GROUP BY ID, YEAR(EventTime) ORDER BY ID, yr"""
        return spark.sql(q).toPandas()
    q = f"""SELECT ID, COUNT(*) n, MIN(EventTime) t0, MAX(EventTime) t1,
                   MIN(CAST(Value AS DOUBLE)) vmin, MAX(CAST(Value AS DOUBLE)) vmax,
                   AVG(CAST(Value AS DOUBLE)) vmean
            FROM {EVENTS} WHERE ID IN ({inlist})
            GROUP BY ID ORDER BY ID"""
    return spark.sql(q).toPandas()
