# Legacy Codebase & Historical Experiments

This directory archives the exploratory code, legacy experiments, initial prototype scripts, and raw logs created during earlier phases of the project:

- **`legacy/closest_pair.h` / `legacy/space.h` / `legacy/experiment.cpp`**: Early monolithic C++ prototype implementations.
- **`legacy/opensky_experiment/` & `legacy/opensky_100m/`**: Initial OpenSky ingestion and flight data scripts before unified modularization.
- **`legacy/cache_benchmark/`**: Early cache profiling scripts.
- **`legacy/analyzer/`**: Historical Python analysis scripts and summary CSV logs.
- **`legacy/results/`**: Initial raw benchmark logs.

---

### Modern Architecture
All active, production-grade C++20 code has been unified and promoted to the repository root:
- **`core/`**: Header-only, zero-overhead $N$-dimensional Rabin hash-grid engine.
- **`adapters/`**: Zero-copy domain adapters (e.g., OpenSky WGS-84 to ECEF + $\alpha\Delta t$).
- **`experiments/`**: Modular benchmark suites (`synthetic`, `opensky`, `rebuild_work`, `cache`).
- **`analyzer/`**: Academic-grade statistical analysis and visualization scripts.
- **`storage/`**: Standardized dataset and benchmark result storage.

Please refer to [`README.md`](../README.md) and [`GUIDE.md`](../GUIDE.md) in the repository root for build and execution instructions.
