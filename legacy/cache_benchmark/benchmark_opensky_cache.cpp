#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#if __has_include(<span>)
#include <span>
#else
namespace std {
template <typename T>
class span {
  const T *ptr_{nullptr};
  std::size_t size_{0};
public:
  constexpr span() noexcept = default;
  constexpr span(const T *ptr, std::size_t count) noexcept : ptr_(ptr), size_(count) {}
  template <typename Container>
  constexpr span(const Container &c) noexcept : ptr_(c.data()), size_(c.size()) {}
  [[nodiscard]] constexpr const T &operator[](std::size_t idx) const noexcept { return ptr_[idx]; }
  [[nodiscard]] constexpr std::size_t size() const noexcept { return size_; }
  [[nodiscard]] constexpr bool empty() const noexcept { return size_ == 0; }
  [[nodiscard]] constexpr const T *data() const noexcept { return ptr_; }
  [[nodiscard]] constexpr const T *begin() const noexcept { return ptr_; }
  [[nodiscard]] constexpr const T *end() const noexcept { return ptr_ + size_; }
};
}
#endif

// ---------------------------------------------------------------------------
// 4D Flight Point Struct & Grid Structures
// ---------------------------------------------------------------------------
template <std::size_t Dim = 4>
struct FlightPoint {
  std::array<float, Dim> coordinates{};
  std::uint32_t flight_id{0};

  [[nodiscard]] inline float distance_to(const FlightPoint<Dim> &other) const noexcept {
    float sum_of_squares = 0.0f;
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coordinates[i] - other.coordinates[i];
      sum_of_squares += diff * diff;
    }
    return std::sqrt(sum_of_squares);
  }
};

template <std::size_t Dim = 4>
using GridCell = std::array<std::int64_t, Dim>;

// 64-bit high dispersion hash function for N-D grid coordinate cells
struct ArrayHasher {
  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &a) const noexcept {
    std::size_t h = 0;
    for (std::size_t i = 0; i < Dim; ++i) {
      std::uint64_t x = static_cast<std::uint64_t>(a[i]);
      x ^= x >> 30;
      x *= 0xbf58476d1ce4e5b9ULL;
      x ^= x >> 27;
      x *= 0x94d049bb133111ebULL;
      x ^= x >> 31;
      h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    }
    return h;
  }
};

template <std::size_t Dim = 4>
using FlightHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<FlightPoint<Dim>>, ArrayHasher>;

// Generates the 3^Dim neighbor offset vector (81 cells for 4D)
template <std::size_t Dim = 4>
std::vector<GridCell<Dim>> generate_neighbor_offsets() {
  std::vector<GridCell<Dim>> offsets;
  std::size_t total = 1;
  for (std::size_t i = 0; i < Dim; ++i) total *= 3;
  offsets.reserve(total);

  GridCell<Dim> current_offset{};
  auto generate_recursive = [&](auto &self, std::size_t dim_index) -> void {
    if (dim_index == Dim) {
      offsets.push_back(current_offset);
      return;
    }
    for (std::int64_t val = -1; val <= 1; ++val) {
      current_offset[dim_index] = val;
      self(self, dim_index + 1);
    }
  };
  generate_recursive(generate_recursive, 0);
  return offsets;
}

// Coordinate mapping into spatial grid index with overflow guards
template <std::size_t Dim = 4>
[[nodiscard]] inline GridCell<Dim> to_flight_grid_cell(const FlightPoint<Dim> &point,
                                                       float delta) noexcept {
  GridCell<Dim> cell{};
  const float safe_delta = std::max(delta, std::numeric_limits<float>::epsilon());
  const double inv_delta = 1.0 / static_cast<double>(safe_delta);

  constexpr double max_safe = static_cast<double>(std::numeric_limits<std::int64_t>::max() - 1000);
  constexpr double min_safe = static_cast<double>(std::numeric_limits<std::int64_t>::min() + 1000);

  for (std::size_t d = 0; d < Dim; ++d) {
    double scaled = std::floor(static_cast<double>(point.coordinates[d]) * inv_delta);
    if (std::isnan(scaled) || scaled > max_safe) {
      cell[d] = std::numeric_limits<std::int64_t>::max() - 1000;
    } else if (scaled < min_safe) {
      cell[d] = std::numeric_limits<std::int64_t>::min() + 1000;
    } else {
      cell[d] = static_cast<std::int64_t>(scaled);
    }
  }
  return cell;
}

