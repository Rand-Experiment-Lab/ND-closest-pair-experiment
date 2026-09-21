#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

#include "closest_pair_100m.h"
#include "flight_point.h"

namespace fs = std::filesystem;

// Global flag and output handle for resilient signal handling (SIGINT / SIGTERM)
static std::ofstream *g_csv_stream = nullptr;
static volatile std::sig_atomic_t g_stop_requested = 0;

void signal_handler(int sig) {
  g_stop_requested = 1;
  std::cerr << "\n[Signal " << sig << "] Graceful shutdown requested! Flushing CSV and exiting...\n";
  if (g_csv_stream && g_csv_stream->is_open()) {
    g_csv_stream->flush();
  }
}

// Minimal robust JSON parser for config.json (no external dependencies required)
struct BenchmarkConfig {
  std::string binary_path{"data/opensky_3days_100M_4d.bin"};
  std::string results_csv{"results/opensky_100M_results.csv"};
  std::size_t iterations{10};
  float min_separation_m{0.05f};
  bool show_progress{true};
  double progress_interval_pct{5.0};
  float alpha{250.0f};
  std::uint64_t seed{133742};
};

BenchmarkConfig load_config_json(const std::string &path) {
  BenchmarkConfig cfg;
  std::ifstream f(path);
  if (!f.is_open()) {
    return cfg;
  }

  std::string line;
  while (std::getline(f, line)) {
    auto parse_val = [&](const std::string &key) -> std::string {
      auto pos = line.find("\"" + key + "\"");
      if (pos == std::string::npos) return "";
      auto colon = line.find(':', pos);
      if (colon == std::string::npos) return "";
      std::string rest = line.substr(colon + 1);
      auto start = rest.find_first_not_of(" \t\r\n\",");
      auto end = rest.find_last_not_of(" \t\r\n\",");
      if (start == std::string::npos || end == std::string::npos) return "";
      return rest.substr(start, end - start + 1);
    };

    std::string v;
    if (!(v = parse_val("output_bin")).empty()) cfg.binary_path = v;
    if (!(v = parse_val("output_csv")).empty()) cfg.results_csv = v;
    if (!(v = parse_val("iterations")).empty()) cfg.iterations = std::stoull(v);
    if (!(v = parse_val("min_separation_m")).empty()) cfg.min_separation_m = std::stof(v);
    if (!(v = parse_val("alpha_velocity_m_s")).empty()) cfg.alpha = std::stof(v);
    if (!(v = parse_val("progress_interval_percent")).empty()) cfg.progress_interval_pct = std::stod(v);
  }
  return cfg;
}

inline bool str_ends_with(const std::string &str, const std::string &suffix) {
  return str.size() >= suffix.size() &&
         str.compare(str.size() - suffix.size(), suffix.size(), suffix) == 0;
}

