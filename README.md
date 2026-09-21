# N-Dimensional Closest Pair: Refactored & Modular Architecture v2.0

This directory contains the cleanly refactored, production-ready implementation of the N-Dimensional Closest Pair engine, unifying synthetic multi-dimensional benchmarks and real-world 4D OpenSky flight collision detection under a zero-overhead generic core.

For a comprehensive walkthrough of experiment reproduction and hypothesis validation, see [**GUIDE.md**](file:///media/vithurshan/vithu/rand/refactored/GUIDE.md).

---

## Directory Structure

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
│   ├── rebuild_work/
│   │   └── benchmark_rebuild_work.cpp  # D=2..11 Fixed vs Variable cost deconstruction & invariance engine
│   └── cache/
│       └── benchmark_cache.cpp         # Hardware cache locality and memory layout benchmark
│
├── storage/                            # Centralized Storage & Results
│   ├── results/
│   │   ├── synthetic/                  # Standardized synthetic benchmark CSVs & master log
│   │   ├── opensky/                    # Standardized OpenSky telemetry benchmark CSVs
│   │   ├── rebuild_work/               # Microarchitectural Fixed vs Variable deconstruction CSVs
│   │   └── cache/                      # Cache miss and memory access profiling CSVs
│   └── datasets/                       # Serialized binary datasets (.bin, git-ignored)
│
├── analyzer/                           # Academic-Grade Visualization & Analysis Pipeline
│   ├── analyze_rebuild_work_hypothesis.py # Rebuild Work Invariance & 2/3^D Ratio Law analyzer
│   └── run_analyzer.py                 # Universal ingestor generating heatmaps, exponents & scaling plots
│
├── legacy/                             # Archived exploratory scripts and historical experiments
├── GUIDE.md                            # Comprehensive step-by-step reproduction and setup guide
└── FINAL_RESEARCH_REPORT_RANDOMIZATION.md # Complete research report on randomization & dimensional law
```

---

## Quick Build & Execution

### 1. Build
```bash
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### 2. Run Benchmarks
```bash
# Synthetic Suite (Uniform, Sorted, Adversarial)
./bin_synthetic --iterations 5

# Real-World OpenSky 4D Telemetry Suite
./bin_opensky --iterations 5

# Rebuild Work Invariance & Dimensional Scaling Suite (D=2..11)
./bin_rebuild_work --suite dim --min-dim 2 --max-dim 11 --iterations 10
```

### 3. Run Analysis & Generate Figures
```bash
cd /media/vithurshan/vithu/rand/refactored
python3 analyzer/analyze_rebuild_work_hypothesis.py storage/results/rebuild_work/rebuild_work_local_master.csv --output-dir storage/results/rebuild_work/analysis
```
