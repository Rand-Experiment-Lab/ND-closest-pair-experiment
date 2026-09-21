# OpenSky 100-Million 4D Closest Pair Benchmark Suite

An independent, high-performance C++20 and Python research pipeline designed to benchmark incremental hash-grid closest pair algorithms across **100 Million real-world aircraft telemetry points** (3 full consecutive days of OpenSky ADS-B states: $24 \times 3 = 72$ hourly files).

---

## 1. Mathematical Architecture & 3-Day Time Reference

### Spatial & Temporal Dimensions (4D Cartesian)
Each aircraft observation $(t, \text{lat}, \text{lon}, \text{alt}, \text{icao24})$ is mapped into 4D ECEF Cartesian coordinates:
$$\begin{aligned}
x &= (R + \text{alt}) \cos(\text{lat}) \cos(\text{lon}) \\
y &= (R + \text{alt}) \cos(\text{lat}) \sin(\text{lon}) \\
z &= (R + \text{alt}) \sin(\text{lat}) \\
w &= \alpha \cdot (t - t_{\text{ref}})
\end{aligned}$$
Where $R = 6,371,000\text{ m}$ (mean Earth radius) and $\alpha = 250.0\text{ m/s}$ (typical commercial aircraft cruise velocity).

### Why $t_{\text{ref}}$ is Essential Across 3 Days
1. **The Issue with Raw Epochs:** Raw Unix timestamp is $t \approx 1.558 \times 10^9\text{ s}$. Multiplying by $\alpha = 250.0$ yields $w \approx 3.89 \times 10^{11}\text{ m}$. In IEEE 754 32-bit `float`, the Unit in the Last Place (ULP) at this scale is $\approx 32,768\text{ meters}$, destroying sub-meter accuracy!
2. **The Exact Solution:** We set $t_{\text{ref}}$ to **Midnight UTC of Day 1** ($1558915200.0\text{ s}$ stored as double-precision 64-bit float).
3. **Continuous 3-Day Window:** Over 72 hours, $\Delta t = (t - t_{\text{ref}}) \in [0.0, 259200.0\text{ s}]$. Thus $w \le 6.48 \times 10^7\text{ m}$, fully preserving sub-meter precision in 32-bit floats.
4. **UTC Reconstruction:** Any 4D point can be mapped back to exact UTC epoch: $t_{\text{UTC}} = t_{\text{ref}} + \frac{w}{\alpha}$.

---

## 2. Server Specifications & Memory Requirements

- **Total 4D Points:** $\sim 100,000,000$ points.
- **Point Vector Memory:** $100\text{M} \times 20\text{ bytes} \approx 2.0\text{ GB}$ ($1.86\text{ GiB}$).
- **Peak Dynamic Grid Memory:** $\approx 12.4\text{ GB}$ ($11.5\text{ GiB}$).
- **Total Peak RSS:** $\mathbf{\approx 14.4\text{ GB}}$ ($\mathbf{13.4\text{ GiB}}$).
- **Target Server:** **31 GB RAM** allows 100% in-memory execution with $>16\text{ GB}$ safety headroom (zero swap, zero OOM risk).

---

## 3. Project Structure

```text
opensky_100m/
├── CMakeLists.txt              # Independent C++20 release build configuration
├── config.json                 # Unified JSON configuration (dates, alpha, thresholds)
├── data_preparator.py          # Automated 3-day download, conversion, and streaming binary packer
├── src/
│   ├── flight_point.h          # 4D point, grid mapping, 81-neighbor offsets, binary loader
│   ├── closest_pair_100m.h     # Deterministic & Randomized Grid algorithms with zero-overhead progress
│   └── main_100m.cpp           # Resilient CLI runner with live CSV flushing and signal handling
├── scripts/
│   └── analyze_100m.py         # Visualizer: execution time, rebuilds, and Gaussian bell-curve fits
└── README.md
```

---

## 4. Quick Start Guide

### Step 1: Build the C++ Benchmark Engine
```bash
cd opensky_100m
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### Step 2: Prepare the 3-Day 100M Dataset
Run the streaming preparator from `opensky_100m/` (or from `build/`):
```bash
python3 data_preparator.py config.json
```
- Automatically handles `.tar` extraction, existing `.csv.gz` files, or downloads from OpenSky.
- Streams points hour-by-hour directly to disk (RAM during conversion remains $< 1.0\text{ GB}$).
- Produces `data/opensky_3days_100M_4d.bin` ($\approx 2.0\text{ GB}$).

### Step 3: Run the 100M Benchmark (Original Order)
Run from `build/` in a persistent terminal (`tmux`, `screen`, or `nohup`):

```bash
# 10 iterations (Deterministic + Randomized)
./benchmark_100m ../config.json
```

Or pass positional parameters:
```bash
./benchmark_100m ../data/opensky_3days_100M_4d.bin 10 0.05 ../results/opensky_100M_results.csv 1
```

#### Run in Background (Safe against SSH disconnects):
```bash
nohup ./benchmark_100m ../config.json > ../results/run_100m.log 2>&1 &
```
Monitor live progress anytime:
```bash
tail -f ../results/run_100m.log
```

---

## 5. Zero-Overhead Live Progress Monitoring

To observe progress over the $\sim 15$-minute execution without impacting algorithm performance:
- The checkpoint check uses CPU branch prediction hints: `__builtin_expect(i >= next_milestone, 0)`.
- Updates only every 5% milestone (20 times total across 100M points).
- **Overhead:** $0.000\%$ (zero cache pollution, zero branch mispredictions).

Example live terminal output:
```text
  -> Iteration 1/10 starting...
  [Progress 5.0%] 5M/100M pts | Min Dist: 18.420 m | Rebuilds: 6 | Elapsed: 44.2s | ETA: 13m 59s
  [Progress 10.0%] 10M/100M pts | Min Dist: 5.120 m | Rebuilds: 11 | Elapsed: 1m 29s | ETA: 13m 21s
  ...
  [Progress 100.0%] 100M/100M pts | Min Dist: 0.250 m | Rebuilds: 29 | Elapsed: 14m 51s | ETA: 0.0s
  -> Iteration 1 done: 891.24 s (891240 ms) | Rebuilds: 29 | Min Dist: 0.250 m
```

---

## 6. Analyze Results & Plot Bell Curves

Generate execution barplots, rebuild statistics, and fitted Gaussian normal distribution curves:
```bash
python3 ../scripts/analyze_100m.py ../results/opensky_100M_results.csv
```

Outputs generated in `results/opensky_100M_results/`:
- `fig1_execution_time.png`: Deterministic vs Randomized execution speed.
- `fig2_rebuild_counts.png`: Average grid rebuilds.
- `fig3_distribution_Original.png`: Empirical histograms + KDE + fitted Gaussian bell curve $N(\mu, \sigma)$ with skewness and kurtosis diagnostics.
- `summary_report.md`: Markdown summary table.