int main(int argc, char *argv[]) {
  std::signal(SIGINT, signal_handler);
  std::signal(SIGTERM, signal_handler);

  std::cout << "===============================================================\n";
  std::cout << "     OpenSky 100-Million 4D Closest Pair Benchmark Suite\n";
  std::cout << "===============================================================\n";

  BenchmarkConfig cfg;

  // Search for config.json in current or parent directory
  if (fs::exists("config.json")) {
    cfg = load_config_json("config.json");
    std::cout << "[Config] Loaded parameters from ./config.json\n";
  } else if (fs::exists("../config.json")) {
    cfg = load_config_json("../config.json");
    std::cout << "[Config] Loaded parameters from ../config.json\n";
  }

  // CLI argument overrides
  if (argc > 1) {
    std::string arg1 = argv[1];
    if (str_ends_with(arg1, ".json")) {
      cfg = load_config_json(arg1);
      std::cout << "[Config] Loaded parameters from " << arg1 << "\n";
    } else {
      cfg.binary_path = arg1;
    }
  }
  if (argc > 2) cfg.iterations = std::stoull(argv[2]);
  if (argc > 3) cfg.min_separation_m = std::stof(argv[3]);
  if (argc > 4) cfg.results_csv = argv[4];
  if (argc > 5) cfg.show_progress = (std::stoi(argv[5]) != 0);

  std::cout << "[Setup] Binary Dataset:  " << cfg.binary_path << "\n";
  std::cout << "[Setup] Iterations:      " << cfg.iterations << "\n";
  std::cout << "[Setup] Min Separation:  " << cfg.min_separation_m << " meters\n";
  std::cout << "[Setup] Output CSV:      " << cfg.results_csv << "\n";
  std::cout << "[Setup] Show Progress:   " << (cfg.show_progress ? "Enabled" : "Disabled")
            << " (" << cfg.progress_interval_pct << "% intervals)\n";
  std::cout << "---------------------------------------------------------------\n";

  // Check file existence
  if (!fs::exists(cfg.binary_path)) {
    // Try checking relative to parent if run from build/
    if (fs::exists("../" + cfg.binary_path)) {
      cfg.binary_path = "../" + cfg.binary_path;
    } else {
      std::cerr << "[Error] Binary file not found: " << cfg.binary_path << "\n";
      std::cerr << "Run `python3 data_preparator.py` first to generate the dataset.\n";
      return 1;
    }
  }

  // Ensure output directory exists
  fs::path out_csv_path(cfg.results_csv);
  if (out_csv_path.has_parent_path()) {
    fs::create_directories(out_csv_path.parent_path());
  }

  // Load points into memory
  std::vector<FlightPoint<4>> points;
  DatasetMeta meta;
  if (!load_flight_dataset_bin(cfg.binary_path, points, meta)) {
    return 1;
  }

  std::cout << "[Memory] Point Vector RAM: "
            << (points.size() * sizeof(FlightPoint<4>)) / (1024 * 1024) << " MB ("
            << points.size() << " points)\n\n";

  // Open CSV and write header if newly created
  bool write_header = !fs::exists(cfg.results_csv) || (fs::file_size(cfg.results_csv) == 0);
  std::ofstream csv_out(cfg.results_csv, std::ios::app);
  if (!csv_out.is_open()) {
    std::cerr << "[Error] Cannot open output CSV file: " << cfg.results_csv << "\n";
    return 1;
  }
  g_csv_stream = &csv_out;

  if (write_header) {
    csv_out << "Timestamp,Dataset,Dimensions,Num_Points,Min_Separation_m,Input_Order,"
            << "Algorithm,Iterations,Min_Distance_m,Flight1_ID,Flight2_ID,"
            << "Flight1_UTC,Flight2_UTC,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,"
            << "Raw_Times_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
    csv_out.flush();
  }

  // Benchmark specifications: ONLY Original order (no sorting splits)
  // 1. Deterministic Grid
  // 2. Randomized Grid
  struct TestSpec {
    std::string order_name;
    std::string algo_name;
    bool is_randomized;
  };

  std::vector<TestSpec> tests = {
      {"Original", "Deterministic Grid", false},
      {"Original", "Randomized Grid", true}
  };

  for (const auto &test : tests) {
    if (g_stop_requested) break;

    std::cout << ">>> Running Scenario: [" << test.order_name << " - " << test.algo_name << "] ("
              << cfg.iterations << " iterations) <<<\n";

    std::vector<double> times_ms;
    std::vector<std::size_t> rebuilds;
    float best_distance = std::numeric_limits<float>::infinity();
    FlightPoint<4> best_p1{}, best_p2{};

    for (std::size_t iter = 0; iter < cfg.iterations; ++iter) {
      if (g_stop_requested) break;

      std::cout << "  -> Iteration " << (iter + 1) << "/" << cfg.iterations << " starting..." << std::endl;

      EncounterResult<4> res;
      if (!test.is_randomized) {
        res = find_closest_pair_deterministic<4>(
            points, cfg.min_separation_m, cfg.show_progress, cfg.progress_interval_pct);
      } else {
        std::uint64_t iter_seed = cfg.seed + iter * 7919;
        res = find_closest_pair_randomized<4>(
            points, iter_seed, cfg.min_separation_m, cfg.show_progress, cfg.progress_interval_pct);
      }

      times_ms.push_back(res.execution_time_ms);
      rebuilds.push_back(res.rebuild_count);
      if (res.distance < best_distance) {
        best_distance = res.distance;
        best_p1 = res.p1;
        best_p2 = res.p2;
      }

      std::cout << "  -> Iteration " << (iter + 1) << " done: "
                << std::fixed << std::setprecision(2) << res.execution_time_ms / 1000.0 << " s"
                << " (" << res.execution_time_ms << " ms) | Rebuilds: " << res.rebuild_count
                << " | Min Dist: " << std::setprecision(3) << res.distance << " m\n\n";
    }

    if (times_ms.empty()) continue;

    // Statistical metrics
    double sum_times = std::accumulate(times_ms.begin(), times_ms.end(), 0.0);
    double mean_time = sum_times / times_ms.size();

    auto sorted_times = times_ms;
    std::sort(sorted_times.begin(), sorted_times.end());
    double median_time = sorted_times[sorted_times.size() / 2];

    double sq_diff_time = 0.0;
    for (double t : times_ms) sq_diff_time += (t - mean_time) * (t - mean_time);
    double stddev_time = (times_ms.size() > 1) ? std::sqrt(sq_diff_time / (times_ms.size() - 1)) : 0.0;

    double sum_reb = std::accumulate(rebuilds.begin(), rebuilds.end(), 0.0);
    double mean_reb = sum_reb / rebuilds.size();

    auto sorted_reb = rebuilds;
    std::sort(sorted_reb.begin(), sorted_reb.end());
    double median_reb = sorted_reb[sorted_reb.size() / 2];

    double sq_diff_reb = 0.0;
    for (std::size_t r : rebuilds) sq_diff_reb += (r - mean_reb) * (r - mean_reb);
    double stddev_reb = (rebuilds.size() > 1) ? std::sqrt(sq_diff_reb / (rebuilds.size() - 1)) : 0.0;

    // Calculate actual timestamp in UTC
    double utc_p1 = meta.t_ref + (meta.alpha > 0 ? (best_p1.coordinates[3] / meta.alpha) : 0.0);
    double utc_p2 = meta.t_ref + (meta.alpha > 0 ? (best_p2.coordinates[3] / meta.alpha) : 0.0);

    // Current ISO timestamp
    auto now_c = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm tm_now{};
    localtime_r(&now_c, &tm_now);
    std::ostringstream time_ss;
    time_ss << std::put_time(&tm_now, "%Y-%m-%d %H:%M:%S");

    // Format raw arrays into JSON-like strings
    std::ostringstream raw_t_ss, raw_r_ss;
    raw_t_ss << "\"[";
    for (std::size_t i = 0; i < times_ms.size(); ++i) {
      if (i > 0) raw_t_ss << ", ";
      raw_t_ss << std::fixed << std::setprecision(2) << times_ms[i];
    }
    raw_t_ss << "]\"";

    raw_r_ss << "\"[";
    for (std::size_t i = 0; i < rebuilds.size(); ++i) {
      if (i > 0) raw_r_ss << ", ";
      raw_r_ss << rebuilds[i];
    }
    raw_r_ss << "]\"";

    // Write to CSV and flush immediately
    csv_out << time_ss.str() << ",OpenSky_100M,4," << points.size() << ","
            << cfg.min_separation_m << "," << test.order_name << "," << test.algo_name << ","
            << times_ms.size() << "," << std::fixed << std::setprecision(3) << best_distance << ","
            << best_p1.flight_id << "," << best_p2.flight_id << ","
            << std::fixed << std::setprecision(1) << utc_p1 << "," << utc_p2 << ","
            << std::setprecision(3) << mean_time << "," << median_time << "," << stddev_time << ","
            << raw_t_ss.str() << ","
            << std::setprecision(2) << mean_reb << "," << median_reb << "," << stddev_reb << ","
            << raw_r_ss.str() << "\n";
    csv_out.flush();

    std::cout << "[Live CSV Updated] -> Saved result for " << test.order_name << " - " << test.algo_name
              << " (" << cfg.results_csv << ")\n";
    std::cout << "  Mean Time: " << (mean_time / 1000.0) << " s | Rebuilds: " << mean_reb
              << " | Closest Encounter: " << best_distance << " m\n";
    std::cout << "---------------------------------------------------------------\n";
  }

  csv_out.close();
  g_csv_stream = nullptr;

  std::cout << "\n[Benchmark Complete] All test cases successfully recorded in "
            << cfg.results_csv << "\n";
  return 0;
}
