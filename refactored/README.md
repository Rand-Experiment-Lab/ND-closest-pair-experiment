# N-Dimensional Closest Pair: Refactored & Modular Architecture v2.0

This directory contains the cleanly refactored, production-ready implementation of the N-Dimensional Closest Pair engine, unifying synthetic multi-dimensional benchmarks and real-world 4D OpenSky flight collision detection under a zero-overhead generic core.

---

## Structure

```
refactored/
├── core/                               # Generic C++20 Header-Only Algorithmic Engine
│   ├── point.h                         # Point<Dim, Payload = EmptyPayload> with [[no_unique_address]] (0 overhead)
│   ├── hash_grid.h                     # GridCell<Dim>, ArrayHasher, 3^D neighbor offsets generator
│   ├── closest_pair.h                  # Deterministic & Randomized Rabin Solvers with PairFilter policy
│   ├── space.h                         # Space<Dim, Payload>, Uniform & Adversarial Ladder generators
│   └── metrics_logger.h                # Standardized 17-column CSV benchmark result logger
│
├── adapters/                           # Zero-Copy Domain Adapters
│   └── opensky/
│       └── opensky_adapter.h           # WGS-84 to ECEF + α·Δt metric coordinate transform & OPS2 loader
│
├── experiments/                        # Benchmark Executables & Drivers
│   ├── synthetic/
│   │   └── benchmark_synthetic.cpp     # 2D to 9D Uniform, Sorted, and Adversarial benchmark suite
│   ├── opensky/
│   │   └── benchmark_opensky.cpp       # 4D OpenSky flight collision detection with Strategy 2 filter
│   └── cache/
│       └── benchmark_cache.cpp         # Hardware cache locality and memory layout benchmark
│
├── storage/                            # Centralized Storage & Results
│   ├── results/
│   │   ├── synthetic/                  # Standardized synthetic benchmark CSVs & master log
│   │   ├── opensky/                    # Standardized OpenSky telemetry benchmark CSVs
│   │   └── cache/                      # Cache miss and memory access profiling CSVs
│   ├── datasets/                       # Serialized binary datasets (.bin, git-ignored)
│   └── archive_legacy/                 # Preserved historical experiment CSVs
│
└── analyzer/                           # Academic-Grade Visualization & Analysis Pipeline
    └── run_analyzer.py                 # Universal ingestor generating heatmaps, exponents & scaling plots
```

---

## Build & Usage

### 1. Build
```bash
cd refactored
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### 2. Run Synthetic Benchmarks
```bash
# Quick sanity check across 2D-9D (2,000 points)
./bin_synthetic --quick

# Full multi-scale benchmark (10k, 50k, 100k points)
./bin_synthetic --iterations 5
```

### 3. Run OpenSky 4D Telemetry Benchmarks
```bash
./bin_opensky --iterations 5 --min-sep 0.05
```

### 4. Run Cache Benchmark
```bash
./bin_cache 100000 5
```

### 5. Run Unified Analyzer
```bash
# Analyze synthetic results
python3 ../analyzer/run_analyzer.py storage/results/synthetic/master_synthetic.csv --output-dir storage/results/synthetic/analysis
```
