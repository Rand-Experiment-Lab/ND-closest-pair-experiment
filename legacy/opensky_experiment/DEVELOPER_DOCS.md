# OpenSky 4D Closest Pair: Developer Architecture & Technical Reference

**System:** Real-World Spatio-Temporal Collision Detection via Multi-Dimensional Grid Hashing  
**Authors/Contributors:** Vithurshan (Research Lead), Pepper (Research & Algorithmic Assistant)  
**Target Space:** $\mathbb{R}^4$ Earth-Centered Earth-Fixed (ECEF) Spatial Coordinates + Scaled Temporal Dimension $(x, y, z, w)$  
**Version:** 2.0 (Full 24-Hour Batch Support & Strategy 2 Intra-Flight Exclusion)  
**Location:** `opensky_experiment/`

---

## 1. System Overview & Problem Formulation

In real-world air traffic surveillance, Automatic Dependent Surveillance–Broadcast (ADS-B) stations log periodic state vectors of airborne and taxiing aircraft.

### Mathematical Formulation
Each radar update is modeled as a 4-dimensional point:
$$P = \begin{bmatrix} x \\ y \\ z \\ w \end{bmatrix} \in \mathbb{R}^4, \quad \text{tagged with an aircraft identifier } \text{flight\_id} \in \mathbb{N}$$

Where:
- $x, y, z$: Orthogonal Cartesian spatial coordinates in meters ($\text{m}$), converted from GPS WGS-84 ellipsoid $(\text{latitude}, \text{longitude}, \text{altitude})$ to Earth-Centered Earth-Fixed (ECEF).
- $w$: Scaled metric time coordinate in meters:
  $$w = \alpha \cdot (t - t_{\text{min}})$$
  - $t$: Absolute Unix epoch timestamp in seconds ($\text{s}$).
  - $t_{\text{min}}$: Global temporal origin of the dataset (e.g. 00:00:00 UTC).
  - $\alpha$: Characteristic velocity parameter in meters/second ($\text{m/s}$), computed as the dataset's average flight velocity ($\approx 190 - 250\text{ m/s}$).

### Closest Pair Objective
Find the pair of distinct aircraft $(P_i, P_j)$ that minimizes the 4-dimensional Euclidean distance:
$$\delta^* = \min_{\substack{i \neq j \\ \text{flight\_id}(i) \neq \text{flight\_id}(j)}} \sqrt{(x_i - x_j)^2 + (y_i - y_j)^2 + (z_i - z_j)^2 + \alpha^2 (t_i - t_j)^2}$$

> **Constraint Enforcement (Strategy 2):**  
> If $\text{flight\_id}(i) == \text{flight\_id}(j)$, the pair represents consecutive updates of the **same physical plane**. It is strictly skipped in neighbor search to prevent intra-flight trivial closest pairs.

---

## 2. Directory Layout

```
opensky_experiment/
├── DEVELOPER_DOCS.md               # This technical reference document
├── flight_space.h                  # C++ data structures: FlightPoint<Dim>, binary IO loader
├── flight_closest_pair.h           # Core algorithm: 4D hash grid with Strategy 2 intra-flight pruning
├── experiment_opensky.cpp          # Benchmark runner (Full day or single file, 4 order scenarios)
├── experiment_opensky_hourly.cpp   # Hourly benchmark runner (24 hours x 4 tests, per-hour summaries)
├── data/                           # Data storage
│   ├── 2019-05-27/                 # Raw 24-hour .csv.gz archives
│   ├── 2019-05-27_hourly/          # 24 Cleaned CSVs + 24 BINs + index JSON
│   └── opensky_2019-05-27_full_day_4d.bin # Consolidated 24-hour binary dataset
├── results/                        # Versioned experiment output CSV files
└── scripts/
    ├── fetch_dates.py              # Query OpenSky S3 repository for available dates
    ├── downloader.py               # Multi-threaded download and extraction
    ├── preprocess_opensky.py       # Single-file preprocessor (CSV -> cleaned CSV + .bin)
    ├── preprocess_day_opensky.py   # Streaming 24-hour batch preprocessor (folder of .csv.gz -> single .bin)
    ├── preprocess_hourly_opensky.py# Multi-core hourly preprocessor (folder -> 24 CSVs + 24 BINs)
    └── run_automated_pipeline.py   # Build-folder centric master automated pipeline script
```

---

## 3. Data Pipeline & Preprocessing Architecture

### 3.1 Preprocessing Workflow (`preprocess_opensky.py` & `preprocess_day_opensky.py`)

```
Raw OpenSky CSV/GZ
  ├── Missing coordinate filter (drops rows without lat/lon/alt/time/icao24)
  ├── Kinematic validation (-90 <= lat <= 90, -180 <= lon <= 180, -100m <= alt <= 25,000m)
  ├── Characteristic velocity estimation: alpha = E[velocity]
  ├── Global temporal anchoring: t_min = min(time)
  ├── WGS-84 Geodetic to ECEF conversion: (lat, lon, alt) -> (x, y, z) in meters
  ├── Time scaling: w = alpha * (t - t_min) in meters
  ├── icao24 string -> uint32 flight_id dictionary mapping
  └── Binary serialization (.bin) + metadata sidecar (.json)
```

