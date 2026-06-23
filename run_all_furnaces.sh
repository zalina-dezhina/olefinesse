#!/usr/bin/env bash
# ============================================================================
# run_all_furnaces.sh
#
# Run notebook_00b_clean_extraction.ipynb on all 7 furnaces in parallel.
# Uses papermill to inject FURNACE as a parameter, so each furnace gets its
# own executed notebook and output saved to output/{FURNACE}/00b_clean/.
#
# Prerequisites (run once):
#   pip install papermill --break-system-packages
#
# Usage:
#   bash run_all_furnaces.sh               # all 7 furnaces
#   bash run_all_furnaces.sh 1HA 1HB       # specific furnaces only
#
# Output (per furnace):
#   output/logs/notebook_00b_1HA.ipynb        (executed notebook with cell outputs)
#   output/logs/1HA.log                        (papermill run log)
#   output/run_analysis_windows.csv            (run metadata only — ~15 rows, no time series)
#   output/1HA_00b_clean_extraction.png        (verification plot)
#
# Data that stays INSIDE Databricks (never written to local disk):
#   Delta table: <DELTA_CATALOG>.1ha_features  (full feature matrix)
#   Delta table: <DELTA_CATALOG>.1ha_clean     (clean cracking windows only)
#
# DELTA_CATALOG is set inside the notebook (cell 2, parameter DELTA_CATALOG).
# Default: indorama_corporate_olefins_paas_azure_weu_dev_bronze.research
# ============================================================================

set -euo pipefail

NOTEBOOK="notebooks/00b_clean/notebook_00b_clean_extraction.ipynb"
OUTPUT_DIR="output"
LOG_DIR="output/logs"
START="2025-02-05"
END="2026-03-20"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

# Which furnaces to run
if [ $# -gt 0 ]; then
    FURNACES=("$@")
else
    FURNACES=(1HA 1HB 1HC 1HD 1HE 1HF 1HG)
fi

echo "═══════════════════════════════════════════════════════════════════════"
echo " Furnaces : ${FURNACES[*]}"
echo " Notebook : $NOTEBOOK"
echo " Window   : $START → $END"
echo " Output   : $OUTPUT_DIR/"
echo "═══════════════════════════════════════════════════════════════════════"

run_furnace() {
    local furnace=$1
    local out_nb="${LOG_DIR}/notebook_00b_${furnace}.ipynb"
    local log="${LOG_DIR}/${furnace}.log"

    echo "[$(date +%H:%M:%S)] ▶ Starting $furnace ..."
    papermill "$NOTEBOOK" "$out_nb" \
        -p FURNACE   "$furnace"  \
        -p START     "$START"    \
        -p END       "$END"      \
        --log-output             \
        > "$log" 2>&1 \
    && echo "[$(date +%H:%M:%S)] ✓ $furnace done  → $out_nb" \
    || echo "[$(date +%H:%M:%S)] ✗ $furnace FAILED — see $log"
}

export -f run_furnace
export OUTPUT_DIR LOG_DIR START END NOTEBOOK

# Run all furnaces in parallel (one background job per furnace)
pids=()
for f in "${FURNACES[@]}"; do
    run_furnace "$f" &
    pids+=($!)
done

# Wait for all jobs and collect exit codes
failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || ((failed++))
done

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
if [ $failed -eq 0 ]; then
    echo " ✓ All furnaces completed successfully."
else
    echo " ✗ $failed furnace(s) failed. Check output/logs/*.log for details."
fi
echo " PNG plots in: $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR"/*.png 2>/dev/null | tail -20 || true
echo " (Processed data is in Databricks Delta tables — not written locally)"
echo "═══════════════════════════════════════════════════════════════════════"
