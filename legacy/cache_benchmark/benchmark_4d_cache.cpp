#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "../closest_pair.h"
#include "../space.h"

namespace fs = std::filesystem;

// ---------------------------------------------------------------------------
// Statistical Helpers
// ---------------------------------------------------------------------------
struct Stats {
  double mean{0.0};
  double median{0.0};
  double std_dev{0.0};
  double min_val{0.0};
  double max_val{0.0};
};

Stats compute_statistics(std::vector<double> vals) {
  Stats s;
  if (vals.empty()) return s;
  std::sort(vals.begin(), vals.end());
  s.min_val = vals.front();
  s.max_val = vals.back();
  s.median = vals[vals.size() / 2];

  double sum = std::accumulate(vals.begin(), vals.end(), 0.0);
  s.mean = sum / vals.size();

  double sq_diff = 0.0;
  for (double v : vals) {
    sq_diff += (v - s.mean) * (v - s.mean);
  }
  s.std_dev = (vals.size() > 1) ? std::sqrt(sq_diff / (vals.size() - 1)) : 0.0;
  return s;
}

Stats compute_rebuild_stats(const std::vector<std::size_t> &rebuilds) {
  std::vector<double> d_reb(rebuilds.begin(), rebuilds.end());
  return compute_statistics(d_reb);
}

std::string current_timestamp() {
  std::time_t t = std::time(nullptr);
  char buf[100];
  if (std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&t))) {
    return buf;
  }
  return "Unknown";
}

std::string current_timestamp_file() {
  std::time_t t = std::time(nullptr);
  char buf[100];
  if (std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", std::localtime(&t))) {
    return buf;
  }
  return "run";
}

// ---------------------------------------------------------------------------
// CSV Logging Interface
// ---------------------------------------------------------------------------
void init_csv(const std::string &filepath) {
  fs::path p(filepath);
  if (p.has_parent_path()) {
    fs::create_directories(p.parent_path());
  }
  bool write_hdr = !fs::exists(filepath) || (fs::file_size(filepath) == 0);
  if (write_hdr) {
    std::ofstream out(filepath, std::ios::out);
    out << "Timestamp,Space_Type,Dimensions,Num_Points,Input_Order,Algorithm,"
           "Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,"
           "Raw_Times_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
    out.flush();
  }
}