// Neighbor cell search:
// 1. Skips same aircraft (pi.flight_id == point.flight_id)
// 2. Skips duplicate sensor artifacts below min_separation
template <std::size_t Dim = 4>
[[nodiscard]] inline float find_min_in_neighbor_cells(
    const GridCell<Dim> &center_cell, const FlightHashMap<Dim> &grid_map,
    const FlightPoint<Dim> &pi, const std::vector<GridCell<Dim>> &neighbor_offsets,
    float min_separation = 0.05f) {
  float min_dist = std::numeric_limits<float>::infinity();

  for (const auto &offset : neighbor_offsets) {
    GridCell<Dim> neighbor_cell;
    for (std::size_t d = 0; d < Dim; ++d) {
      neighbor_cell[d] = center_cell[d] + offset[d];
    }

    auto it = grid_map.find(neighbor_cell);
    if (it != grid_map.end()) {
      for (const auto &point : it->second) {
        if (pi.flight_id == point.flight_id) {
          continue; // Ignore intra-flight telemetry
        }
        float dist = pi.distance_to(point);
        if (dist <= min_separation) {
          continue; // Filter duplicate GPS sensor reports
        }
        if (dist < min_dist) {
          min_dist = dist;
        }
      }
    }
  }
  return min_dist;
}

// ---------------------------------------------------------------------------
// Core Closest Pair Algorithm for Flight Points
// ---------------------------------------------------------------------------
template <std::size_t Dim = 4>
[[nodiscard]] float find_min_dist_flight_grid(std::span<const FlightPoint<Dim>> points,
                                             float min_separation,
                                             std::size_t *out_rebuild_count = nullptr) {
  const std::size_t size = points.size();
  if (size < 2) return 0.0f;

  std::size_t rebuilds = 0;
  const auto neighbor_offsets = generate_neighbor_offsets<Dim>();

  // Determine initial candidate delta
  float delta = std::numeric_limits<float>::infinity();
  const auto &p0 = points[0];
  for (std::size_t i = 1; i < size; ++i) {
    const auto &pi = points[i];
    if (pi.flight_id != p0.flight_id) {
      float d = p0.distance_to(pi);
      if (d > min_separation) {
        delta = d;
        break;
      }
    }
  }

  if (delta == std::numeric_limits<float>::infinity() ||
      delta <= std::numeric_limits<float>::epsilon()) {
    delta = 10000.0f;
  }

  FlightHashMap<Dim> grid_map;
  grid_map.reserve(std::min(size, static_cast<std::size_t>(65536)));

  grid_map[to_flight_grid_cell(points[0], delta)].push_back(points[0]);
  grid_map[to_flight_grid_cell(points[1], delta)].push_back(points[1]);

  for (std::size_t i = 2; i < size; ++i) {
    const auto &pi = points[i];
    GridCell<Dim> cell = to_flight_grid_cell(pi, delta);

    float neighbor_min = find_min_in_neighbor_cells<Dim>(
        cell, grid_map, pi, neighbor_offsets, min_separation);

    if (neighbor_min < delta) {
      delta = neighbor_min;
      ++rebuilds;

      grid_map.clear();
      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[j];
        grid_map[to_flight_grid_cell(pj, delta)].push_back(pj);
      }
    } else {
      grid_map[cell].push_back(pi);
    }
  }

  if (out_rebuild_count) *out_rebuild_count = rebuilds;
  return delta;
}

