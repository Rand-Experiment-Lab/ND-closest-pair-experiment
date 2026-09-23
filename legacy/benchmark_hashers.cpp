#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <execution>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "space.h"

// ============================================================================
// 1. Hashers Definition
// ============================================================================

template <std::size_t Dim>
using GridCell = std::array<std::int64_t, Dim>;

// 1. Current implementation (Boost hash_combine + std::hash)
struct BoostArrayHasher {
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

// 2. FNV-1a / SplitMix-64 Multiplicative Hasher
struct FastSplitMixHasher {
  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &arr) const noexcept {
    std::uint64_t h = 14695981039346656037ULL;
    for (const auto elem : arr) {
      h ^= static_cast<std::uint64_t>(elem);
      h *= 1099511628211ULL;
      h ^= (h >> 32);
    }
    h ^= h >> 33;
    h *= 0xff51afd7ed558ccdULL;
    h ^= h >> 33;
    h *= 0xc4ceb9fe1a85ec53ULL;
    h ^= h >> 33;
    return static_cast<std::size_t>(h);
  }
};

// 3. Spatial Primes Hasher (Geometric / Lattice-oriented)
struct SpatialPrimesHasher {
  static constexpr std::uint64_t Primes[] = {
      73856093ULL,   19349663ULL,   83492791ULL,
      2654435761ULL, 5147483647ULL, 6180339887ULL,
      8209384729ULL, 9123456789ULL, 9876543211ULL
  };

  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &arr) const noexcept {
    std::uint64_t h = 0;
    for (std::size_t i = 0; i < Dim; ++i) {
      h ^= static_cast<std::uint64_t>(arr[i]) * Primes[i % 9];
    }
    h ^= (h >> 30);
    h *= 0xbf58476d1ce4e5b9ULL;
    h ^= (h >> 27);
    return static_cast<std::size_t>(h);
  }
};

// 4. Compact Wyhash-style Hasher (mum-multiplier on memory words)
struct WyhashStyleHasher {
  static inline std::uint64_t wymum(std::uint64_t A, std::uint64_t B) noexcept {
#if defined(__SIZEOF_INT128__)
    __uint128_t r = A;
    r *= B;
    return static_cast<std::uint64_t>(r ^ (r >> 64));
#else
    std::uint64_t ha = A >> 32, la = static_cast<std::uint32_t>(A);
    std::uint64_t hb = B >> 32, lb = static_cast<std::uint32_t>(B);
    std::uint64_t w0 = la * lb;
    std::uint64_t w1 = ha * lb + (w0 >> 32);
    std::uint64_t w2 = la * hb + static_cast<std::uint32_t>(w1);
    std::uint64_t hi = ha * hb + (w1 >> 32) + (w2 >> 32);
    std::uint64_t lo = (w2 << 32) | static_cast<std::uint32_t>(w0);
    return hi ^ lo;
#endif
  }

  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &arr) const noexcept {
    static constexpr std::uint64_t secret[4] = {
        0xa0761d6478bd642fULL, 0xe7037ed1a0b428dbULL,
        0x8ebc6af09c88c6e3ULL, 0x589965cc75374cc3ULL};
    std::uint64_t seed = secret[0];
    for (std::size_t i = 0; i < Dim; ++i) {
      seed = wymum(static_cast<std::uint64_t>(arr[i]) ^ secret[i % 4],
                   seed ^ secret[(i + 1) % 4]);
    }
    return static_cast<std::size_t>(seed);
  }
};

// Map alias for arbitrary hasher
template <std::size_t Dim, typename Hasher>
using CustomGridHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<Point<Dim>>, Hasher>;

// Grid cell converter
template <std::size_t Dim>
[[nodiscard]] inline GridCell<Dim> to_grid_cell(const Point<Dim> &point,
                                               float delta) noexcept {
  GridCell<Dim> cell{};
  for (std::size_t d = 0; d < Dim; ++d) {
    cell[d] = static_cast<std::int64_t>(std::floor(point.coordinates[d] / delta));
  }
  return cell;
}

// Statistics structure
struct BenchmarkStats {
  double mean_time_ms{0.0};
  double median_time_ms{0.0};
  double std_dev_time_ms{0.0};
  double mean_raw_hash_time_ms{0.0};
  std::size_t unique_hash_count{0};
  std::size_t total_points_hashed{0};
  std::size_t unique_cells{0};
  std::size_t bucket_count{0};
  float max_load_factor{0.0f};
};