void log_row(const std::string &filepath, const std::string &space_type,
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
      << space_type << ","
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
// Synthetic 4D Uniform Generator
// ---------------------------------------------------------------------------
std::vector<Point<4>> generate_4d_uniform(std::size_t count, std::uint64_t seed = 42) {
  std::vector<Point<4>> pts(count);
  std::mt19937_64 gen(seed);
  std::uniform_real_distribution<float> dist(0.0f, 1000.0f);

  for (auto &p : pts) {
    for (std::size_t d = 0; d < 4; ++d) {
      p.coordinates[d] = dist(gen);
    }
  }
  return pts;
}

// ---------------------------------------------------------------------------
// Benchmark Execution per Scale
// ---------------------------------------------------------------------------
struct BenchmarkRunResult {
  double mean_time_ms{0.0};
  double mean_rebuilds{0.0};
  float min_distance{0.0f};
};

BenchmarkRunResult run_scenario(const std::vector<Point<4>> &points,
                                bool is_randomized,
                                std::size_t iterations,
                                std::uint64_t base_seed,
                                const std::string &csv_file,
                                const std::string &order_name,
                                const std::string &algo_name) {
  std::vector<double> times_ms;
  std::vector<std::size_t> rebuilds;
  float best_min_dist = std::numeric_limits<float>::infinity();

  times_ms.reserve(iterations);
  rebuilds.reserve(iterations);

  std::vector<Point<4>> run_buffer;
  if (is_randomized) {
    run_buffer.resize(points.size());
  }

  for (std::size_t iter = 0; iter < iterations; ++iter) {
    std::size_t reb_count = 0;
    float dist = 0.0f;
    double dur_ms = 0.0;

    if (!is_randomized) {
      // Deterministic: Contiguous sequential access through points
      auto t_start = std::chrono::high_resolution_clock::now();
      dist = find_min_dist_grid_based<4>(std::span<const Point<4>>(points), false, &reb_count);
      auto t_end = std::chrono::high_resolution_clock::now();
      dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    } else {
      // Randomized: Uniform Fisher-Yates shuffle directly in memory
      std::copy(points.begin(), points.end(), run_buffer.begin());
      std::mt19937_64 rng(base_seed + iter * 7919 + 1337);
      std::shuffle(run_buffer.begin(), run_buffer.end(), rng);

      // Core grid timer starts strictly after shuffle and copy
      auto t_start = std::chrono::high_resolution_clock::now();
      dist = find_min_dist_grid_based<4>(std::span<const Point<4>>(run_buffer), false, &reb_count);
      auto t_end = std::chrono::high_resolution_clock::now();
      dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    }

    times_ms.push_back(dur_ms);
    rebuilds.push_back(reb_count);
    best_min_dist = std::min(best_min_dist, dist);
  }

  Stats t_st = compute_statistics(times_ms);
  Stats r_st = compute_rebuild_stats(rebuilds);

  log_row(csv_file, "Uniform_Normal", 4, points.size(), order_name, algo_name,
          iterations, best_min_dist, t_st, times_ms, r_st, rebuilds);

  return BenchmarkRunResult{t_st.mean, r_st.mean, best_min_dist};
}

// ---------------------------------------------------------------------------
// CLI Parser & Main
// ---------------------------------------------------------------------------
int main(int argc, char *argv[]) {
  std::cout << "\n================================================================================\n";
  std::cout << "      4D CACHE-TRANSITION BENCHMARK ORCHESTRATOR (STANDALONE)                   \n";
  std::cout << "      Testing Deterministic vs. Randomized Grid under L1/L2/L3 Memory Scaling   \n";
  std::cout << "================================================================================\n";

  // Default configuration
  std::size_t iterations = 10;
  std::string output_csv = "results/cache_benchmark_4d_" + current_timestamp_file() + ".csv";
  std::vector<std::size_t> sizes = {
      1000, 5000, 10000, 50000, 100000, 500000,
      1000000, 1500000, 2000000, 3000000, 5000000
  };

  // Parse positional or flag-based arguments
  // Usage 1: ./benchmark_4d_cache [iterations] [output_csv] [sizes_comma_separated]
  // Usage 2: ./benchmark_4d_cache --iterations 10 --sizes 1000,5000,... --output file.csv
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--iterations" || arg == "-i") {
      if (i + 1 < argc) iterations = std::stoull(argv[++i]);
    } else if (arg == "--output" || arg == "-o") {
      if (i + 1 < argc) output_csv = argv[++i];
    } else if (arg == "--sizes" || arg == "-s") {
      if (i + 1 < argc) {
        sizes.clear();
        std::stringstream ss(argv[++i]);
        std::string item;
        while (std::getline(ss, item, ',')) {
          if (!item.empty()) sizes.push_back(std::stoull(item));
        }
      }
    } else if (arg == "--help" || arg == "-h") {
      std::cout << "Usage: " << argv[0] << " [iterations] [output_csv] [comma_separated_sizes]\n"
                << "   or: " << argv[0] << " --iterations 10 --output results.csv --sizes 1000,5000,...\n\n"
                << "Defaults:\n"
                << "  Iterations : 10\n"
                << "  Output CSV : " << output_csv << "\n"
                << "  Sizes      : 1k, 5k, 10k, 50k, 100k, 500k, 1.0M, 1.5M, 2.0M, 3.0M, 5.0M\n";
      return 0;
    } else {
      // Positional args fallback
      if (i == 1) {
        iterations = std::stoull(arg);
      } else if (i == 2) {
        output_csv = arg;
      } else if (i == 3) {
        sizes.clear();
        std::stringstream ss(arg);
        std::string item;
        while (std::getline(ss, item, ',')) {
          if (!item.empty()) sizes.push_back(std::stoull(item));
        }
      }
    }
  }

  std::sort(sizes.begin(), sizes.end());

  std::cout << "  Iterations per scale : " << iterations << "\n";
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

  init_csv(output_csv);

  std::cout << std::left << std::setw(10) << "Scale N"
            << std::right << std::setw(14) << "Memory (MB)"
            << std::setw(15) << "Det Time (ms)"
            << std::setw(15) << "Rand Time (ms)"
            << std::setw(14) << "Speedup (x)"
            << std::setw(16) << "Advantage"
            << std::setw(12) << "Det Reb"
            << std::setw(12) << "Rand Reb"
            << "\n";
  std::cout << std::string(108, '-') << "\n";

  auto bench_start = std::chrono::steady_clock::now();

  for (std::size_t idx = 0; idx < sizes.size(); ++idx) {
    std::size_t N = sizes[idx];
    double mem_mb = (N * sizeof(Point<4>)) / (1024.0 * 1024.0);

    // Generate fresh uniform points
    std::uint64_t scale_seed = 42000 + idx * 31337;
    auto points = generate_4d_uniform(N, scale_seed);

    // Run Deterministic Grid (Original Order)
    auto det_res = run_scenario(points, false, iterations, scale_seed, output_csv,
                                "Original", "Deterministic Grid");

    // Run Randomized Grid (Shuffled Permutations)
    auto rand_res = run_scenario(points, true, iterations, scale_seed, output_csv,
                                 "Original", "Randomized Grid");

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
  std::cout << "   python3 analyzer/run_analyzer.py " << output_csv << "\n";
  std::cout << "================================================================================\n\n";

  return 0;
}
