#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

#include "../../adapters/opensky/opensky_adapter.h"
#include "../../core/closest_pair.h"
#include "../../core/metrics_logger.h"
#include "../../core/space.h"

using namespace core;
using namespace adapters::opensky;

struct Config {
  std::string suite = "dim";
  int iterations = 30;
  int min_dim = 2;
  int max_dim = 11;
  std::size_t dim_n = 100000;
  std::string tag = "local";
  std::string opensky_dir = "storage/datasets/opensky";
  std::string output_dir = "storage/results/rebuild_work";
  std::string run_csv_path;
  std::string master_csv_path;
};

static Config g_cfg;

static std::string serialize_vec(const auto &vec) {
  std::string s = "[";
  for (std::size_t k = 0; k < vec.size(); ++k) {
    s += std::to_string(vec[k]);
    if (k + 1 < vec.size()) s += ", ";
  }
  return s + "]";
}

// -----------------------------------------------------------------------------
// Core Evaluator for a single Experiment Unit
// -----------------------------------------------------------------------------
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
void evaluate_unit(const std::string &suite_name,
                   const std::string &dataset_name,
                   const std::vector<PointType> &points,
                   Filter filter = Filter{}) {
  const std::size_t n = points.size();
  std::cout << "\n=================================================================\n";
  std::cout << " [Unit] Suite: " << suite_name << " | Dataset: " << dataset_name
            << " | Dim: " << Dim << "D | Points: " << n
            << " | Iterations: " << g_cfg.iterations << "\n";
  std::cout << "=================================================================\n";

  // 1. Deterministic Pass (1 reference run for comparison)
  auto det_res = find_closest_pair_deterministic<Dim, PointType, Filter>(
      std::span<const PointType>(points), filter);
  std::cout << "  > [Deterministic] " << std::fixed << std::setprecision(2)
            << det_res.execution_time_ms << " ms | Probe: " << det_res.probe_time_ms << " ms"
            << " | RebuildTime: " << det_res.rebuild_time_ms << " ms"
            << " | Rebuilds: " << det_res.rebuild_count
            << " | Work: " << det_res.rebuild_work << " pts\n";

  std::vector<double> det_times = {det_res.execution_time_ms};
  std::vector<std::size_t> det_rebuilds = {det_res.rebuild_count};
  std::string det_meta = "{\"suite\": \"" + suite_name + "\"" +
                         ", \"raw_rebuild_works\": [" + std::to_string(det_res.rebuild_work) + "]" +
                         ", \"raw_rebuild_counts\": [" + std::to_string(det_res.rebuild_count) + "]" +
                         ", \"raw_rebuild_times_ms\": [" + std::to_string(det_res.rebuild_time_ms) + "]" +
                         ", \"raw_probe_times_ms\": [" + std::to_string(det_res.probe_time_ms) + "]" +
                         ", \"raw_total_neighbor_probes\": [" + std::to_string(det_res.total_neighbor_probes) + "]" +
                         ", \"raw_empty_probes\": [" + std::to_string(det_res.empty_cell_probes) + "]" +
                         ", \"raw_cell_hits\": [" + std::to_string(det_res.non_empty_cells_hit) + "]" +
                         ", \"raw_dist_evals\": [" + std::to_string(det_res.distance_evals) + "]" +
                         ", \"raw_peak_cells\": [" + std::to_string(det_res.peak_occupied_cells) + "]" +
                         ", \"raw_shuffle_ms\": [0.0]}";

  MetricsLogger::log_record(g_cfg.run_csv_path, suite_name, dataset_name, Dim,
                            n, "Original", "Deterministic Grid", 1,
                            det_res.min_distance, det_times, det_rebuilds, det_meta);

  // 2. Randomized Passes (K iterations for statistical correlation)
  std::cout << "  > Running " << g_cfg.iterations << " Randomized Iterations...\n";

  std::vector<double> rand_times;
  std::vector<std::size_t> rand_rebuilds;
  std::vector<std::size_t> rand_rebuild_works;
  std::vector<double> rand_rebuild_times;
  std::vector<double> rand_probe_times;
  std::vector<std::size_t> rand_total_probes;
  std::vector<std::size_t> rand_cell_hits;
  std::vector<std::size_t> rand_dist_evals;
  std::vector<std::size_t> rand_peak_cells;
  std::vector<std::size_t> rand_empty_probes;
  std::vector<double> rand_shuffle_times;
  std::vector<double> rand_total_pipeline_times;
  float min_dist = 0.0f;

  for (int it = 0; it < g_cfg.iterations; ++it) {
    auto res = find_closest_pair_randomized<Dim, PointType, Filter>(points, filter);
    rand_times.push_back(res.execution_time_ms);
    rand_rebuilds.push_back(res.rebuild_count);
    rand_rebuild_works.push_back(res.rebuild_work);
    rand_rebuild_times.push_back(res.rebuild_time_ms);
    rand_probe_times.push_back(res.probe_time_ms);
    rand_total_probes.push_back(res.total_neighbor_probes);
    rand_cell_hits.push_back(res.non_empty_cells_hit);
    rand_dist_evals.push_back(res.distance_evals);
    rand_peak_cells.push_back(res.peak_occupied_cells);
    rand_empty_probes.push_back(res.empty_cell_probes);
    rand_shuffle_times.push_back(res.shuffle_time_ms);
    rand_total_pipeline_times.push_back(res.execution_time_ms + res.shuffle_time_ms);
    min_dist = res.min_distance;

    if ((it + 1) % 5 == 0 || it == g_cfg.iterations - 1) {
      double pct_r = (res.execution_time_ms > 0) ? (res.rebuild_time_ms / res.execution_time_ms) * 100.0 : 0.0;
      double pct_p = (res.execution_time_ms > 0) ? (res.probe_time_ms / res.execution_time_ms) * 100.0 : 0.0;
      std::cout << "    [" << (it + 1) << "/" << g_cfg.iterations << "] "
                << "Total: " << std::fixed << std::setprecision(1) << res.execution_time_ms << " ms "
                << "| Probe: " << res.probe_time_ms << " ms (" << std::setprecision(1) << pct_p << "%) "
                << "| Rebuild: " << res.rebuild_time_ms << " ms (" << std::setprecision(1) << pct_r << "%) "
                << "| Work: " << res.rebuild_work << " pts "
                << "| Rebuilds: " << res.rebuild_count << "\n" << std::flush;
    }
  }

  SummaryStats time_stats = compute_stats(rand_times);
  double mean_work = std::accumulate(rand_rebuild_works.begin(), rand_rebuild_works.end(), 0.0) / g_cfg.iterations;
  double mean_rebuilds = std::accumulate(rand_rebuilds.begin(), rand_rebuilds.end(), 0.0) / g_cfg.iterations;
  double mean_rebuild_time = std::accumulate(rand_rebuild_times.begin(), rand_rebuild_times.end(), 0.0) / g_cfg.iterations;
  double mean_probe_time = std::accumulate(rand_probe_times.begin(), rand_probe_times.end(), 0.0) / g_cfg.iterations;
  double pct_rebuild = (time_stats.mean > 0) ? (mean_rebuild_time / time_stats.mean) * 100.0 : 0.0;
  double pct_probe = (time_stats.mean > 0) ? (mean_probe_time / time_stats.mean) * 100.0 : 0.0;

  std::cout << "  > [Randomized Mean] " << std::fixed << std::setprecision(2)
            << time_stats.mean << " ± " << time_stats.std_dev << " ms\n"
            << "    ├─ Neighbor Probing : " << mean_probe_time << " ms (" << std::setprecision(1) << pct_probe << "% of runtime)"
            << " | Total Probes: " << (rand_total_probes.empty() ? 0 : rand_total_probes[0]) << "\n"
            << "    ├─ Grid Rebuilds    : " << mean_rebuild_time << " ms (" << std::setprecision(1) << pct_rebuild << "% of runtime)"
            << " | Mean Work: " << std::setprecision(0) << mean_work << " pts\n"
            << "    └─ Mean Rebuild Count: " << std::setprecision(1) << mean_rebuilds << "\n";

  std::string rand_meta = "{\"suite\": \"" + suite_name + "\"" +
                          ", \"platform\": \"" + g_cfg.tag + "\"" +
                          ", \"mean_rebuild_work\": " + std::to_string(mean_work) +
                          ", \"mean_rebuilds\": " + std::to_string(mean_rebuilds) +
                          ", \"mean_rebuild_time_ms\": " + std::to_string(mean_rebuild_time) +
                          ", \"mean_probe_time_ms\": " + std::to_string(mean_probe_time) +
                          ", \"rebuild_time_pct\": " + std::to_string(pct_rebuild) +
                          ", \"probe_time_pct\": " + std::to_string(pct_probe) +
                          ", \"raw_rebuild_works\": " + serialize_vec(rand_rebuild_works) +
                          ", \"raw_rebuild_counts\": " + serialize_vec(rand_rebuilds) +
                          ", \"raw_rebuild_times_ms\": " + serialize_vec(rand_rebuild_times) +
                          ", \"raw_probe_times_ms\": " + serialize_vec(rand_probe_times) +
                          ", \"raw_total_neighbor_probes\": " + serialize_vec(rand_total_probes) +
                          ", \"raw_empty_probes\": " + serialize_vec(rand_empty_probes) +
                          ", \"raw_cell_hits\": " + serialize_vec(rand_cell_hits) +
                          ", \"raw_dist_evals\": " + serialize_vec(rand_dist_evals) +
                          ", \"raw_peak_cells\": " + serialize_vec(rand_peak_cells) +
                          ", \"raw_shuffle_ms\": " + serialize_vec(rand_shuffle_times) +
                          ", \"raw_pipeline_times_ms\": " + serialize_vec(rand_total_pipeline_times) + "}";

  MetricsLogger::log_record(g_cfg.run_csv_path, suite_name, dataset_name, Dim,
                            n, "Randomized", "Randomized Grid", g_cfg.iterations,
                            min_dist, rand_times, rand_rebuilds, rand_meta);
  MetricsLogger::log_record(g_cfg.master_csv_path, suite_name, dataset_name, Dim,
                            n, "Randomized", "Randomized Grid", g_cfg.iterations,
                            min_dist, rand_times, rand_rebuilds, rand_meta);
}