template <typename T>
void compute_stats(const std::vector<T> &values, double &mean, double &median,
                   double &std_dev) {
  if (values.empty()) {
    mean = median = std_dev = 0.0;
    return;
  }
  size_t n = values.size();
  double sum = std::accumulate(values.begin(), values.end(), 0.0);
  mean = sum / static_cast<double>(n);

  double var_sum = 0.0;
  for (const auto &v : values) {
    double diff = static_cast<double>(v) - mean;
    var_sum += diff * diff;
  }
  std_dev = std::sqrt(var_sum / (n > 1 ? n - 1 : 1));

  std::vector<double> sorted(values.begin(), values.end());
  std::sort(sorted.begin(), sorted.end());
  if (n % 2 == 0) {
    median = (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0;
  } else {
    median = sorted[n / 2];
  }
}

// ============================================================================
// Benchmark Routine for a Single Hasher
// ============================================================================
template <std::size_t Dim, typename Hasher>
BenchmarkStats benchmark_hasher(const std::vector<Point<Dim>> &points,
                                int rebuild_iterations, float base_delta,
                                bool use_par) {
  const std::size_t N = points.size();
  Hasher hasher;

  // 1. Measure raw hashing speed & hash collision quality
  std::vector<GridCell<Dim>> cells(N);
  if (use_par) {
    std::transform(std::execution::par, points.begin(), points.end(),
                   cells.begin(), [base_delta](const Point<Dim> &p) {
                     return to_grid_cell<Dim>(p, base_delta);
                   });
  } else {
    std::transform(std::execution::seq, points.begin(), points.end(),
                   cells.begin(), [base_delta](const Point<Dim> &p) {
                     return to_grid_cell<Dim>(p, base_delta);
                   });
  }

  // Raw hash computation time benchmark
  std::vector<double> raw_hash_times;
  raw_hash_times.reserve(rebuild_iterations);
  std::vector<std::size_t> hashes(N);

  for (int iter = 0; iter < rebuild_iterations; ++iter) {
    auto t0 = std::chrono::high_resolution_clock::now();
    if (use_par) {
      std::transform(std::execution::par, cells.begin(), cells.end(),
                     hashes.begin(),
                     [&hasher](const GridCell<Dim> &c) { return hasher(c); });
    } else {
      std::transform(std::execution::seq, cells.begin(), cells.end(),
                     hashes.begin(),
                     [&hasher](const GridCell<Dim> &c) { return hasher(c); });
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    raw_hash_times.push_back(
        std::chrono::duration<double, std::milli>(t1 - t0).count());
  }

  // Count unique cells vs unique hash values (to observe collision rate)
  std::unordered_set<std::size_t> unique_hashes;
  unique_hashes.reserve(N);
  for (std::size_t h : hashes) {
    unique_hashes.insert(h);
  }

  // 2. Measure Full Grid Rebuilds (Insertions, Table rehashing, vector appends)
  std::vector<double> rebuild_times;
  rebuild_times.reserve(rebuild_iterations);

  std::size_t final_unique_cells = 0;
  std::size_t final_bucket_count = 0;
  float final_max_load_factor = 0.0f;

  for (int iter = 0; iter < rebuild_iterations; ++iter) {
    // vary delta slightly each rebuild to simulate shrinking delta
    float current_delta = base_delta * (1.0f - 0.03f * static_cast<float>(iter));
    CustomGridHashMap<Dim, Hasher> grid_map;

    auto t0 = std::chrono::high_resolution_clock::now();

    // Standard incremental grid insertion
    for (std::size_t j = 0; j < N; ++j) {
      GridCell<Dim> c = to_grid_cell<Dim>(points[j], current_delta);
      grid_map[c].push_back(points[j]);
    }

    auto t1 = std::chrono::high_resolution_clock::now();
    rebuild_times.push_back(
        std::chrono::duration<double, std::milli>(t1 - t0).count());

    if (iter == 0) {
      final_unique_cells = grid_map.size();
      final_bucket_count = grid_map.bucket_count();
      final_max_load_factor = grid_map.max_load_factor();
    }
  }

  BenchmarkStats stats;
  compute_stats(rebuild_times, stats.mean_time_ms, stats.median_time_ms,
                stats.std_dev_time_ms);

  double dummy_med, dummy_std;
  compute_stats(raw_hash_times, stats.mean_raw_hash_time_ms, dummy_med,
                dummy_std);

  stats.unique_hash_count = unique_hashes.size();
  stats.total_points_hashed = N;
  stats.unique_cells = final_unique_cells;
  stats.bucket_count = final_bucket_count;
  stats.max_load_factor = final_max_load_factor;

  return stats;
}

// ============================================================================
// Dimension Driver
// ============================================================================
template <std::size_t Dim>
void run_dimension_suite(std::size_t num_points, int rebuild_iterations,
                         bool use_par) {
  std::cout << "\n"
            << std::string(96, '=') << "\n"
            << "  DIMENSION: " << Dim << "D | Points: " << num_points
            << " | Rebuild Iterations: " << rebuild_iterations
            << " | Policy: " << (use_par ? "std::execution::par" : "std::execution::seq")
            << "\n"
            << std::string(96, '=') << "\n";

  // Generate uniform points
  auto space = Space<Dim>::get_or_create("uniform", num_points, "datasets", 12345);

  // Reasonable delta for testing grid density
  float delta = 25.0f;

  struct Runner {
    std::string name;
    BenchmarkStats stats;
  };

  std::vector<Runner> results = {
      {"1. BoostArrayHasher (Current)",
       benchmark_hasher<Dim, BoostArrayHasher>(space.points, rebuild_iterations,
                                               delta, use_par)},
      {"2. FastSplitMixHasher       ",
       benchmark_hasher<Dim, FastSplitMixHasher>(
           space.points, rebuild_iterations, delta, use_par)},
      {"3. SpatialPrimesHasher      ",
       benchmark_hasher<Dim, SpatialPrimesHasher>(
           space.points, rebuild_iterations, delta, use_par)},
      {"4. WyhashStyleHasher        ",
       benchmark_hasher<Dim, WyhashStyleHasher>(
           space.points, rebuild_iterations, delta, use_par)}};

  std::cout << std::left << std::setw(32) << "Hasher"
            << std::right << std::setw(14) << "Mean Rebuild"
            << std::setw(14) << "Median"
            << std::setw(12) << "StdDev"
            << std::setw(14) << "Raw Hash(ms)"
            << std::setw(14) << "Unique Hashes"
            << "\n";
  std::cout << std::string(102, '-') << "\n";

  double baseline_mean = results[0].stats.mean_time_ms;

  for (const auto &r : results) {
    double speedup = baseline_mean / (r.stats.mean_time_ms > 0 ? r.stats.mean_time_ms : 1.0);
    std::cout << std::left << std::setw(32) << r.name
              << std::right << std::fixed << std::setprecision(2)
              << std::setw(11) << r.stats.mean_time_ms << " ms"
              << std::setw(11) << r.stats.median_time_ms << " ms"
              << std::setw(9) << r.stats.std_dev_time_ms << " ms"
              << std::setw(11) << r.stats.mean_raw_hash_time_ms << " ms"
              << std::setw(14) << r.stats.unique_hash_count;

    if (&r != &results[0]) {
      std::cout << " (" << std::fixed << std::setprecision(2) << speedup
                << "x vs Boost)";
    }
    std::cout << "\n";
  }
}

// ============================================================================
// Main entry
// ============================================================================
int main(int argc, char *argv[]) {
  // Mode selection: seq (default) or par
  bool use_par = false;
  std::size_t num_points = 100'000;
  int rebuild_iterations = 5;

  if (argc > 1) {
    std::string arg = argv[1];
    if (arg == "par" || arg == "parallel") {
      use_par = true;
    } else if (arg == "seq" || arg == "sequential") {
      use_par = false;
    }
  }

  if (argc > 2) {
    num_points = std::stoull(argv[2]);
  }
  if (argc > 3) {
    rebuild_iterations = std::stoi(argv[3]);
  }

  std::cout << "\n========================================================\n"
            << "     N-DIMENSIONAL GRID HASHER COMPARISON BENCHMARK     \n"
            << "========================================================\n"
            << "Config:\n"
            << "  Execution Policy: " << (use_par ? "PARALLEL (std::execution::par)" : "SEQUENTIAL (std::execution::seq)") << "\n"
            << "  Num Points      : " << num_points << "\n"
            << "  Rebuild Iters   : " << rebuild_iterations << "\n"
            << "Usage:\n"
            << "  ./benchmark_hashers [seq|par] [num_points] [rebuild_iters]\n"
            << "========================================================\n";

  // Test across 2D, 3D, 5D, 7D, 9D
  run_dimension_suite<2>(num_points, rebuild_iterations, use_par);
  run_dimension_suite<3>(num_points, rebuild_iterations, use_par);
  run_dimension_suite<5>(num_points, rebuild_iterations, use_par);
  run_dimension_suite<7>(num_points, rebuild_iterations, use_par);
  run_dimension_suite<9>(num_points, rebuild_iterations, use_par);

  std::cout << "\nBenchmark complete.\n";
  return 0;
}
