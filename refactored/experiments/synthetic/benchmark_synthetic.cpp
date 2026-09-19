#include <iostream>
#include <string>
#include <vector>

#include "../../core/closest_pair.h"
#include "../../core/metrics_logger.h"
#include "../../core/space.h"

using namespace core;

struct BenchmarkRunConfig {
  std::string run_csv_path;
  std::string master_csv_path = "storage/results/synthetic/master_synthetic.csv";
  int iterations = 5;
  bool quick_mode = false;
};

static BenchmarkRunConfig g_config;

template <std::size_t Dim>
void run_synthetic_scenario(const std::string &scenario_name,
                            const std::string &input_order,
                            const Space<Dim> &space,
                            std::size_t num_points,
                            const std::string &extra_json = "{}") {
  std::cout << "  > Testing [" << scenario_name << "] Order: " << input_order << " ...\n";

  // 1. Deterministic Solver
  std::vector<double> det_times;
  std::vector<std::size_t> det_rebuilds;
  float det_min_dist = 0.0f;

  for (int it = 0; it < g_config.iterations; ++it) {
    auto res = find_closest_pair_deterministic<Dim>(std::span<const Point<Dim>>(space.points));
    det_times.push_back(res.execution_time_ms);
    det_rebuilds.push_back(res.rebuild_count);
    det_min_dist = res.min_distance;
  }

  MetricsLogger::log_record(g_config.run_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Deterministic Grid",
                            g_config.iterations, det_min_dist, det_times,
                            det_rebuilds, extra_json);
  MetricsLogger::log_record(g_config.master_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Deterministic Grid",
                            g_config.iterations, det_min_dist, det_times,
                            det_rebuilds, extra_json);

  // 2. Randomized Solver
  std::vector<double> rand_times;
  std::vector<std::size_t> rand_rebuilds;
  float rand_min_dist = 0.0f;

  for (int it = 0; it < g_config.iterations; ++it) {
    auto res = find_closest_pair_randomized<Dim>(space.points);
    rand_times.push_back(res.execution_time_ms);
    rand_rebuilds.push_back(res.rebuild_count);
    rand_min_dist = res.min_distance;
  }

  MetricsLogger::log_record(g_config.run_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Randomized Grid",
                            g_config.iterations, rand_min_dist, rand_times,
                            rand_rebuilds, extra_json);
  MetricsLogger::log_record(g_config.master_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Randomized Grid",
                            g_config.iterations, rand_min_dist, rand_times,
                            rand_rebuilds, extra_json);

  SummaryStats det_s = compute_stats(det_times);
  SummaryStats rand_s = compute_stats(rand_times);

  double speedup = (rand_s.mean > 0.0) ? (det_s.mean / rand_s.mean) : 1.0;
  std::cout << "      Det Mean: " << std::fixed << std::setprecision(3) << det_s.mean
            << " ms | Rand Mean: " << rand_s.mean << " ms | Speedup: "
            << std::setprecision(2) << speedup << "x\n";
}

template <std::size_t Dim>
void run_all_tests_for_dim(const std::vector<std::size_t> &point_counts) {
  std::cout << "\n" << std::string(80, '=') << "\n";
  std::cout << "  DIMENSION " << Dim << "D SYNTHETIC EXPERIMENTS\n";
  std::cout << std::string(80, '=') << "\n";

  for (std::size_t n : point_counts) {
    std::cout << "\n-- Points: " << n << " --\n";

    // Scenario 1: Normal Uniform (Original Order)
    auto norm_space = Space<Dim>::get_or_create("uniform", n);
    run_synthetic_scenario<Dim>("Normal", "Original", norm_space, n);

    // Scenario 2: Normal Uniform (Sorted X-Axis)
    norm_space.sort_points(SortStrategy::AxisAscending, 0);
    run_synthetic_scenario<Dim>("Normal", "Sorted_X_Axis", norm_space, n);

    // Scenario 3: Adversarial "Ladder of Pairs" (forces O(N^2) rebuilds)
    std::size_t adv_n = std::min<std::size_t>(n, 25000); // capped to avoid hours of stalling
    if (g_config.quick_mode) adv_n = std::min<std::size_t>(adv_n, 2000);

    auto adv_space = Space<Dim>::get_or_create("adversarial", adv_n);
    run_synthetic_scenario<Dim>("Adversarial", "Ladder_of_Pairs", adv_space, adv_n,
                                "{\"generator\": \"ladder_of_pairs\"}");
  }
}

int main(int argc, char *argv[]) {
  std::string tag = get_timestamp_file_tag();
  g_config.run_csv_path = "storage/results/synthetic/synthetic_benchmark_" + tag + ".csv";

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--quick") {
      g_config.quick_mode = true;
      g_config.iterations = 2;
    } else if (arg == "--iterations" && i + 1 < argc) {
      g_config.iterations = std::max(1, std::stoi(argv[++i]));
    }
  }

  std::cout << "=================================================================\n";
  std::cout << "  ND Closest Pair: Unified Synthetic Benchmark Engine\n";
  std::cout << "  Writing to: " << g_config.run_csv_path << "\n";
  std::cout << "  Iterations: " << g_config.iterations << "\n";
  std::cout << "=================================================================\n";

  std::vector<std::size_t> counts;
  if (g_config.quick_mode) {
    counts = {2000};
  } else {
    counts = {10000, 50000, 100000};
  }

  run_all_tests_for_dim<2>(counts);
  run_all_tests_for_dim<3>(counts);
  run_all_tests_for_dim<4>(counts);
  run_all_tests_for_dim<5>(counts);
  run_all_tests_for_dim<7>(counts);
  run_all_tests_for_dim<9>(counts);

  std::cout << "\nAll synthetic benchmarks completed successfully!\n";
  return 0;
}
