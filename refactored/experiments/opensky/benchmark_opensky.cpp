#include <algorithm>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include "../../adapters/opensky/opensky_adapter.h"
#include "../../core/closest_pair.h"
#include "../../core/metrics_logger.h"

using namespace core;
using namespace adapters::opensky;

int main(int argc, char *argv[]) {
  std::string tag = get_timestamp_file_tag();
  std::string run_csv_path = "storage/results/opensky/opensky_benchmark_" + tag + ".csv";
  std::string master_csv_path = "storage/results/opensky/master_opensky.csv";

  std::string input_path = "";
  int iterations = 5;
  float min_separation = 0.05f;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--input" && i + 1 < argc) {
      input_path = argv[++i];
    } else if (arg == "--iterations" && i + 1 < argc) {
      iterations = std::max(1, std::stoi(argv[++i]));
    } else if (arg == "--min-sep" && i + 1 < argc) {
      min_separation = std::stof(argv[++i]);
    }
  }

  std::cout << "=================================================================\n";
  std::cout << "  ND Closest Pair: Unified OpenSky 4D Real Data Benchmark Engine\n";
  std::cout << "  Logging to: " << run_csv_path << "\n";
  std::cout << "  Iterations: " << iterations << "\n";
  std::cout << "=================================================================\n";

  // Scan OpenSky dataset directories or handle input_path
  std::vector<std::string> dataset_files;
  if (!input_path.empty()) {
    if (std::filesystem::is_directory(input_path)) {
      for (const auto &entry : std::filesystem::directory_iterator(input_path)) {
        if (entry.path().extension() == ".bin") {
          dataset_files.push_back(entry.path().string());
        }
      }
      std::sort(dataset_files.begin(), dataset_files.end());
    } else if (std::filesystem::exists(input_path)) {
      dataset_files.push_back(input_path);
    } else {
      std::cerr << "Error: Specified input path does not exist: " << input_path << "\n";
      return 1;
    }
  } else {
    std::vector<std::string> candidates = {
        "storage/datasets/opensky",
        "opensky_experiment/data/2019-05-27_hourly",
        "opensky_100m/data",
        "cache_benchmark"};

    for (const auto &cand : candidates) {
      if (std::filesystem::exists(cand)) {
        for (const auto &entry : std::filesystem::directory_iterator(cand)) {
          if (entry.path().extension() == ".bin") {
            dataset_files.push_back(entry.path().string());
          }
        }
        if (!dataset_files.empty()) {
          std::sort(dataset_files.begin(), dataset_files.end());
          break;
        }
      }
    }
  }

  if (dataset_files.empty()) {
    std::cout << "[OpenSky Benchmark] Notice: No preprocessed .bin datasets found.\n"
              << "Please preprocess OpenSky data or provide --input <path_or_dir>.\n";
    return 0;
  }

  Strategy2FlightFilter flight_filter{min_separation};

  for (const auto &filepath : dataset_files) {
    std::vector<FlightPoint4D> points;
    float alpha = 0.0f;
    double t_min = 0.0;

    if (!OpenSkyAdapter::load_binary_dataset(filepath, points, &alpha, &t_min)) {
      continue;
    }

    std::size_t num_points = points.size();
    std::string filename = std::filesystem::path(filepath).stem().string();
    std::cout << "\n--- Processing: " << filename << " (" << num_points << " points) ---\n";

    // Build extra metadata JSON
    std::string extra_json = "{\"alpha\": " + std::to_string(alpha) +
                             ", \"t_min\": " + std::to_string(t_min) +
                             ", \"min_separation_m\": " + std::to_string(min_separation) + "}";

    // 1. Deterministic Run
    std::vector<double> det_times;
    std::vector<std::size_t> det_rebuilds;
    std::vector<std::size_t> det_rebuild_works;
    std::vector<std::size_t> last_det_indices;
    float det_min_dist = 0.0f;
    FlightPoint4D best_p1{}, best_p2{};

    std::cout << "  Running Deterministic (" << iterations << " iterations)...\n";
    for (int it = 0; it < iterations; ++it) {
      auto res = find_closest_pair_deterministic<4>(
          std::span<const FlightPoint4D>(points), flight_filter);
      det_times.push_back(res.execution_time_ms);
      det_rebuilds.push_back(res.rebuild_count);
      det_rebuild_works.push_back(res.rebuild_work);
      det_min_dist = res.min_distance;
      best_p1 = res.p1;
      best_p2 = res.p2;
      last_det_indices = res.rebuild_indices;
      std::cout << "    [Det " << (it + 1) << "/" << iterations << "] "
                << res.execution_time_ms << " ms, " << res.rebuild_count << " rebuilds, "
                << res.rebuild_work << " points re-hashed\n" << std::flush;
    }

    double det_mean_work = std::accumulate(det_rebuild_works.begin(), det_rebuild_works.end(), 0.0) / iterations;

    std::string det_extra_json = "{\"alpha\": " + std::to_string(alpha) +
                                 ", \"t_min\": " + std::to_string(t_min) +
                                 ", \"min_separation_m\": " + std::to_string(min_separation) +
                                 ", \"mean_rebuild_work\": " + std::to_string(det_mean_work) + "}";

    MetricsLogger::log_record(run_csv_path, "OpenSky", filename, 4,
                              num_points, "Original", "Deterministic Grid",
                              iterations, det_min_dist, det_times,
                              det_rebuilds, det_extra_json);
    MetricsLogger::log_record(master_csv_path, "OpenSky", filename, 4,
                              num_points, "Original", "Deterministic Grid",
                              iterations, det_min_dist, det_times,
                              det_rebuilds, det_extra_json);

    // 2. Randomized Run
    std::vector<double> rand_times;
    std::vector<std::size_t> rand_rebuilds;
    std::vector<std::size_t> rand_rebuild_works;
    std::vector<std::size_t> last_rand_indices;
    float rand_min_dist = 0.0f;

    std::cout << "  Running Randomized (" << iterations << " iterations)...\n";
    for (int it = 0; it < iterations; ++it) {
      auto res = find_closest_pair_randomized<4>(points, flight_filter);
      rand_times.push_back(res.execution_time_ms);
      rand_rebuilds.push_back(res.rebuild_count);
      rand_rebuild_works.push_back(res.rebuild_work);
      rand_min_dist = res.min_distance;
      last_rand_indices = res.rebuild_indices;
      std::cout << "    [Rand " << (it + 1) << "/" << iterations << "] "
                << res.execution_time_ms << " ms, " << res.rebuild_count << " rebuilds, "
                << res.rebuild_work << " points re-hashed\n" << std::flush;
    }

    double rand_mean_work = std::accumulate(rand_rebuild_works.begin(), rand_rebuild_works.end(), 0.0) / iterations;

    std::string rand_extra_json = "{\"alpha\": " + std::to_string(alpha) +
                                  ", \"t_min\": " + std::to_string(t_min) +
                                  ", \"min_separation_m\": " + std::to_string(min_separation) +
                                  ", \"mean_rebuild_work\": " + std::to_string(rand_mean_work) + "}";

    MetricsLogger::log_record(run_csv_path, "OpenSky", filename, 4,
                              num_points, "Original", "Randomized Grid",
                              iterations, rand_min_dist, rand_times,
                              rand_rebuilds, rand_extra_json);
    MetricsLogger::log_record(master_csv_path, "OpenSky", filename, 4,
                              num_points, "Original", "Randomized Grid",
                              iterations, rand_min_dist, rand_times,
                              rand_rebuilds, rand_extra_json);

    SummaryStats det_s = compute_stats(det_times);
    SummaryStats rand_s = compute_stats(rand_times);

    std::cout << "  Min Distance: " << det_min_dist << " m between Flight "
              << best_p1.payload.flight_id << " and " << best_p2.payload.flight_id << "\n";
    std::cout << "  Deterministic Mean: " << det_s.mean << " ms (Work: " << det_mean_work << " points)\n";
    std::cout << "  Randomized Mean   : " << rand_s.mean << " ms (Work: " << rand_mean_work << " points)\n";
    if (rand_s.mean > 0.0) {
      std::cout << "  Speedup           : " << (det_s.mean / rand_s.mean) << "x\n";
    }
  }

  std::cout << "\nOpenSky benchmarks completed successfully!\n";
  return 0;
}