// ---------------------------------------------------------------------------
// Binary Dataset Loader
// ---------------------------------------------------------------------------
bool load_flight_points(const std::string &path, std::vector<FlightPoint<4>> &points,
                        std::size_t max_points_to_load) {
  std::ifstream in(path, std::ios::binary);
  if (!in.is_open()) {
    std::cerr << "[Error] Cannot open binary file: " << path << "\n";
    return false;
  }

  char magic[4];
  in.read(magic, 4);
  std::string magic_str(magic, 4);
  if (magic_str != "OPS2" && magic_str != "OPS1") {
    std::cerr << "[Error] Invalid magic header '" << magic_str << "' in " << path << "\n";
    return false;
  }

  std::uint32_t file_dim = 0;
  std::uint64_t count = 0;
  float alpha = 0.0f;
  double t_ref = 0.0;

  in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
  in.read(reinterpret_cast<char *>(&count), sizeof(count));
  in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
  if (magic_str == "OPS2") {
    in.read(reinterpret_cast<char *>(&t_ref), sizeof(t_ref));
  }

  if (file_dim != 4) {
    std::cerr << "[Error] Dimension mismatch: expected 4, got " << file_dim << "\n";
    return false;
  }

  std::size_t points_to_read = std::min(static_cast<std::uint64_t>(max_points_to_load), count);
  std::cout << "[Dataset Loader] File contains " << count << " points. Reading first "
            << points_to_read << " points ("
            << (points_to_read * sizeof(FlightPoint<4>)) / (1024 * 1024) << " MB RAM)...\n";

  points.resize(points_to_read);
  // Each record in OPS2/OPS1 is 20 bytes (16 bytes coordinates + 4 bytes flight_id)
  in.read(reinterpret_cast<char *>(points.data()), points_to_read * sizeof(FlightPoint<4>));
  if (!in) {
    std::cerr << "[Error] Failed to read full point data.\n";
    return false;
  }

  std::cout << "[Dataset Loader] Loaded " << points_to_read << " points successfully.\n\n";
  return true;
}

// ---------------------------------------------------------------------------
// Statistical Helpers
// ---------------------------------------------------------------------------
struct Stats {
  double mean{0.0};
  double median{0.0};
  double std_dev{0.0};
};

Stats compute_statistics(const std::vector<double> &values) {
  Stats st;
  if (values.empty()) return st;
  std::size_t n = values.size();
  st.mean = std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(n);

  double var_sum = 0.0;
  for (double v : values) {
    double d = v - st.mean;
    var_sum += d * d;
  }
  st.std_dev = (n > 1) ? std::sqrt(var_sum / static_cast<double>(n - 1)) : 0.0;

  std::vector<double> sorted = values;
  std::sort(sorted.begin(), sorted.end());
  st.median = (n % 2 == 0) ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0 : sorted[n / 2];
  return st;
}

Stats compute_rebuild_stats(const std::vector<std::size_t> &values) {
  std::vector<double> d_vals(values.begin(), values.end());
  return compute_statistics(d_vals);
}

std::string current_timestamp() {
  auto now = std::chrono::system_clock::now();
  auto in_time_t = std::chrono::system_clock::to_time_t(now);
  std::stringstream ss;
  ss << std::put_time(std::localtime(&in_time_t), "%Y-%m-%d %H:%M:%S");
  return ss.str();
}

void init_csv(const std::string &filepath) {
  std::ifstream check(filepath);
  if (!check.good()) {
    std::ofstream out(filepath);
    out << "Timestamp,Dataset,Dimensions,Num_Points,Input_Order,Algorithm,Iterations,"
        << "Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,Raw_Times_ms,"
        << "Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
    out.flush();
  }
}

