# Standalone 4D Cache-Transition Benchmark Suite

This standalone benchmark suite evaluates **Deterministic Grid vs. Randomized Grid** across increasing scales ($N = 1\text{k} \to 5\text{M}$) to empirically measure:
1. **The L3 Cache Spillover / Cache Thrashing Cliff**
2. **Speedup transitions ($T_{\text{det}} / T_{\text{rand}}$)**
3. **Execution time and hash grid rebuild counts**

---

## 1. Benchmark Executables

The suite contains two specialized tools:
* **`benchmark_opensky_cache` (Real-World Trajectories):** Reads genuine OpenSky 4D flight telemetry (`opensky_5M_4d.bin` or `opensky_3days_100M_4d.bin`). Because points follow continuous physical corridors, **Deterministic preserves L1/L2 cache locality while Randomized shatters it**, producing the **L3 Cache Cliff**!
* **`benchmark_4d_cache` (Synthetic Uniform Normal):** Generates independent random points in $[0, 1000]^4$ (used as a control baseline to confirm that pre-randomized data shows flat $1.0\times$ scaling).

---

## 2. Quick Compilation

```bash
cd cache_benchmark
make
```

Or compile individually:
```bash
g++ -std=c++2a -O3 -mavx2 -march=native -pthread benchmark_opensky_cache.cpp -o benchmark_opensky_cache
g++ -std=c++2a -O3 -mavx2 -march=native -pthread benchmark_4d_cache.cpp -o benchmark_4d_cache
```

---

## 3. Running the OpenSky Real-World Cache Benchmark

The binary file `opensky_5M_4d.bin` (95 MB, 5,000,000 continuous flight points) is included directly in the directory.

### Default Run (10 iterations across all 11 scales from 1k to 5M):
```bash
./benchmark_opensky_cache
```

### Fast Run (3 iterations):
```bash
./benchmark_opensky_cache --iterations 3 --output cache_results_fast.csv
```

### Custom Scale Run:
```bash
./benchmark_opensky_cache --sizes 500000,1000000,1500000,2000000,3000000,5000000 --iterations 5
```

---

## 4. Transferring to Lab Server (`csetuf09`)

The complete packaged tarball is ready at `/media/vithurshan/vithu/rand/cache_bench_opensky.tar.gz` (72 MB, includes source code, Makefile, and the 5M OpenSky binary dataset).

```bash
# On your local machine, copy the tarball to your server:
scp /media/vithurshan/vithu/rand/cache_bench_opensky.tar.gz cse_g4@csetuf09:~/OpenGP/

# On the server:
ssh cse_g4@csetuf09
cd ~/OpenGP
tar -xzvf cache_bench_opensky.tar.gz
cd cache_benchmark
make
./benchmark_opensky_cache
```

---

## 5. Visualizing the Curves
Once the benchmark produces its CSV:
```bash
python3 ../analyzer/run_analyzer.py cache_benchmark_opensky_results.csv
```
This automatically produces speedup plots, timing curves, and rebuild distribution graphs in `analyzer/`.
