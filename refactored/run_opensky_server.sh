#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ITERATIONS=${1:-30}
DATASET_DIR=${2:-"storage/datasets/opensky"}

echo "======================================================="
echo "  OpenSky 4D Streaming Closest-Pair Server Benchmark"
echo "  Iterations per dataset: $ITERATIONS"
echo "  Dataset Directory     : $DATASET_DIR"
echo "======================================================="

# 1. Build release binaries
echo "[1/3] Building C++ benchmark binary..."
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target bin_opensky -j$(nproc 2>/dev/null || echo 4)

# 2. Run benchmark on datasets
echo "[2/3] Executing OpenSky benchmark..."
./build/bin_opensky --input "$DATASET_DIR" --iterations "$ITERATIONS"

# 3. Find latest generated CSV and run visualizer
LATEST_CSV=$(ls -t storage/results/opensky/opensky_benchmark_*.csv 2>/dev/null | head -n 1)
if [ -n "$LATEST_CSV" ]; then
    echo "[3/3] Generating analysis figures and tables from: $LATEST_CSV"
    python3 analyzer/run_analyzer.py "$LATEST_CSV" || echo "Note: Install matplotlib, seaborn, pandas to render PNG plots."
fi

echo "======================================================="
echo "  Benchmark finished successfully!"
echo "  Results stored in: storage/results/opensky/"
echo "======================================================="
