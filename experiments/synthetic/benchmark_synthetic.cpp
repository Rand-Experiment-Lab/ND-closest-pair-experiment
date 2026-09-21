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

  auto serialize_vec = [](const auto &vec) {
    std::string s = "[";
    for (std::size_t k = 0; k < vec.size(); ++k) {
      s += std::to_string(vec[k]);
      if (k + 1 < vec.size()) s += ", ";
    }
    return s + "]";
  };

  // 1. Deterministic Solver
  std::vector<double> det_times;
  std::vector<std::size_t> det_rebuilds;
  std::vector<std::size_t> det_rebuild_works;
  std::vector<std::size_t> det_non_empty_cells;
  std::vector<std::size_t> det_dist_evals;
  std::vector<std::size_t> det_peak_cells;
  float det_min_dist = 0.0f;

  for (int it = 0; it < g_config.iterations; ++it) {
    auto res = find_closest_pair_deterministic<Dim>(std::span<const Point<Dim>>(space.points));
    det_times.push_back(res.execution_time_ms);
    det_rebuilds.push_back(res.rebuild_count);
    det_rebuild_works.push_back(res.rebuild_work);
    det_non_empty_cells.push_back(res.non_empty_cells_hit);
    det_dist_evals.push_back(res.distance_evals);
    det_peak_cells.push_back(res.peak_occupied_cells);
    det_min_dist = res.min_distance;
  }

  double det_mean_work = std::accumulate(det_rebuild_works.begin(), det_rebuild_works.end(), 0.0) / g_config.iterations;
  double det_mean_hits = std::accumulate(det_non_empty_cells.begin(), det_non_empty_cells.end(), 0.0) / g_config.iterations;
  double det_mean_evals = std::accumulate(det_dist_evals.begin(), det_dist_evals.end(), 0.0) / g_config.iterations;
  double det_mean_peak = std::accumulate(det_peak_cells.begin(), det_peak_cells.end(), 0.0) / g_config.iterations;

  std::string det_extra_json = "{\"scenario\": \"" + scenario_name + "\"" +
                               ", \"custom_meta\": " + (extra_json.empty() ? "{}" : extra_json) +
                               ", \"mean_rebuild_work\": " + std::to_string(det_mean_work) +
                               ", \"mean_cell_hits\": " + std::to_string(det_mean_hits) +
                               ", \"mean_dist_evals\": " + std::to_string(det_mean_evals) +
                               ", \"mean_peak_cells\": " + std::to_string(det_mean_peak) +
                               ", \"raw_rebuild_works\": " + serialize_vec(det_rebuild_works) +
                               ", \"raw_cell_hits\": " + serialize_vec(det_non_empty_cells) +
                               ", \"raw_dist_evals\": " + serialize_vec(det_dist_evals) + "}";

  MetricsLogger::log_record(g_config.run_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Deterministic Grid",
                            g_config.iterations, det_min_dist, det_times,
                            det_rebuilds, det_extra_json);
  MetricsLogger::log_record(g_config.master_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Deterministic Grid",
                            g_config.iterations, det_min_dist, det_times,
                            det_rebuilds, det_extra_json);

  // 2. Randomized Solver
  std::vector<double> rand_times;
  std::vector<std::size_t> rand_rebuilds;
  std::vector<std::size_t> rand_rebuild_works;
  std::vector<std::size_t> rand_non_empty_cells;
  std::vector<std::size_t> rand_dist_evals;
  std::vector<std::size_t> rand_peak_cells;
  std::vector<double> rand_shuffle_times;
  float rand_min_dist = 0.0f;

  for (int it = 0; it < g_config.iterations; ++it) {
    auto res = find_closest_pair_randomized<Dim>(space.points);
    rand_times.push_back(res.execution_time_ms);
    rand_rebuilds.push_back(res.rebuild_count);
    rand_rebuild_works.push_back(res.rebuild_work);
    rand_non_empty_cells.push_back(res.non_empty_cells_hit);
    rand_dist_evals.push_back(res.distance_evals);
    rand_peak_cells.push_back(res.peak_occupied_cells);
    rand_shuffle_times.push_back(res.shuffle_time_ms);
    rand_min_dist = res.min_distance;
  }

  double rand_mean_work = std::accumulate(rand_rebuild_works.begin(), rand_rebuild_works.end(), 0.0) / g_config.iterations;
  double rand_mean_hits = std::accumulate(rand_non_empty_cells.begin(), rand_non_empty_cells.end(), 0.0) / g_config.iterations;
  double rand_mean_evals = std::accumulate(rand_dist_evals.begin(), rand_dist_evals.end(), 0.0) / g_config.iterations;
  double rand_mean_peak = std::accumulate(rand_peak_cells.begin(), rand_peak_cells.end(), 0.0) / g_config.iterations;
  double rand_mean_shuffle = std::accumulate(rand_shuffle_times.begin(), rand_shuffle_times.end(), 0.0) / g_config.iterations;

  std::string rand_extra_json = "{\"scenario\": \"" + scenario_name + "\"" +
                                ", \"custom_meta\": " + (extra_json.empty() ? "{}" : extra_json) +
                                ", \"mean_rebuild_work\": " + std::to_string(rand_mean_work) +
                                ", \"mean_cell_hits\": " + std::to_string(rand_mean_hits) +
                                ", \"mean_dist_evals\": " + std::to_string(rand_mean_evals) +
                                ", \"mean_peak_cells\": " + std::to_string(rand_mean_peak) +
                                ", \"mean_shuffle_ms\": " + std::to_string(rand_mean_shuffle) +
                                ", \"raw_rebuild_works\": " + serialize_vec(rand_rebuild_works) +
                                ", \"raw_cell_hits\": " + serialize_vec(rand_non_empty_cells) +
                                ", \"raw_dist_evals\": " + serialize_vec(rand_dist_evals) +
                                ", \"raw_shuffle_ms\": " + serialize_vec(rand_shuffle_times) + "}";

  MetricsLogger::log_record(g_config.run_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Randomized Grid",
                            g_config.iterations, rand_min_dist, rand_times,
                            rand_rebuilds, rand_extra_json);
  MetricsLogger::log_record(g_config.master_csv_path, "Synthetic", scenario_name, Dim,
                            num_points, input_order, "Randomized Grid",
                            g_config.iterations, rand_min_dist, rand_times,
                            rand_rebuilds, rand_extra_json);

  SummaryStats det_s = compute_stats(det_times);
  SummaryStats rand_s = compute_stats(rand_times);

  double speedup = (rand_s.mean > 0.0) ? (det_s.mean / rand_s.mean) : 1.0;
  std::cout << "      Det Mean: " << std::fixed << std::setprecision(3) << det_s.mean
            << " ms | Rand Mean: " << rand_s.mean << " ms | Speedup: "
            << std::setprecision(2) << speedup << "x\n";
  std::cout << "      [Det] Rebuilds: " << det_rebuilds.back() << ", Work: " << det_rebuild_works.back()
            << ", PeakCells: " << det_peak_cells.back() << "\n";
  std::cout << "      [Rand] Mean Rebuilds: " << std::fixed << std::setprecision(1)
            << (std::accumulate(rand_rebuilds.begin(), rand_rebuilds.end(), 0.0)/g_config.iterations)
            << ", Mean Work: " << rand_mean_work << ", PeakCells: " << rand_mean_peak
            << ", Shuffle: " << rand_mean_shuffle << " ms\n";
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
  std::string prefix = (!std::filesystem::exists("storage") && std::filesystem::exists("../storage")) ? "../" : "";
  g_config.master_csv_path = prefix + "storage/results/synthetic/master_synthetic.csv";
  g_config.run_csv_path = prefix + "storage/results/synthetic/synthetic_benchmark_" + tag + ".csv";

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