void log_row(const std::string &filepath, const std::string &dataset,
             std::size_t dim, std::size_t num_points, const std::string &order,
             const std::string &algo, std::size_t iterations, float min_dist,
             const Stats &t_st, const std::vector<double> &raw_times,
             const Stats &r_st, const std::vector<std::size_t> &raw_rebuilds) {
  std::ofstream out(filepath, std::ios::app);
  if (!out.is_open()) return;

  std::ostringstream time_ss;
  time_ss << "\"[";
  for (std::size_t i = 0; i < raw_times.size(); ++i) {
    time_ss << std::fixed << std::setprecision(3) << raw_times[i];
    if (i + 1 < raw_times.size()) time_ss << ", ";
  }
  time_ss << "]\"";

  std::ostringstream reb_ss;
  reb_ss << "\"[";
  for (std::size_t i = 0; i < raw_rebuilds.size(); ++i) {
    reb_ss << raw_rebuilds[i];
    if (i + 1 < raw_rebuilds.size()) reb_ss << ", ";
  }
  reb_ss << "]\"";

  out << current_timestamp() << ","
      << dataset << ","
      << dim << ","
      << num_points << ","
      << order << ","
      << algo << ","
      << iterations << ","
      << std::fixed << std::setprecision(6) << min_dist << ","
      << std::setprecision(3) << t_st.mean << ","
      << t_st.median << ","
      << t_st.std_dev << ","
      << time_ss.str() << ","
      << std::setprecision(2) << r_st.mean << ","
      << r_st.median << ","
      << r_st.std_dev << ","
      << reb_ss.str() << "\n";
  out.flush();
}

// ---------------------------------------------------------------------------
// Benchmark Execution per Scale
// ---------------------------------------------------------------------------
struct BenchmarkRunResult {
  double mean_time_ms{0.0};
  double mean_rebuilds{0.0};
  float min_distance{0.0f};
};

BenchmarkRunResult run_scenario(const std::vector<FlightPoint<4>> &source_points,
                                std::size_t count,
                                bool is_randomized,
                                std::size_t iterations,
                                std::uint64_t base_seed,
                                float min_separation,
                                const std::string &csv_file,
                                const std::string &order_name,
                                const std::string &algo_name) {
  std::vector<double> times_ms;
  std::vector<std::size_t> rebuilds;
  float best_min_dist = std::numeric_limits<float>::infinity();

  times_ms.reserve(iterations);
  rebuilds.reserve(iterations);

  std::vector<FlightPoint<4>> run_buffer;
  if (is_randomized) {
    run_buffer.resize(count);
  }

  for (std::size_t iter = 0; iter < iterations; ++iter) {
    std::size_t reb_count = 0;
    float dist = 0.0f;
    double dur_ms = 0.0;

    if (!is_randomized) {
      // Deterministic: Contiguous sequential access through real flight trajectories
      std::span<const FlightPoint<4>> slice(source_points.data(), count);
      auto t_start = std::chrono::high_resolution_clock::now();
      dist = find_min_dist_flight_grid<4>(slice, min_separation, &reb_count);
      auto t_end = std::chrono::high_resolution_clock::now();
      dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    } else {
      // Randomized: Uniform Fisher-Yates shuffle directly in memory
      std::copy(source_points.begin(), source_points.begin() + count, run_buffer.begin());
      std::mt19937_64 rng(base_seed + iter * 7919 + 1337);
      std::shuffle(run_buffer.begin(), run_buffer.end(), rng);

      // Core grid timer starts strictly after shuffle and copy
      std::span<const FlightPoint<4>> slice(run_buffer.data(), count);
      auto t_start = std::chrono::high_resolution_clock::now();
      dist = find_min_dist_flight_grid<4>(slice, min_separation, &reb_count);
      auto t_end = std::chrono::high_resolution_clock::now();
      dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    }

    times_ms.push_back(dur_ms);
    rebuilds.push_back(reb_count);
    best_min_dist = std::min(best_min_dist, dist);
  }

  Stats t_st = compute_statistics(times_ms);
  Stats r_st = compute_rebuild_stats(rebuilds);

  log_row(csv_file, "OpenSky_Real_Flight", 4, count, order_name, algo_name,
          iterations, best_min_dist, t_st, times_ms, r_st, rebuilds);

  return BenchmarkRunResult{t_st.mean, r_st.mean, best_min_dist};
}

