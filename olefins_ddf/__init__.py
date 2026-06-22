"""olefins_ddf - Delta-Delta furnace-health analysis & forecasting toolkit.

Delta-Delta is the run-normalised per-tube coil-outlet skin-temperature drift
that operators use as the olefins furnace health / coking signal. This package
locates the relevant DCS tags, loads their history from the Unity Catalog
historian, reconstructs Delta / Delta-Delta, segments the run/decoke cycle,
builds a unified feature matrix, and runs correlation analysis.

See docs/ for the methodology, data dictionary, and the running research log.
"""
__all__ = [
    "catalog", "config", "correlations", "deltadelta", "features",
    "io_events", "plots", "runs",
]
__version__ = "0.2.0"
