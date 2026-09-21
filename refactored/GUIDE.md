# Step-by-Step Guide: Reproducing N-Dimensional Closest Pair Experiments

This guide provides complete instructions to set up the environment, compile the C++20 engine, run synthetic and real-world experiments, and generate publication-grade statistical analysis and plots.

---

## 1. System Requirements & Dependencies

### Hardware Requirements
- **CPU**: x86_64 CPU (AVX2 support recommended for `-march=native`).
- **RAM**: Minimum 8 GB (16 GB+ recommended for $N \ge 1,000,000$ points and $D \ge 8$).
- **OS**: Linux (Ubuntu 20.04+, Debian 11+, Fedora 34+, Arch Linux) or macOS (11+).

### Software Dependencies
Install the required build tools and libraries:

**On Ubuntu / Debian:**
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake g++ libtbb-dev python3 python3-pip
pip3 install numpy pandas matplotlib scipy seaborn
```

**On Fedora / RHEL:**
```bash
sudo dnf install -y gcc-c++ cmake tbb-devel python3 python3-pip
pip3 install numpy pandas matplotlib scipy seaborn
```

---

## 2. Directory Layout & Dataset Setup

The refactored framework uses a modular structure:

```
refactored/
├── core/                               # Generic C++20 Algorithmic Engine
│   ├── point.h                         # Point<Dim, Payload> abstraction (zero overhead)
│   ├── hash_grid.h                     # Hash grid indexing, ArrayHasher, 3^D stencil offsets
│   ├── closest_pair.h                  # Core Rabin grid engine (Deterministic & Randomized)
│   ├── space.h                         # Point generators (Uniform, Shuffled, Adversarial) & Binary IO
│   └── metrics_logger.h                # 17-column standardized benchmark result logger
├── adapters/
│   └── opensky/                        # OpenSky WGS-84 to ECEF + α·Δt metric converter & loader
├── experiments/                        # Benchmark Drivers
│   ├── synthetic/                      # benchmark_synthetic.cpp (D=2..9, Uniform & Adversarial)
│   ├── opensky/                        # benchmark_opensky.cpp (4D real-world ADS-B telemetry)
│   ├── rebuild_work/                   # benchmark_rebuild_work.cpp (D=2..11, Fixed vs Variable deconstruction)
│   └── cache/                          # benchmark_cache.cpp (Cache locality & memory layout)
├── analyzer/                           # Statistical Analyzers & Plotting Scripts
│   ├── analyze_rebuild_work_hypothesis.py # Invariance hypothesis & 2/3^D ratio validator
│   └── run_analyzer.py                 # Multi-scale scaling and speedup analyzer
└── storage/
    ├── datasets/
    │   ├── opensky/                    # Preprocessed 4D OpenSky binary datasets (*.bin)
    │   └── synthetic/                  # Pre-generated / cached synthetic binary datasets (*.bin)
    └── results/                        # Output CSV benchmark logs
```

### Dataset Availability
- **Synthetic Datasets**: If not already present, `Space<Dim>::get_or_create()` will **automatically generate** uniform and adversarial spaces on-the-fly and cache them to disk.
- **Real-World OpenSky Datasets**: Place the 5 hourly preprocessed `.bin` files (`states_2019-05-27-00_4d.bin` through `04_4d.bin`) into `refactored/storage/datasets/opensky/`. The loader automatically detects fallback search locations.

---

## 3. Compilation

Build the release binaries using CMake:

```bash
cd refactored
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

This will produce four optimized executables in `refactored/build/`:
1. `bin_synthetic`: Baseline synthetic multi-scale benchmarks ($D=2 \dots 9$, Uniform, Sorted, Ladder of Pairs).
2. `bin_opensky`: Real-world 4D flight collision detection benchmarks.
3. `bin_rebuild_work`: Algorithmic cost deconstruction, $W$ vs $R$ invariance, and dimensional scaling ($D=2 \dots 11$).
4. `bin_cache`: Cache hierarchy and memory access profiling.

---

## 4. Running Experiments

All commands below assume you are inside the `refactored/build/` directory (or passing relative paths from `refactored/`).

### Experiment A: Synthetic Benchmark Suite
Runs standard uniform distributions, spatial sorting, and adversarial stress tests.

```bash
# Quick sanity check across 2D-9D (2,000 points per dimension)
./bin_synthetic --quick

# Full multi-scale benchmark (10,000 to 100,000 points, 5 iterations each)
./bin_synthetic --iterations 5

# Custom point count and iteration count
./bin_synthetic --points 50000 --iterations 10
```
- **Adversarial Test ("Ladder of Pairs")**: Automatically runs within the synthetic suite to verify that deterministic ordering degrades to $\Omega(N^2)$ while randomized ordering retains $O(N)$ execution time ($>280\times$ speedup).
- Output: Appends to `storage/results/synthetic/master_synthetic.csv`.

---

