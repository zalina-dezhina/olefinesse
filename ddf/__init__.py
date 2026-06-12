"""Delta-Delta forecasting toolkit for the Indorama olefins furnaces.

Delta      = deviation of an individual tube's outlet skin temperature from its
             furnace/pass average at a given instant.
Delta-Delta = how that per-tube deviation has *drifted* since the start of the
             current run (post-decoke baseline). It is the furnace-health /
             coking signal operators act on to decide when to decoke.

This package locates the relevant DCS tags, loads their high-frequency history
from the Unity Catalog time-series tables, reconstructs Delta and Delta-Delta,
segments the run/decoke cycle, and plots everything.
"""
from .config import CLUSTER_ID, CATALOG, EVENTS, METADATA, FURNACES