// ---------------------------------------------------------------------------
// CLI Parser & Main
// ---------------------------------------------------------------------------
int main(int argc, char *argv[]) {
  std::cout << "\n================================================================================\n";
  std::cout << "   OPENSKY REAL-WORLD 4D CACHE-MISS BENCHMARK (L3 CACHE CLIFF PROFILER)\n";
  std::cout << "================================================================================\n";

  std::string binary_path = "opensky_5M_4d.bin";
  std::string output_csv = "cache_benchmark_opensky_results.csv";
  std::size_t iterations = 10;
  float min_separation = 0.05f;

  std::vector<std::size_t> sizes = {
      1000, 5000, 10000, 50000, 100000,
      500000, 1000000, 1500000, 2000000, 3000000, 5000000
  };

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if ((arg == "--bin" || arg == "-b") && i + 1 < argc) {
      binary_path = argv[++i];
    } else if ((arg == "--iterations" || arg == "-i") && i + 1 < argc) {
      iterations = std::stoull(argv[++i]);
    } else if ((arg == "--output" || arg == "-o") && i + 1 < argc) {
      output_csv = argv[++i];
    } else if ((arg == "--min-separation") && i + 1 < argc) {
      min_separation = std::stof(argv[++i]);
    } else if (arg == "--sizes" && i + 1 < argc) {
      sizes.clear();
      std::stringstream ss(argv[++i]);
      std::string item;
      while (std::getline(ss, item, ',')) {
        if (!item.empty()) sizes.push_back(std::stoull(item));
      }
    } else if (arg == "--help" || arg == "-h") {
      std::cout << "Usage: " << argv[0] << " [options]\n\n"
                << "Options:\n"
                << "  --bin, -b <path>          Path to OpenSky 4D binary file (default: opensky_5M_4d.bin)\n"
                << "  --iterations, -i <num>    Iterations per scale (default: 10)\n"
                << "  --output, -o <file>       Output CSV filepath (default: cache_benchmark_opensky_results.csv)\n"
                << "  --min-separation <meters> Minimum physical aircraft separation filter (default: 0.05)\n"
                << "  --sizes <N1,N2,...>       Comma-separated list of N values\n"
                << "  --help, -h                Show this help message\n";
      return 0;
    }
  }

  // Check fallback paths for binary file
  if (!std::ifstream(binary_path).good()) {
    if (std::ifstream("../" + binary_path).good()) {
      binary_path = "../" + binary_path;
    } else if (std::ifstream("../opensky_100m/data/opensky_3days_100M_4d.bin").good()) {
      binary_path = "../opensky_100m/data/opensky_3days_100M_4d.bin";
    } else if (std::ifstream("opensky_100m/data/opensky_3days_100M_4d.bin").good()) {
      binary_path = "opensky_100m/data/opensky_3days_100M_4d.bin";
    }
  }

  std::size_t max_req_n = 0;
  for (auto s : sizes) max_req_n = std::max(max_req_n, s);

  std::cout << "  OpenSky Binary File  : " << binary_path << "\n";
  std::cout << "  Iterations per scale : " << iterations << "\n";
  std::cout << "  Min Separation Filter: " << min_separation << " m\n";
  std::cout << "  Output CSV log       : " << output_csv << "\n";
  std::cout << "  Point Scales (N)     : ";
  for (std::size_t i = 0; i < sizes.size(); ++i) {
    if (sizes[i] >= 1000000) {
      std::cout << std::fixed << std::setprecision(1) << sizes[i] / 1e6 << "M";
    } else {
      std::cout << sizes[i] / 1000 << "k";
    }
    if (i + 1 < sizes.size()) std::cout << ", ";
  }
  std::cout << " (" << sizes.size() << " scales total)\n";
  std::cout << "================================================================================\n\n";

  std::vector<FlightPoint<4>> points;
  if (!load_flight_points(binary_path, points, max_req_n)) {
    return 1;
  }

  // Filter scales to only those available in points
  std::vector<std::size_t> valid_sizes;
  for (auto s : sizes) {
    if (s <= points.size()) {
      valid_sizes.push_back(s);
    } else {
      std::cout << "[Warning] Skipping N=" << s << " (only " << points.size() << " points loaded)\n";
    }
  }

  init_csv(output_csv);

  std::cout << std::left << std::setw(10) << "Scale N"
            << std::right << std::setw(14) << "Point RAM (MB)"
            << std::setw(15) << "Det Time (ms)"
            << std::setw(15) << "Rand Time (ms)"
            << std::setw(14) << "Speedup (x)"
            << std::setw(16) << "Advantage"
            << std::setw(12) << "Det Reb"
            << std::setw(12) << "Rand Reb"
            << "\n";
  std::cout << std::string(108, '-') << "\n";

  auto bench_start = std::chrono::steady_clock::now();

  for (std::size_t idx = 0; idx < valid_sizes.size(); ++idx) {
    std::size_t N = valid_sizes[idx];
    double mem_mb = (N * sizeof(FlightPoint<4>)) / (1024.0 * 1024.0);
    std::uint64_t scale_seed = 42000 + idx * 31337;

    // Run Deterministic Grid (Real flight trajectory continuity)
    auto det_res = run_scenario(points, N, false, iterations, scale_seed, min_separation,
                                output_csv, "Original", "Deterministic Grid");

    // Run Randomized Grid (Shuffled permutation)
    auto rand_res = run_scenario(points, N, true, iterations, scale_seed, min_separation,
                                 output_csv, "Original", "Randomized Grid");

    double speedup = (rand_res.mean_time_ms > 0) ? (det_res.mean_time_ms / rand_res.mean_time_ms) : 1.0;
    std::string winner = (speedup > 1.005) ? "RANDOMIZED" : ((speedup < 0.995) ? "DETERMINISTIC" : "PARITY");

    std::string scale_str = (N >= 1e6) ? (std::to_string(N / 1000000) + (N % 1000000 != 0 ? ".5M" : "M"))
                                       : (std::to_string(N / 1000) + "k");

    std::cout << std::left << std::setw(10) << scale_str
              << std::right << std::fixed << std::setprecision(1) << std::setw(14) << mem_mb
              << std::setprecision(2) << std::setw(15) << det_res.mean_time_ms
              << std::setprecision(2) << std::setw(15) << rand_res.mean_time_ms
              << std::setprecision(3) << std::setw(14) << speedup
              << std::setw(16) << winner
              << std::setprecision(1) << std::setw(12) << det_res.mean_rebuilds
              << std::setprecision(1) << std::setw(12) << rand_res.mean_rebuilds
              << std::endl;
  }

  auto bench_end = std::chrono::steady_clock::now();
  double total_sec = std::chrono::duration<double>(bench_end - bench_start).count();

  std::cout << std::string(108, '=') << "\n";
  std::cout << " BENCHMARK COMPLETE! Total Elapsed Time: "
            << std::fixed << std::setprecision(1) << total_sec << " s ("
            << total_sec / 60.0 << " min)\n";
  std::cout << " Results saved and flushed to: " << output_csv << "\n";
  std::cout << " To visualize with plots:\n";
  std::cout << "   python3 ../analyzer/run_analyzer.py " << output_csv << "\n";
  std::cout << "================================================================================\n\n";

  return 0;
}