### Experiment B: Real-World OpenSky Telemetry Benchmark
Runs 4D spatiotemporal collision detection on commercial aircraft trajectories ($x, y, z, \alpha \cdot \Delta t$) with Strategy 2 flight trajectory pruning.

```bash
# Run with default settings (5 iterations per hourly dataset)
./bin_opensky --iterations 5

# Run with custom minimum separation filter (in kilometers)
./bin_opensky --iterations 5 --min-sep 0.05
```
- Demonstrates runtime parity between deterministic and randomized orders on real-world benign flight coordinates.
- Output: Appends to `storage/results/opensky/master_opensky.csv`.

---

### Experiment C: Rebuild Work Invariance & Dimensional Phase Transition Engine
Deconstructs execution time into **Fixed Cost** (Neighbor Probing $T_{\text{probe}}$) and **Variable Cost** (Grid Rebuilding $T_{\text{rebuild}}$).

#### 1. Dimensional Scaling Suite ($D = 2 \dots 11$)
Tests the exponential $3^D$ explosion and verifies the $\frac{2}{3^D}$ Ratio Law:
```bash
./bin_rebuild_work --suite dim --min-dim 2 --max-dim 11 --dim-n 100000 --iterations 10 --tag local
```

#### 2. Scale Suite ($N = 10\text{k} \dots 1\text{M}$ in 4D)
Tests point count scaling and working set size against CPU cache boundaries:
```bash
./bin_rebuild_work --suite scale --iterations 10 --tag local
```

#### 3. Real-World Suite (OpenSky 4D Telemetry)
Instruments the 5 real-world datasets with microsecond probe and rebuild timers:
```bash
./bin_rebuild_work --suite real --iterations 10 --tag local
```

#### 4. Complete Unified Run
Runs all three suites sequentially with 30 iterations:
```bash
./bin_rebuild_work --suite all --iterations 30 --tag local
```
- Output: Saved to `storage/results/rebuild_work/rebuild_work_local_<suite>_<timestamp>.csv` and consolidated in `storage/results/rebuild_work/rebuild_work_local_master.csv`.

---

### Experiment D: Cache Hierarchy Benchmark
Measures memory access patterns and hash table density:
```bash
./bin_cache 100000 5
```

---

## 5. Running the Statistical Analyzers

After generating benchmark CSVs, run the Python analyzers to reproduce tables, correlation statistics, and high-resolution figures.

### 1. Invariance & Hypothesis Analyzer
Evaluates the core hypothesis: **Cumulative Rebuild Work ($W = \sum i_k$) is the true causal driver of runtime variance, while Rebuild Count ($R$) is statistically uncoupled.**

```bash
cd /media/vithurshan/vithu/rand/refactored
python3 analyzer/analyze_rebuild_work_hypothesis.py \
    storage/results/rebuild_work/rebuild_work_local_master.csv \
    --output-dir storage/results/rebuild_work/analysis
```
Generated artifacts in `storage/results/rebuild_work/analysis/`:
- `dim_transition_analysis.csv`: Empirical probe vs rebuild time percentage across $D=2 \dots 11$.
- `correlation_analysis.csv`: Pearson $r(W, T)$ vs $r(R, T)$ confirming metric superiority.
- `hypothesis_testing_report.txt`: Automated mathematical validation report.
- Plots:
  - `fig_probe_vs_rebuild_scaling.png`: Visualizing the exponential $3^D$ dominance.
  - `fig_correlation_W_vs_R.png`: Scatter plots proving $R^2 > 95\%$ for $W$ vs $R^2 \approx 0\%$ for $R$.

### 2. Universal Multi-Scale Analyzer
Generates empirical scaling exponents, speedup distributions, and heatmaps:
```bash
python3 analyzer/run_analyzer.py \
    storage/results/synthetic/master_synthetic.csv \
    --output-dir storage/results/synthetic/analysis
```

---

## 6. Algorithmic Rigor & Zero Bias Guarantee

To eliminate experimental bias and guarantee fair evaluation:
1. **Identical Grid Hashing Logic**: Both deterministic and randomized modes call the exact same template function `find_closest_pair_grid()` in `core/closest_pair.h`. There is zero algorithmic divergence, differing solely by whether `std::shuffle` is executed prior to the point stream.
2. **Shuffle Timing Isolation**: The high-resolution timer for randomized execution strictly brackets the grid solver loop. The time taken to copy and shuffle vectors (`std::shuffle`) is measured separately and recorded as `shuffle_time_ms`, ensuring randomized execution is not artificially penalized in algorithmic comparisons.
3. **Identical Stencil Footprint**: Both methods traverse the exact same static array of $3^D$ neighbor cell offsets generated via `compute_neighbor_offsets<Dim>()`.
4. **Deterministic Seed Control**: Point space generation uses fixed 64-bit Mersenne Twister seeds (`seed = 42`) ensuring bit-level reproducibility of synthetic datasets across machines.
