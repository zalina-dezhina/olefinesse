"""
view_results.py — browse all output figures with explanations.

Run from the repo root:
    python view_results.py
"""

import os
import glob
import math
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Descriptions for each chart type ─────────────────────────────────────────
DESCRIPTIONS = {
    "raw_cot": (
        "Raw Coil Outlet Temperatures",
        "Temperature of all 192 tube skin thermocouples over time.\n"
        "Vertical dashed lines = decoke events (run boundaries).\n"
        "Look for: sudden drops (decoke), gradual spread between tubes (coking)."
    ),
    "delta": (
        "Delta  (tube − pass average)",
        "Each tube's temperature minus the average of its pass (A/B/C/D).\n"
        "Removes furnace-wide drift; shows which tubes run hot or cold\n"
        "relative to their neighbours. Should be ~0 after a fresh decoke."
    ),
    "delta_delta": (
        "Delta-Delta  (coking signal)",
        "Delta re-baselined to zero at the start of every run.\n"
        "This is the primary health / coking indicator operators use.\n"
        "Grows as coke accumulates; triggers a decoke when it hits the limit."
    ),
    "dd_trajectories": (
        "Delta-Delta Trajectories by Run",
        "All Delta-Delta curves overlaid, x-axis = days since last decoke.\n"
        "Shows how fast coking progresses each run and whether runs are\n"
        "getting shorter (faster coking) or longer over time."
    ),
    "health_vs_drivers": (
        "Health vs Process Drivers",
        "Scatter plots of the Delta-Delta health metric against key\n"
        "process variables: run age, COT severity, feed rate, steam ratio.\n"
        "Steeper slope = stronger driver of coking."
    ),
    "pass_health": (
        "Per-Pass Health  (passes A / B / C / D)",
        "Delta-Delta broken out by pass. Shows whether coking is uniform\n"
        "across all four passes or concentrated in one — important for\n"
        "diagnosing feed/steam imbalances between passes."
    ),
    "pass_dd_dist": (
        "Delta-Delta Distribution by Pass",
        "Box / violin plots of tube Delta-Delta values per pass.\n"
        "Wide spread = tubes within a pass behave very differently.\n"
        "Skewed distribution may indicate individual bad tubes."
    ),
    "corr_heatmap": (
        "Spearman Correlation Heatmap",
        "Pairwise correlations between all features in the feature matrix.\n"
        "Dark red = strong positive correlation, dark blue = negative.\n"
        "Use to spot multicollinearity before building a forecast model."
    ),
    "drivers_of_coking_rate": (
        "Drivers of Coking Rate",
        "Ranked bar chart: which process variables most strongly correlate\n"
        "with the rate of Delta-Delta growth (coking speed).\n"
        "Top drivers are the levers operators can pull to slow coking."
    ),
    "drivers_of_dd_abs_max": (
        "Drivers of Peak Delta-Delta",
        "Same ranking but for the maximum Delta-Delta reached at end-of-run.\n"
        "Tells you what predicts how bad a run gets, not just how fast."
    ),
    "xcorr": (
        "Lagged Cross-Correlation  (COT → Delta-Delta)",
        "How many hours / days does a change in COT severity lead\n"
        "the Delta-Delta health response? Peak lag = process response time.\n"
        "Critical for setting the forecast horizon of the predictive model."
    ),
    "pairscatter": (
        "Key Pair Scatter Plots",
        "Three key relationships plotted directly:\n"
        "  • Run age vs Delta-Delta (coking grows with time)\n"
        "  • COT vs coking rate (severity drives coking speed)\n"
        "  • Steam/HC ratio vs coking rate (dilution slows coking)"
    ),
    "data_coverage": (
        "Data Coverage by Year",
        "Number of samples per tag per year from the historian.\n"
        "Process drivers (feed, steam, COT) reach back to 2019.\n"
        "Dense tube skin TCs only available from Feb 2025 onward."
    ),
    "fleet_health": (
        "Fleet Health Comparison  (all 7 furnaces)",
        "Side-by-side Delta-Delta health metric for furnaces 1HA–1HG.\n"
        "Shows which furnaces are coking faster or running in worse health.\n"
        "Use for prioritising which furnace to decoke next."
    ),
    "run_lengths": (
        "Run Length Distribution",
        "Histogram / box plot of days between decokes per furnace.\n"
        "Shorter runs = more frequent decoking = lower throughput.\n"
        "Target: understand what drives run length variability (17–25 days)."
    ),
}

def get_description(filename):
    name = filename.lower()
    for key, (title, desc) in DESCRIPTIONS.items():
        if key in name:
            return title, desc
    base = os.path.splitext(filename)[0].replace("_", " ").title()
    return base, ""

# ── Load all PNGs ─────────────────────────────────────────────────────────────
all_pngs = sorted(glob.glob(os.path.join(OUTPUT_DIR, "**", "*.png"), recursive=True) +
                  glob.glob(os.path.join(OUTPUT_DIR, "*.png")))

if not all_pngs:
    print(f"No PNG files found in {OUTPUT_DIR}")
    raise SystemExit

print(f"Found {len(all_pngs)} figures — opening viewer...")

# ── Group by furnace ──────────────────────────────────────────────────────────
from collections import defaultdict

FURNACE_ORDER = ["1HA", "1HB", "1HC", "1HD", "1HE", "1HF", "1HG", "FLEET", "OTHER"]

def get_group(path):
    name = os.path.basename(path)
    for f in ["1HA", "1HB", "1HC", "1HD", "1HE", "1HF", "1HG"]:
        if f in name:
            return f
    if "fleet" in name.lower() or "run_length" in name.lower():
        return "FLEET"
    return "OTHER"

grouped = defaultdict(list)
for p in all_pngs:
    grouped[get_group(p)].append(p)

# ── Render: one figure window per furnace group ───────────────────────────────
COLS = 3

for group in FURNACE_ORDER:
    if group not in grouped:
        continue
    items = grouped[group]
    n     = len(items)
    rows  = math.ceil(n / COLS)
    label = f"Furnace {group}" if group not in ("FLEET", "OTHER") else group

    fig = plt.figure(figsize=(COLS * 7, rows * 6.5))
    fig.suptitle(label, fontsize=20, fontweight="bold", y=1.0)

    for i, img_path in enumerate(items):
        filename   = os.path.basename(img_path)
        title, desc = get_description(filename)

        ax = fig.add_subplot(rows, COLS, i + 1)
        img = mpimg.imread(img_path)
        ax.imshow(img)
        ax.axis("off")

        # Title above image
        ax.set_title(title, fontsize=10, fontweight="bold", pad=6, color="#16213e")

        # Description below image
        ax.text(
            0.5, -0.04, desc,
            transform=ax.transAxes,
            fontsize=7.5, color="#444444",
            ha="center", va="top",
            wrap=True,
            bbox=dict(boxstyle="round,pad=0.4", fc="#f0f4f8", ec="none", alpha=0.8),
        )

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()
