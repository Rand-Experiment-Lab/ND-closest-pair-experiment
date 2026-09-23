# Developer Documentation: Modular Architecture (`feature/modular-refactor`)

This document provides an exhaustive, component-by-component technical reference for the refactored N-Dimensional Closest Pair engine located in `refactored/`. It details the design rationale, mathematical models, memory layouts, algorithmic mechanisms, and code implementations across every file in the system.

---

## Table of Contents
1. [Architectural Philosophy & Design Patterns](#1-architectural-philosophy--design-patterns)
2. [Core Layer (`refactored/core/`)](#2-core-layer-refactoredcore)
   - [2.1 `point.h`](#21-corepointh)
   - [2.2 `hash_grid.h`](#22-corehash_gridh)
   - [2.3 `closest_pair.h`](#23-coreclosest_pairh)
   - [2.4 `space.h`](#24-corespaceh)
   - [2.5 `metrics_logger.h`](#25-coremetrics_loggerh)
3. [Adapters Layer (`refactored/adapters/`)](#3-adapters-layer-refactoredadapters)
   - [3.1 `opensky/opensky_adapter.h`](#31-adaptersopenskyopensky_adapterh)
4. [Experiments Layer (`refactored/experiments/`)](#4-experiments-layer-refactoredexperiments)
   - [4.1 `synthetic/benchmark_synthetic.cpp`](#41-experimentssyntheticbenchmark_syntheticcpp)
   - [4.2 `opensky/benchmark_opensky.cpp`](#42-experimentsopenskybenchmark_openskycpp)
   - [4.3 `cache/benchmark_cache.cpp`](#43-experimentscachebenchmark_cachecpp)
5. [Storage Layer & Unified Measurement Schema (`refactored/storage/`)](#5-storage-layer--unified-measurement-schema-refactoredstorage)
6. [Analysis Engine (`refactored/analyzer/`)](#6-analysis-engine-refactoredanalyzer)
   - [6.1 `run_analyzer.py`](#61-analyzerrun_analyzerpy)
7. [Build System (`refactored/CMakeLists.txt`)](#7-build-system-refactoredcmakeliststxt)

---

## 1. Architectural Philosophy & Design Patterns

The legacy implementation suffered from triple/quadruple code duplication: the Rabin spatial hash grid was independently copy-pasted across synthetic benchmarks, OpenSky experiments, cache benchmarks, and 100M stream processors.

The `refactored/` architecture solves this using three C++20 principles:
1. **Zero-Cost Abstractions:** High-level abstractions that compile down to the exact assembly of hand-tuned C.
2. **Policy-Based Design:** Filtering conditions (e.g. ignoring intra-flight pings from the same aircraft) are injected as template functors. When using trivial filters, branches are eliminated at compile time via `if constexpr`.
3. **Empty Base / Member Optimization:** Generic point templates support custom domain payloads (`EmptyPayload` vs `OpenSkyMetadata`) without wasting a single byte of memory for synthetic benchmarks via C++20 `[[no_unique_address]]`.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                 Policy-Based Closest Pair               │
                  │              core::find_closest_pair_grid               │
                  └────────────┬──────────────────────────────┬─────────────┘
                               │                              │
          PairFilter = DefaultPairFilter          PairFilter = Strategy2FlightFilter
          (Compiled as no-op / constexpr)         (Checks flight_id & min separation)
                               │                              │
                               ▼                              ▼
                 ┌───────────────────────────┐  ┌───────────────────────────┐
                 │ Point<Dim, EmptyPayload>  │  │ Point<4, OpenSkyMetadata> │
                 │ • Size: Dim * 4 bytes     │  │ • Size: 32 bytes          │
                 │ • Zero metadata overhead  │  │ • Packed flight_id + UTC  │
                 └───────────────────────────┘  └───────────────────────────┘
```

---

## 2. Core Layer (`refactored/core/`)

### 2.1 `core/point.h`

#### Purpose
Defines the fundamental geometric entity in $D$-dimensional Euclidean space $\mathbb{R}^D$, with optional domain metadata.

#### Code Breakdown & Implementation Details
```cpp
struct EmptyPayload {};

template <std::size_t Dim, typename Payload = EmptyPayload>
struct Point {
  std::array<float, Dim> coords{};
  [[no_unique_address]] Payload payload{};
  ...
};
```

1. **`EmptyPayload`:** A zero-sized struct (`sizeof == 1` in C++ standard, but 0 bytes when marked `[[no_unique_address]]`).
2. **`[[no_unique_address]] Payload payload;`:** In C++20, this attribute instructs the compiler that if `Payload` is an empty class, it does not require a distinct memory address. This guarantees:
   - `sizeof(Point<2, EmptyPayload>) == 8` bytes ($2 \times \text{float}$).
   - `sizeof(Point<3, EmptyPayload>) == 12` bytes ($3 \times \text{float}$).
   - `sizeof(Point<4, EmptyPayload>) == 16` bytes ($4 \times \text{float}$).
   These guarantees are verified at compile-time using `static_assert`:
   ```cpp
   static_assert(sizeof(Point<2, EmptyPayload>) == 2 * sizeof(float));
   static_assert(sizeof(Point<3, EmptyPayload>) == 3 * sizeof(float));
   static_assert(sizeof(Point<4, EmptyPayload>) == 4 * sizeof(float));
   static_assert(sizeof(Point<7, EmptyPayload>) == 7 * sizeof(float));
   static_assert(sizeof(Point<9, EmptyPayload>) == 9 * sizeof(float));
   ```
3. **Loop Unrolling on Squared Distance:**
   ```cpp
   [[nodiscard]] inline float squared_dist(const Point &other) const noexcept {
     float sum = 0.0f;
   #if defined(__clang__)
   #pragma clang loop unroll(enable)
   #elif defined(__GNUC__)
   #pragma GCC unroll 8
   #endif
     for (std::size_t i = 0; i < Dim; ++i) {
       float diff = coords[i] - other.coords[i];
       sum += diff * diff;
     }
     return sum;
   }
   ```
   - Avoids calling `std::sqrt` until strictly necessary (triangle inequality comparisons and cell checking only require squared Euclidean distance $\sum (x_i - y_i)^2$).
   - Explicit GCC and Clang unrolling directives ensure vectorized FMA (Fused Multiply-Add) assembly instructions (`vfmadd231ps`).

---

### 2.2 `core/hash_grid.h`

#### Purpose
Implements spatial hashing, coordinate quantization, and neighborhood cell index generation for Rabin's algorithm.

#### Mathematical Foundation
Space is discretized into hypercubes of side length $\delta$ (the current minimum closest-pair distance). For any point $P \in \mathbb{R}^D$:
$$\text{Cell}_d = \left\lfloor \frac{P_d}{\delta} \right\rfloor \quad \forall d \in \{0, 1, \dots, D-1\}$$

Any two points with distance $<\delta$ are guaranteed to lie either in the **same grid cell** or in **immediately adjacent neighbor cells**.

#### Code Breakdown
1. **`GridCell<Dim>` Type Definition:**
   ```cpp
   template <std::size_t Dim>
   using GridCell = std::array<std::int64_t, Dim>;
   ```
   Uses 64-bit signed integers to prevent integer overflow when points cross coordinate quadrants (e.g. $[-10^7, +10^7]$).

2. **`ArrayHasher` (Multi-Dimensional Hash Functor):**
   ```cpp
   struct ArrayHasher {
     template <std::size_t Dim>
     std::size_t operator()(const GridCell<Dim> &arr) const noexcept {
       std::size_t hash_val = 0;
       for (const auto elem : arr) {
         hash_val ^= std::hash<std::int64_t>{}(elem) + 0x9e3779b9 +
                     (hash_val << 6) + (hash_val >> 2);
       }
       return hash_val;
     }
   };
   ```
   - Uses the Golden Ratio fractional constant $0x9e3779b9 \approx 2^{32}/\phi$ (derived from Boost `hash_combine`).
   - Ensures uniform bit dispersion across 64-bit hash buckets, minimizing collision clusters even when points are densely aligned along single axes.

3. **`to_grid_cell` Quantization:**
   ```cpp
   template <std::size_t Dim, typename PointType>
   [[nodiscard]] inline GridCell<Dim> to_grid_cell(const PointType &point, float delta) noexcept
   ```
   - Converts division by $\delta$ into multiplication by precomputed inverse: $\text{inv\_delta} = 1.0 / \text{safe\_delta}$ (vectorized reciprocal multiplication is significantly faster than division).
   - Bounds checks clamp coordinates against integer limits to safeguard against `NaN` or `inf` inputs.

4. **$3^D$ Neighbor Offsets Generator (`compute_neighbor_offsets`):**
   ```cpp
   template <std::size_t Dim>
   [[nodiscard]] inline std::vector<GridCell<Dim>> compute_neighbor_offsets()
   ```
   - In dimension $D$, each cell has $3^D - 1$ neighbors plus itself, totaling $3^D$ cells:
     - 2D: $3^2 = 9$ cells.
     - 3D: $3^3 = 27$ cells.
     - 4D: $3^4 = 81$ cells.
     - 5D: $3^5 = 243$ cells.
     - 7D: $3^7 = 2,187$ cells.
     - 9D: $3^9 = 19,683$ cells.
   - Computes offsets systematically using radix-3 decomposition:
     $$\text{offset}[d] = (\text{index} \bmod 3) - 1$$
   - Generated **once** as a static lookup vector per dimension, eliminating runtime recalculation.

---

### 2.3 `core/closest_pair.h`

#### Purpose
Contains the core deterministic and randomized Rabin spatial grid algorithm, returning distances, closest points, and rebuild statistics.

#### Core Engine Implementation (`find_closest_pair_grid`)
```cpp
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
[[nodiscard]] ClosestPairResult<PointType>
find_closest_pair_grid(std::span<const PointType> points, Filter filter, bool verbose)
```

#### Step-by-Step Algorithm Execution:
1. **Initial Seed Estimation:**
   Scans the first $\min(N, 50)$ points to find a valid initial pair that satisfies `filter(p1, p2)`, establishing an initial finite $\delta$.
2. **Hash Table Allocation:**
   Constructs `GridHashMap<Dim, PointType>` with `reserve(n)`.
3. **Sequential Stream & Collision Check:**
   For each incoming point $P_i$ ($i > \text{init\_limit}$):
   - Computes cell coordinate $C = \text{to\_grid\_cell}(P_i, \delta)$.
   - Scans all $3^D$ neighbor cells $C + \Delta$.
   - For every point $P_j$ residing in an adjacent cell:
     - Evaluates compile-time filter:
       ```cpp
       if constexpr (!Filter::is_trivial) {
         if (!filter(pi, pj)) continue;
       }
       ```
     - Computes Euclidean squared distance: $\text{dist\_sq} = P_i.\text{squared\_dist}(P_j)$.
     - If $\text{dist\_sq} < \delta^2$: updates best pair, sets $\delta = \sqrt{\text{dist\_sq}}$, and flags `rebuild = true`.
4. **Grid Rebuild (The Critical Scaling Step):**
   - If `rebuild == true`:
     - Increments `rebuild_count`.
     - Clears the entire hash table.
     - Re-inserts all preceding points $P_0, \dots, P_i$ into the newly scaled grid of cell size $\delta_{\text{new}}$.
   - Else:
     - Inserts $P_i$ into cell $C$.

#### Why Randomized Grid Scales in $O(N)$ Expected Time
- In arbitrary (or adversarial) input order, $\delta$ may shrink with every point, triggering $N$ rebuilds of size $1, 2, \dots, N$, causing $\sum_{i=1}^N i = O(N^2)$ execution time.
- In **Randomized Grid**, points are uniformly permuted. By backward analysis, the probability that the $i$-th point triggers a rebuild is at most $2/i$.
- Expected work per point:
  $$\mathbb{E}[\text{Work}_i] = O(1) + \frac{2}{i} \cdot O(i) = O(1)$$
- Total expected time across all $N$ points:
  $$\mathbb{E}[\text{Total Time}] = \sum_{i=1}^N O(1) = O(N)$$

#### Specialized Interfaces:
- **`find_closest_pair_deterministic`:** Evaluates points in their existing order.
- **`find_closest_pair_randomized`:** Takes `std::vector<PointType>` by value, shuffles with `std::mt19937`, and records execution time **strictly after** the copy and shuffle, ensuring memory allocation latency does not distort algorithmic benchmarks.
- **`find_closest_pair_pre_shuffled`:** Takes an already shuffled `std::span` to measure pure hardware throughput without any in-loop shuffling.

---

### 2.4 `core/space.h`

#### Purpose
Container and dataset generator for $D$-dimensional point collections, providing multi-threaded sorting and binary caching.

#### Code Breakdown:
1. **Parallel Sorting:**
   ```cpp
   void sort_points(SortStrategy strategy = SortStrategy::AxisAscending, std::size_t axis = 0)
   ```
   Uses Intel TBB / C++17 parallel execution policies (`std::execution::par`) to sort points across 4 strategies:
   - `AxisAscending`: Sorts by coordinate along chosen axis.
   - `AxisDescending`: Sorts in reverse order along axis.
   - `DistanceAscending`: Sorts by radial distance from origin.
   - `DistanceDescending`: Sorts in reverse radial distance.

2. **Adversarial "Ladder of Pairs" Generator:**
   ```cpp
   [[nodiscard]] static Space<Dim, Payload>
   create_adversarial_space(std::size_t count, float min_val = 0.0f, float max_val = 1000.0f)
   ```
   - Specifically engineered to break deterministic algorithms by forcing $N/2$ grid rebuilds.
   - Generates $N/2$ pairs of points. Pair $i$ is isolated along the Y-axis:
     $$y_i = \text{min\_val} + i \cdot \Delta y$$
   - Points within pair $i$ are placed on the X-axis separated by an internal distance $d_i$:
     $$P_{2i} = (0, y_i), \quad P_{2i+1} = (d_i, y_i)$$
   - The internal distance decreases monotonically by $\epsilon$:
     $$d_{i+1} = d_i - \epsilon$$
   - Result: As the deterministic algorithm encounters pair $i$, the distance is guaranteed to be smaller than all previous pairs, forcing an immediate full grid rebuild for **every single pair**.

3. **Binary Serialization (`get_or_create`):**
   - Automatically serializes spaces to `storage/datasets/synthetic/{type}_d{Dim}_n{count}.bin`.
   - On subsequent benchmark runs, the dataset is loaded directly from disk in milliseconds, guaranteeing 100% identical data and zero generation latency.

---

### 2.5 `core/metrics_logger.h`

#### Purpose
Provides standardized, thread-safe, high-precision CSV metrics logging matching the **17-column Unified Schema**.

#### Features:
- Computes mean, median, and sample standard deviation across timed iterations for both **execution time** and **rebuild count**.
- Encapsulates atomic iteration measurements into a JSON array string `Raw_Times_ms` (e.g. `"[0.53, 0.49, ...]"`) so CSV parsers treat it as a single table column.
- Encapsulates domain-specific metadata into `Extra_Metadata_JSON` (properly escaping double quotes per RFC 4180).

---

## 3. Adapters Layer (`refactored/adapters/`)

### 3.1 `adapters/opensky/opensky_adapter.h`

#### Purpose
Converts real-world ADS-B radar flight state vectors into 4D Euclidean points, enforces air traffic collision rules, and reads high-speed binary archives.

#### Mathematical Transformations:

```
                          Geodetic Coordinates
                         (lat, lon, alt_m, epoch_t)
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │        WGS-84 to ECEF (m)         │
                   │    a = 6378137.0 m, f = 1/298.257 │
                   └─────────────────┬─────────────────┘
                                     │
                                     ▼
                      Orthogonal Cartesian Coordinates
                                 (x, y, z)
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │    Metric Temporal Coupling (m)   │
                   │         w = α · (t - t_min)       │
                   └─────────────────┬─────────────────┘
                                     │
                                     ▼
                           Final 4D Vector in R⁴
                              (x, y, z, w)
```

1. **WGS-84 to Earth-Centered Earth-Fixed (ECEF):**
   Earth is modeled as an oblate spheroid with semi-major axis $a = 6,378,137\text{ m}$ and flattening $f = 1 / 298.257223563$. First eccentricity squared:
   $$e^2 = 2f - f^2$$
   Prime vertical radius of curvature $N(\phi)$:
   $$N(\phi) = \frac{a}{\sqrt{1 - e^2 \sin^2\phi}}$$
   Orthogonal coordinates in meters:
   $$x = (N(\phi) + h) \cos\phi \cos\lambda$$
   $$y = (N(\phi) + h) \cos\phi \sin\lambda$$
   $$z = (N(\phi)(1 - e^2) + h) \sin\phi$$
   Where $\phi = \text{latitude}$, $\lambda = \text{longitude}$, $h = \text{altitude}$.

2. **Metric Temporal Coordinate ($w$):**
   $$w = \alpha \cdot (t - t_{\min})$$
   - $t$: Unix epoch in seconds.
   - $t_{\min}$: Origin timestamp of the observation window.
   - $\alpha$: Characteristic flight velocity scaling factor ($\approx 180\text{--}250\text{ m/s}$). Converts seconds into equivalent spatial meters traversed by an aircraft.

3. **Strategy 2 Intra-Flight Collision Pruning:**
   ```cpp
   struct Strategy2FlightFilter {
     static constexpr bool is_trivial = false;
     float min_separation{0.05f};

     [[nodiscard]] inline bool operator()(const FlightPoint4D &a, const FlightPoint4D &b) const noexcept {
       if (a.payload.flight_id == b.payload.flight_id) return false;
       if (min_separation > 0.0f) {
         return a.squared_dist(b) > (min_separation * min_separation);
       }
       return true;
     }
   };
   ```
   - **`flight_id(a) == flight_id(b)`:** Rejects pairs belonging to the same aircraft. ADS-B stations receive consecutive pings from the same plane every 1–5 seconds. Without this rule, the closest pair would trivially be the same plane observed at adjacent timestamps.
   - **`min_separation`:** Rejects sensor duplicate artifacts where two distinct flight IDs report the exact same position ($d \le 5\text{ cm}$).

4. **Zero-Copy Binary Loader:**
   Directly reads `OPS2` (OpenSky format v2 with 64-bit float $t_{\min}$ and 32-bit float $\alpha$) and `OPSK` files using packed structs:
   ```cpp
   #pragma pack(push, 1)
   struct BinaryRecord {
     std::uint32_t id;
     float coords[4];
   };
   #pragma pack(pop)
   ```
   Reads millions of points in a single `in.read()` call directly into contiguous vectors.

---

## 4. Experiments Layer (`refactored/experiments/`)

### 4.1 `experiments/synthetic/benchmark_synthetic.cpp`
- **Target:** `bin_synthetic`
- **Scope:** Benchmarks dimensions $D \in \{2, 3, 4, 5, 7, 9\}$ across:
  - Normal Space in Original Generation Order
  - Normal Space in Sorted X-Axis Order
  - Adversarial "Ladder of Pairs" Space
- **CLI Options:**
  - `--quick`: Runs 2,000 points per dimension for instant verification.
  - `--iterations <N>`: Sets repetitions per configuration (default: 5).
- **Output:** Streams results to `storage/results/synthetic/synthetic_benchmark_<timestamp>.csv` and appends to `master_synthetic.csv`.

### 4.2 `experiments/opensky/benchmark_opensky.cpp`
- **Target:** `bin_opensky`
- **Scope:** Ingests hourly preprocessed OpenSky flight datasets (e.g. `states_2019-05-27-08_4d.bin` with ~1.3M to 2.2M points per hour).
- **Execution:** Runs Deterministic vs. Randomized grid algorithms with `Strategy2FlightFilter`.
- **Output:** Streams results to `storage/results/opensky/opensky_benchmark_<timestamp>.csv` and appends to `master_opensky.csv`.

### 4.3 `experiments/cache/benchmark_cache.cpp`
- **Target:** `bin_cache`
- **Scope:** Micro-benchmarks cache behavior across memory layouts on 4D spaces:
  1. **Contiguous Sequential:** Points visited in memory address order.
  2. **Pre-Shuffled Contiguous:** Points shuffled globally and stored in contiguous memory before iteration (hardware prefetcher friendly).
- **Output:** Streams results to `storage/results/cache/cache_benchmark_<timestamp>.csv`.

---

## 5. Storage Layer & Unified Measurement Schema (`refactored/storage/`)

All benchmark drivers produce CSV files conforming strictly to the **17-column Unified Schema**:

```csv
Timestamp,Benchmark_Type,Dataset_Name,Dimensions,Num_Points,Input_Order,Algorithm,Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Times_ms,Extra_Metadata_JSON
```

### Column Specifications:
| Index | Column Name | Type | Description |
|---|---|---|---|
| 1 | `Timestamp` | String (ISO) | Execution timestamp: `YYYY-MM-DD HH:MM:SS` |
| 2 | `Benchmark_Type` | String | Categorization: `Synthetic`, `OpenSky`, or `CacheBenchmark` |
| 3 | `Dataset_Name` | String | Name/Tag of dataset: `Normal`, `Adversarial`, `states_2019-05-27-08_4d` |
| 4 | `Dimensions` | Integer | Spatial dimensionality $D$ (2, 3, 4, 5, 7, 9) |
| 5 | `Num_Points` | Integer | Total point count $N$ |
| 6 | `Input_Order` | String | Ordering configuration: `Original`, `Sorted_X_Axis`, `Ladder_of_Pairs` |
| 7 | `Algorithm` | String | Solver: `Deterministic Grid` or `Randomized Grid` |
| 8 | `Iterations` | Integer | Number of benchmark runs $k$ |
| 9 | `Min_Distance` | Float | Minimum Euclidean distance found $\delta^*$ |
| 10 | `Mean_Time_ms` | Float | Arithmetic mean execution time in milliseconds |
| 11 | `Median_Time_ms` | Float | Median execution time in milliseconds |
| 12 | `StdDev_Time_ms` | Float | Sample standard deviation of execution time |
| 13 | `Mean_Rebuilds` | Float | Mean count of grid rebuild events |
| 14 | `Median_Rebuilds` | Float | Median count of grid rebuild events |
| 15 | `StdDev_Rebuilds` | Float | Standard deviation of grid rebuild events |
| 16 | `Raw_Times_ms` | JSON Array | Array of individual iteration times: `"[0.86, 0.72]"` |
| 17 | `Extra_Metadata_JSON` | JSON Object | Domain-specific parameters: `{"alpha": 186.4, "min_separation_m": 0.05}` |

---

## 6. Analysis Engine (`refactored/analyzer/`)

### 6.1 `analyzer/run_analyzer.py`

#### Purpose
Universal data analysis and figure generation tool matching ACM/IEEE academic publication styling.

#### Key Functions:
1. **`load_and_preprocess_csv(csv_path)`:**
   - Ingests any CSV adhering to the 17-column schema.
   - Automatically detects scaling units (thousands `k` vs millions `M`).
   - Parses JSON string arrays (`Raw_Times_ms`) into NumPy vectors.
2. **Timing Scaling Plots (`01`–`04`):**
   - Plots execution time vs. $N$ on logarithmic axes.
   - Fits empirical scaling exponents using `np.polyfit` in log-log space ($\log_{10} T = k \cdot \log_{10} N + c$).
   - Overlays theoretical $O(N)$ and $O(N^2)$ reference slopes.
3. **Comparative Analysis (`05`–`09`):**
   - Plots Deterministic vs. Randomized speedup across dimensions.
4. **Speedup Heatmaps (`10`–`12`):**
   - Diverging colormap (`RdBu_r`) centered at zero using `TwoSlopeNorm(vmin=-1, vcenter=0, vmax=4)`:
     - Neutral white = $1.0\times$ (identical performance).
     - Red shades = Randomized algorithm faster.
     - Blue shades = Deterministic algorithm faster.
   - Annotates each cell with speedup ratios (e.g. `130x`).

---

## 7. Build System (`refactored/CMakeLists.txt`)

```cmake
cmake_minimum_required(VERSION 3.16)
project(ND-closest-pair-refactored VERSION 2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Optimized release flags for native SIMD and AVX2 vectorization
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG -Wall -Wextra")

find_package(TBB REQUIRED)
find_package(Threads REQUIRED)

include_directories(${CMAKE_CURRENT_SOURCE_DIR})

add_executable(bin_synthetic experiments/synthetic/benchmark_synthetic.cpp)
target_link_libraries(bin_synthetic PRIVATE TBB::tbb Threads::Threads)

add_executable(bin_opensky experiments/opensky/benchmark_opensky.cpp)
target_link_libraries(bin_opensky PRIVATE TBB::tbb Threads::Threads)

add_executable(bin_cache experiments/cache/benchmark_cache.cpp)
target_link_libraries(bin_cache PRIVATE TBB::tbb Threads::Threads)
```

### Compiler Optimization Highlights:
- **`-O3`**: Full loop vectorization, inline expansion, and algebraic simplification.
- **`-march=native`**: Generates AVX2 / FMA instructions specific to the host CPU architecture.
- **`-DNDEBUG`**: Strips runtime assertion checks from inner collision loops.
- **`TBB::tbb`**: Provides work-stealing task threadpools for `std::execution::par` sorting.