### 3.2 WGS-84 Geodetic to ECEF Transformation
Air traffic coordinates are broadcast as latitude $\phi$, longitude $\lambda$, and altitude $h$ above the WGS-84 reference ellipsoid:
- Semi-major axis: $a = 6{,}378{,}137.0\text{ m}$
- First eccentricity squared: $e^2 = 0.00669437999014$

The prime vertical radius of curvature $N(\phi)$ is:
$$N(\phi) = \frac{a}{\sqrt{1 - e^2 \sin^2(\phi)}}$$

Cartesian ECEF coordinates are computed as:
$$x = (N(\phi) + h) \cos(\phi) \cos(\lambda)$$
$$y = (N(\phi) + h) \cos(\phi) \sin(\lambda)$$
$$z = \left(N(\phi)(1 - e^2) + h\right) \sin(\phi)$$

### 3.3 High-Speed Binary Format (`OPS2` Specification)
To eliminate CSV string parsing overhead, processed points are serialized in a packed, memory-mappable binary layout:

| Offset (Bytes) | Field Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `magic` | `char[4]` | Format identifier: `'O'`, `'P'`, `'S'`, `'2'` |
| `0x04 - 0x07` | `dim` | `uint32` | Dimensionality of points (strictly `4`) |
| `0x08 - 0x0F` | `count` | `uint64` | Total number of points in file |
| `0x10 - 0x13` | `alpha` | `float32` | Velocity scale factor in m/s |
| `0x14 - 0x1B` | `t_min` | `float64` | Original Unix epoch timestamp (double precision) |
| `0x1C - End` | `records` | `Record[]` | Contiguous array of point records (below) |

**Individual Record Layout (20 Bytes per point):**
```
struct BinaryRecord {
    uint32_t flight_id;    // 4 bytes: Unique integer mapped from icao24
    float coordinates[4];  // 16 bytes: [x, y, z, w] in meters
};
```
*Reading 20 million points requires only $400\text{ MB}$ of RAM and loads in $\approx 0.15\text{ seconds}$ via raw binary streaming.*

---

## 4. C++ Data Structures & Algorithm Design

### 4.1 Data Container (`flight_space.h`)

```cpp
template <std::size_t Dim>
struct FlightPoint {
    std::array<float, Dim> coordinates{}; // [x_m, y_m, z_m, w_time_m]
    std::uint32_t flight_id{0};           // Unique integer aircraft ID

    [[nodiscard]] float distance_to(const FlightPoint<Dim> &other) const noexcept {
        float sum = 0.0f;
        for (std::size_t i = 0; i < Dim; ++i) {
            float diff = coordinates[i] - other.coordinates[i];
            sum += diff * diff;
        }
        return std::sqrt(sum);
    }
};
```

### 4.2 Incremental $\delta$-Grid with Strategy 2 Exclusion (`flight_closest_pair.h`)

The grid coordinates of a 4D point under cell width $\delta$ are computed as:
$$\text{cell}[d] = \left\lfloor \frac{\text{coord}[d]}{\delta} \right\rfloor \quad \forall d \in \{0, 1, 2, 3\}$$

```
┌──────────────────────────────────────────────────────────┐
│              Incremental 4D Grid Step i                  │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
           Compute 4D grid cell: cell_i = floor(p_i / δ)
                            │
                            ▼
     Query all 3^4 = 81 neighboring grid cells in hash map
                            │
         ┌──────────────────┴──────────────────┐
         │ For each point p in neighbor cells: │
         └──────────────────┬──────────────────┘
                            │
                Is p.flight_id == p_i.flight_id?
                    ├── YES ──► SKIP (Same Aircraft!)
                    └── NO  ──► Compute 4D distance: d = dist(p_i, p)
                                    │
                               Is d < δ?
                                    ├── NO  ──► Continue
                                    └── YES ──► Set δ = d
                                                Rebuild entire grid for 0..i
```

#### Why $3^4 = 81$ Neighbor Lookups?
In 4D, each cell is a 4-dimensional hypercube of edge length $\delta$. Any point that is closer than $\delta$ to $p_i$ must lie in either the same cell or an immediately adjacent hypercube cell along any of the 4 axes:
$$\text{Number of neighbor hypercubes} = 3^{\text{Dim}} = 3^4 = \mathbf{81\text{ cells}}$$

#### Strategy 2 Implementation
```cpp
for (const auto &point : it->second) {
    if (pi.flight_id == point.flight_id) {
        continue; // Strictly eliminates intra-flight comparisons
    }
    float dist = pi.distance_to(point);
    if (dist < min_dist) {
        min_dist = dist;
        *out_closest_partner = point;
    }
}
```

---

## 5. Experiment Harness & Methodology (`experiment_opensky.cpp`)

