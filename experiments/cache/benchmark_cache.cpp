#include <algorithm>
#include <chrono>
#include <iostream>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include "../../core/closest_pair.h"
#include "../../core/metrics_logger.h"
#include "../../core/space.h"

using namespace core;

int main(int argc, char *argv[]) {
  std::string tag = get_timestamp_file_tag();
  std::string prefix = (!std::filesystem::exists("storage") && std::filesystem::exists("../storage")) ? "../" : "";
  std::string run_csv_path = prefix + "storage/results/cache/cache_benchmark_" + tag + ".csv";

  std::size_t num_points = 100000;
  int iterations = 5;

  if (argc > 1) {
    num_points = std::stoull(argv[1]);
  }
  if (argc > 2) {
    iterations = std::stoi(argv[2]);
  }

  std::cout << "=================================================================\n";
  std::cout << "  ND Closest Pair: Cache Locality & Spatial Memory Benchmark\n";
  std::cout << "  Points: " << num_points << " (4D) | Iterations: " << iterations << "\n";
  std::cout << "=================================================================\n";

  auto space = Space<4>::get_or_create("uniform", num_points);

  // Strategy A: Contiguous sequential
  std::vector<double> seq_times;
  std::vector<std::size_t> seq_rebuilds;
  for (int it = 0; it < iterations; ++it) {
    auto res = find_closest_pair_deterministic<4>(std::span<const Point<4>>(space.points));
    seq_times.push_back(res.execution_time_ms);
    seq_rebuilds.push_back(res.rebuild_count);
  }

  MetricsLogger::log_record(run_csv_path, "CacheBenchmark", "Uniform4D", 4,
                            num_points, "ContiguousSequential", "Deterministic Grid",
                            iterations, 0.0f, seq_times, seq_rebuilds,
                            "{\"strategy\": \"sequential_contiguous\"}");

  // Strategy B: Pre-shuffled contiguous (hardware prefetch friendly sequential walk of random points)
  auto shuffled_space = space;
  std::mt19937_64 g(12345);
  std::shuffle(shuffled_space.points.begin(), shuffled_space.points.end(), g);

  std::vector<double> shuf_times;
  std::vector<std::size_t> shuf_rebuilds;
  for (int it = 0; it < iterations; ++it) {
    auto res = find_closest_pair_deterministic<4>(std::span<const Point<4>>(shuffled_space.points));
    shuf_times.push_back(res.execution_time_ms);
    shuf_rebuilds.push_back(res.rebuild_count);
  }

  MetricsLogger::log_record(run_csv_path, "CacheBenchmark", "Uniform4D", 4,
                            num_points, "PreShuffledContiguous", "Deterministic Grid",
                            iterations, 0.0f, shuf_times, shuf_rebuilds,
                            "{\"strategy\": \"preshuffled_contiguous\"}");

  SummaryStats seq_s = compute_stats(seq_times);
  SummaryStats shuf_s = compute_stats(shuf_times);

  std::cout << "  1. Contiguous Sequential Mean Time : " << seq_s.mean << " ms\n";
  std::cout << "  2. Pre-Shuffled Contiguous Mean Time: " << shuf_s.mean << " ms\n";

  std::cout << "\nCache locality benchmark finished! Logged to: " << run_csv_path << "\n";
  return 0;
}
