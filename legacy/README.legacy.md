# N-Dimensional Closest Pair Experiment

Instructions to build, verify, and run performance benchmarks for the N-Dimensional Closest Pair project on Linux and Windows.

---

## Prerequisites

- **C++ Compiler**: C++20 standard support
  - Linux: `g++` 10+ or `clang++` 11+
  - Windows: Visual Studio 2022 (MSVC v143+) or MinGW-w64
- **Build System**: CMake 3.10+
- **Libraries**: Intel TBB (`tbb`)
- **Python** *(optional for plotting)*: Python 3 with `pandas`, `matplotlib`, `seaborn`

---

## Linux Instructions

### 1. Install Dependencies

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install build-essential cmake libtbb-dev python3 python3-pip
pip install pandas matplotlib seaborn
```

### 2. Build the Project

```bash
# Create build directory and compile
cmake -B build -S .
cmake --build build -j$(nproc)
```

### 3. Run Synthetic Space Benchmarks (from `build/`)

```bash
cd build

# Verify correctness (Grid vs Brute Force baseline)
./verify

# Run quick benchmark verification
./experiment_quick
./experiment_quick normal
./experiment_quick adversarial

# Run synthetic performance benchmark suite
./experiment              # Runs both Normal (100k-1M) and Adversarial (10k-50k)
./experiment normal       # Runs only Normal space experiments (Original & Sorted)
./experiment adversarial  # Runs only Adversarial space experiments (Ladder of Pairs)

# (Optional) Pre-generate binary dataset caches
./data_set_generator
```

---

## Real-World OpenSky 4D ADS-B Benchmark

All real-world experiments are executed with the **`build/` folder as the reference point**. All raw inputs, intermediate outputs, and results resolve relative to `build/`:
- **Raw Data:** `../opensky_experiment/data/<date>/` (contains raw `states_*.csv.gz`)
- **Intermediate Outputs:** `../opensky_experiment/data/<date>_hourly/` (contains 24 cleaned CSVs and 24 `.bin` files)
- **Benchmark Results:** `../opensky_experiment/results/` (timestamped result CSVs)

### 1. Compile OpenSky Targets (from project root or `build/`)

```bash
cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
cmake --build build --target experiment_opensky experiment_opensky_hourly -j$(nproc)
```

### 2. Hourly Benchmark Workflow (24 Hours x 4 Scenarios)

From inside `build/`:

```bash
cd build

# Step A: Preprocess raw hourly .csv.gz archives into 4D Cartesian (x, y, z, w)
python3 ../opensky_experiment/scripts/preprocess_hourly_opensky.py \
  ../opensky_experiment/data/2019-05-27 \
  ../opensky_experiment/data/2019-05-27_hourly

# Step B: Run the 4-test benchmark suite (10 iterations, 0.05m non-zero filter)
./experiment_opensky_hourly ../opensky_experiment/data/2019-05-27_hourly 10 0.05
```
*Results automatically saved to: `../opensky_experiment/results/opensky_hourly_results_<timestamp>.csv`*

### 3. Full-Day Consolidated Benchmark (39 Million Points)

From inside `build/`:

```bash
cd build

# Step A: (Optional) Preprocess all 24 hours into a single consolidated binary
python3 ../opensky_experiment/scripts/preprocess_day_opensky.py \
  ../opensky_experiment/data/2019-05-27 \
  ../opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin

# Step B: Run full-day benchmark across 4 order scenarios
./experiment_opensky ../opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin 10 0.05
```
*Results automatically saved to: `../opensky_experiment/results/opensky_results_<timestamp>.csv`*

### 4. All-in-One Automated Pipeline (Download, Preprocess & Benchmark)

From inside `build/`:

```bash
cd build

# Run for a specific day:
python3 ../opensky_experiment/scripts/run_automated_pipeline.py --date 2019-05-27

# Run batch sequentially across all available 25 dates with all 24 hours:
python3 ../opensky_experiment/scripts/run_automated_pipeline.py --all-dates --min-hours 24
```

For complete technical documentation on the ECEF spatial projection, metric velocity scaling $\alpha$, and Strategy 2 intra-flight pruning, refer to [DEVELOPER_DOCS.md](file:///media/vithurshan/vithu/rand/opensky_experiment/DEVELOPER_DOCS.md).

---

## Windows Instructions

### Option A: Using Visual Studio & Developer Command Prompt

#### 1. Install Dependencies

- Install **Visual Studio 2022** with the **Desktop development with C++** workload.
- Install Intel TBB via vcpkg or NuGet:

  ```cmd
  vcpkg install tbb:x64-windows
  ```

#### 2. Build the Project

Open **Developer Command Prompt for VS 2022** and run:

```cmd
cmake -B build -S . -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Release
```

#### 3. Run Executables

```cmd
:: Run verification
.\build\Release\verify.exe

:: Run quick benchmark
.\build\Release\experiment_quick.exe

:: Run full experiment suite
.\build\Release\experiment.exe

:: Generate plots
python plot_advanced.py
```

---

### Option B: Using MSYS2 / MinGW-w64

#### 1. Install Dependencies in MSYS2 UCRT64 Terminal

```bash
pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-tbb python-pandas python-matplotlib python-seaborn
```

#### 2. Build and Run

```bash
cmake -B build -S . -G "MinGW Makefiles"
cmake --build build

./build/verify.exe
./build/experiment_quick.exe
./build/experiment.exe
```
