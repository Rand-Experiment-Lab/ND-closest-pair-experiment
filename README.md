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

### 3. Run Executables

```bash
# Verify correctness (Grid vs Brute Force baseline)
./build/verify

# Run quick benchmark verification (supports: 'normal', 'adversarial', or no argument for all)
./build/experiment_quick
./build/experiment_quick normal
./build/experiment_quick adversarial

# Run performance benchmark suite
./build/experiment              # Runs both Normal (100k-1M) and Adversarial (10k-50k)
./build/experiment normal       # Runs only Normal space experiments (Original & Sorted)
./build/experiment adversarial  # Runs only Adversarial space experiments (Ladder of Pairs)

# (Optional) Pre-generate binary dataset caches matching the experiment suites
./build/data_set_generator

# (Optional) Generate benchmark plots
python3 plot_advanced.py
```

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