// -----------------------------------------------------------------------------
// Suite 1: Dimension Variation (Holding N Constant, D = min_dim .. max_dim)
// -----------------------------------------------------------------------------
void run_dimension_suite() {
  std::cout << "\n#################################################################\n";
  std::cout << "  SUITE 1: CONTROLLED DIMENSION TEST (N = " << g_cfg.dim_n
            << " CONSTANT, D = " << g_cfg.min_dim << " .. " << g_cfg.max_dim << ")\n";
  std::cout << "#################################################################\n";
  const std::size_t n = g_cfg.dim_n;

  for (int d = g_cfg.min_dim; d <= g_cfg.max_dim; ++d) {
    std::string ds_name = "Synthetic_" + std::to_string(d) + "D_" + std::to_string(n / 1000) + "k";
    switch (d) {
      case 2: {
        auto space = Space<2>::get_or_create("uniform", n);
        evaluate_unit<2>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 3: {
        auto space = Space<3>::get_or_create("uniform", n);
        evaluate_unit<3>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 4: {
        auto space = Space<4>::get_or_create("uniform", n);
        evaluate_unit<4>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 5: {
        auto space = Space<5>::get_or_create("uniform", n);
        evaluate_unit<5>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 6: {
        auto space = Space<6>::get_or_create("uniform", n);
        evaluate_unit<6>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 7: {
        auto space = Space<7>::get_or_create("uniform", n);
        evaluate_unit<7>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 8: {
        auto space = Space<8>::get_or_create("uniform", n);
        evaluate_unit<8>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 9: {
        auto space = Space<9>::get_or_create("uniform", n);
        evaluate_unit<9>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 10: {
        auto space = Space<10>::get_or_create("uniform", n);
        evaluate_unit<10>("DimensionSuite", ds_name, space.points);
        break;
      }
      case 11: {
        auto space = Space<11>::get_or_create("uniform", n);
        evaluate_unit<11>("DimensionSuite", ds_name, space.points);
        break;
      }
      default:
        std::cerr << "Unsupported dimension: " << d << " (valid range: 2..11)\n";
        break;
    }
  }
}

// -----------------------------------------------------------------------------
// Suite 2: Scale Variation (Holding D = 4 Constant)
// -----------------------------------------------------------------------------
void run_scale_suite() {
  std::cout << "\n#################################################################\n";
  std::cout << "  SUITE 2: CONTROLLED SCALE TEST (D = 4 CONSTANT)\n";
  std::cout << "#################################################################\n";

  std::vector<std::size_t> counts = {10000, 50000, 100000, 500000, 1000000};
  for (std::size_t n : counts) {
    auto space = Space<4>::get_or_create("uniform", n);
    evaluate_unit<4>("ScaleSuite", "Synthetic_4D_" + std::to_string(n / 1000) + "k", space.points);
  }
}

// -----------------------------------------------------------------------------
// Suite 3: Real-World OpenSky Telemetry (D = 4, 5 Hours)
// -----------------------------------------------------------------------------
void run_real_suite() {
  std::cout << "\n#################################################################\n";
  std::cout << "  SUITE 3: REAL-WORLD OPENSKY 4D FLIGHT TELEMETRY\n";
  std::cout << "#################################################################\n";

  std::vector<std::string> files;
  std::vector<std::string> candidate_dirs = {
      g_cfg.opensky_dir,
      "../" + g_cfg.opensky_dir,
      "../../" + g_cfg.opensky_dir,
      "refactored/" + g_cfg.opensky_dir,
      "opensky_experiment/data/2019-05-27_hourly",
      "../opensky_experiment/data/2019-05-27_hourly"
  };

  for (const auto &cand : candidate_dirs) {
    if (std::filesystem::exists(cand)) {
      for (const auto &entry : std::filesystem::directory_iterator(cand)) {
        if (entry.path().extension() == ".bin") {
          files.push_back(entry.path().string());
        }
      }
      if (!files.empty()) {
        std::cout << "[OpenSky] Located dataset directory: " << cand << "\n";
        break;
      }
    }
  }
  std::sort(files.begin(), files.end());

  if (files.empty()) {
    std::cerr << "Warning: No OpenSky .bin datasets found in " << g_cfg.opensky_dir << " or fallback paths.\n";
    return;
  }

  Strategy2FlightFilter flight_filter;
  for (const auto &fp : files) {
    std::vector<FlightPoint4D> points;
    float alpha = 0.0f;
    double t_min = 0.0;
    if (!OpenSkyAdapter::load_binary_dataset(fp, points, &alpha, &t_min)) {
      continue;
    }
    std::string name = std::filesystem::path(fp).stem().string();
    evaluate_unit<4, FlightPoint4D, Strategy2FlightFilter>("RealOpenSkySuite", name, points, flight_filter);
  }
}

// -----------------------------------------------------------------------------
// Main Entry Point
// -----------------------------------------------------------------------------
int main(int argc, char *argv[]) {
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--suite" && i + 1 < argc) {
      g_cfg.suite = argv[++i];
    } else if (arg == "--iterations" && i + 1 < argc) {
      g_cfg.iterations = std::max(2, std::stoi(argv[++i]));
    } else if (arg == "--tag" && i + 1 < argc) {
      g_cfg.tag = argv[++i];
    } else if (arg == "--min-dim" && i + 1 < argc) {
      g_cfg.min_dim = std::max(2, std::stoi(argv[++i]));
    } else if (arg == "--max-dim" && i + 1 < argc) {
      g_cfg.max_dim = std::min(11, std::max(2, std::stoi(argv[++i])));
    } else if (arg == "--dim" && i + 1 < argc) {
      int d = std::min(11, std::max(2, std::stoi(argv[++i])));
      g_cfg.min_dim = d;
      g_cfg.max_dim = d;
    } else if (arg == "--dim-n" && i + 1 < argc) {
      g_cfg.dim_n = std::stoull(argv[++i]);
    } else if (arg == "--opensky-dir" && i + 1 < argc) {
      g_cfg.opensky_dir = argv[++i];
    } else if (arg == "--output-dir" && i + 1 < argc) {
      g_cfg.output_dir = argv[++i];
    }
  }

  if (g_cfg.output_dir == "storage/results/rebuild_work" && !std::filesystem::exists("storage") && std::filesystem::exists("../storage")) {
    g_cfg.output_dir = "../storage/results/rebuild_work";
  }
  std::filesystem::create_directories(g_cfg.output_dir);
  std::string ts = get_timestamp_file_tag();
  g_cfg.run_csv_path = g_cfg.output_dir + "/rebuild_work_" + g_cfg.tag + "_" + g_cfg.suite + "_" + ts + ".csv";
  g_cfg.master_csv_path = g_cfg.output_dir + "/rebuild_work_" + g_cfg.tag + "_master.csv";

  std::cout << "=================================================================\n";
  std::cout << "  REBUILD WORK INVARIANCE & DIMENSIONAL TRANSITION ENGINE\n";
  std::cout << "  Platform Tag : " << g_cfg.tag << "\n";
  std::cout << "  Suite Target : " << g_cfg.suite << "\n";
  std::cout << "  Dimensions   : D = " << g_cfg.min_dim << " .. " << g_cfg.max_dim << "\n";
  std::cout << "  Dim Points N : " << g_cfg.dim_n << "\n";
  std::cout << "  Iterations   : " << g_cfg.iterations << " per unit\n";
  std::cout << "  Run CSV      : " << g_cfg.run_csv_path << "\n";
  std::cout << "  Master CSV   : " << g_cfg.master_csv_path << "\n";
  std::cout << "=================================================================\n";

  if (g_cfg.suite == "all" || g_cfg.suite == "dim") {
    run_dimension_suite();
  }
  if (g_cfg.suite == "all" || g_cfg.suite == "scale") {
    run_scale_suite();
  }
  if (g_cfg.suite == "all" || g_cfg.suite == "real") {
    run_real_suite();
  }

  std::cout << "\nAll experiments completed! Results cleanly saved to:\n";
  std::cout << " -> " << g_cfg.run_csv_path << "\n";
  std::cout << " -> " << g_cfg.master_csv_path << "\n";
  return 0;
}