The benchmark runner validates two foundational algorithmic hypotheses:
1. **Hypothesis 1 (Deterministic vs. Randomized):**  
   Does shuffling real-world radar streams reduce the number of grid rebuilds and total runtime compared to processing in raw chronological sequence?
2. **Hypothesis 2 (Input Ordering Sensitivity):**  
   How does pre-sorting points along the temporal axis (4th dimension: $w$) affect the frequency of grid rebuilds in deterministic mode?

### Benchmarking Scenarios Evaluated (10 Iterations Each)

| Scenario Name | Input Order | Algorithm | Expected Rebuild Behavior |
| :--- | :--- | :--- | :--- |
| **Scenario 1A** | Original Radar Order | Deterministic Grid | Rebuilds determined by real-world arrival order of radar packets. |
| **Scenario 1B** | Original Radar Order | Randomized Grid | Points shuffled using `std::mt19937` with `std::seed_seq`. Expected $O(\log N)$ rebuilds. |
| **Scenario 2A** | Sorted along 4th Axis ($w$) | Deterministic Grid | Chronologically monotonic insertion. Stresses sequential time buckets. |
| **Scenario 2B** | Sorted along 4th Axis ($w$) | Randomized Grid | Shuffled order breaks temporal monotonicity. |

### Memory & Benchmark Integrity Measures
- **Zero-Allocation Timing Window:** To ensure unbiased timing, the randomized algorithm shuffles points into a **pre-allocated buffer** before starting the high-resolution timer.
- **Span Interfaces (`std::span`):** Functions accept zero-copy pointer views, preventing vector copy and destruction noise during timing.
- **Reconstructed UTC Timestamps:** When the closest encounter is identified, the program uses $t_{\text{min}}$ and $\alpha$ to reconstruct the exact real-world UTC time down to the second:
  $$t_{\text{actual}} = t_{\text{min}} + \frac{w}{\alpha}$$

---

## 6. Execution Reference Guide (All Commands Executed from `build/`)

> [!IMPORTANT]
> The primary execution working directory is always `build/`. All binaries and scripts resolve their relative paths with `build/` as the reference point:
> - **Input Data & Intermediates:** `../opensky_experiment/data/`
> - **Results Output:** `../opensky_experiment/results/`

### 6.1 Compilation (from `build/` or project root)
```bash
# Configure and compile both targets:
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build --target experiment_opensky experiment_opensky_hourly -j$(nproc)
```

### 6.2 Preprocessing Hourly Files (24 CSVs & 24 BINs)
Run from `build/`:
```bash
cd build

python3 ../opensky_experiment/scripts/preprocess_hourly_opensky.py \
  ../opensky_experiment/data/2019-05-27 \
  ../opensky_experiment/data/2019-05-27_hourly
```

### 6.3 Running the Hourly Benchmark (24 Hours x 4 Tests)
Run from `build/`:
```bash
cd build

# Syntax: ./experiment_opensky_hourly [hourly_data_dir] [iterations=10] [min_sep=0.05]
./experiment_opensky_hourly ../opensky_experiment/data/2019-05-27_hourly 10 0.05
```
*Results automatically saved to: `../opensky_experiment/results/opensky_hourly_results_<timestamp>.csv`*

### 6.4 Preprocessing Full-Day Consolidated Binary
Run from `build/`:
```bash
cd build

python3 ../opensky_experiment/scripts/preprocess_day_opensky.py \
  ../opensky_experiment/data/2019-05-27 \
  ../opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin
```

### 6.5 Running Full-Day Consolidated Experiment
Run from `build/`:
```bash
cd build

# Syntax: ./experiment_opensky [binary_path] [iterations=10] [min_sep=0.05]
./experiment_opensky ../opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin 10 0.05
```
*Results automatically saved to: `../opensky_experiment/results/opensky_results_<timestamp>.csv`*

### 6.6 All-in-One Automated Pipeline (Download, Preprocess & Benchmark)
Run from `build/`:
```bash
cd build

# Run for a specific date:
python3 ../opensky_experiment/scripts/run_automated_pipeline.py --date 2019-05-27

# Or run batch across all 25 dates and all 24 hours:
python3 ../opensky_experiment/scripts/run_automated_pipeline.py --all-dates --min-hours 24
```

---

## 7. Verification & Empirical Results (Baseline Validation)

On the initial 1.53 million radar records (`states_2019-01-28-00.csv`), the system produced the following baseline:
- **Total Points Processed:** $1{,}533{,}465$
- **Velocity Scaling ($\alpha$):** $189.9\text{ m/s}$
- **Global Minimum 4D Distance:** $4.78\text{ meters}$
- **Identified Encounter:** Aircraft #1607 and Aircraft #1092 at `2019-01-28 00:36:09 UTC` (simultaneous tarmac/taxiway proximity).
- **Observed Rebuilds:** $20 - 26$ rebuilds across both deterministic and randomized runs, matching the theoretical Harmonic bound $E[R] \approx 2 \ln(1.5 \times 10^6) \approx 28.4$.
