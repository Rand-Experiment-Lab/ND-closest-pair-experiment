#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <set>
#include <span>
#include <sstream>
#include <string>
#include <vector>

#include "flight_closest_pair.h"
#include "flight_space.h"

using namespace std;

std::string g_hourly_csv_log = "";
static std::set<std::string> g_completed_cases;

std::string current_timestamp() {
  std::time_t t = std::time(nullptr);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y-%m-%d %H:%M:%S",
                    std::localtime(&t))) {
    return mbstr;
  }
  return "Unknown";
}

std::string current_timestamp_file_format() {
  std::time_t t = std::time(nullptr);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y%m%d_%H%M%S",
                    std::localtime(&t))) {
    return mbstr;
  }
  return "run";
}

std::string format_epoch_to_utc(double epoch_seconds) {
  std::time_t t = static_cast<std::time_t>(epoch_seconds);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y-%m-%d %H:%M:%S UTC", std::gmtime(&t))) {
    return mbstr;
  }
  return to_string(epoch_seconds);
}

struct Stats {
  double mean;
  double median;
  double std_dev;
};

template <typename T> Stats compute_statistics(const std::vector<T> &values) {
  Stats st = {0, 0, 0};
  if (values.empty())
    return st;
  size_t n = values.size();
  double sum = std::accumulate(values.begin(), values.end(), 0.0);
  st.mean = sum / static_cast<double>(n);
  double variance_sum = 0.0;
  for (const auto &val : values) {
    double diff = static_cast<double>(val) - st.mean;
    variance_sum += diff * diff;
  }
  double variance = variance_sum / (n > 1 ? n - 1 : 1);
  st.std_dev = std::sqrt(variance);

  std::vector<double> sorted_values(values.begin(), values.end());
  std::sort(sorted_values.begin(), sorted_values.end());

  if (n % 2 == 0) {
    st.median = (sorted_values[n / 2 - 1] + sorted_values[n / 2]) / 2.0;
  } else {
    st.median = sorted_values[n / 2];
  }
  return st;
}

void parse_completed_cases_from_csv(const std::string &csv_path) {
  g_completed_cases.clear();
  if (!std::filesystem::exists(csv_path)) return;

  std::ifstream f(csv_path);
  if (!f.is_open()) return;

  std::string line;
  bool is_header = true;
  while (std::getline(f, line)) {
    if (line.empty()) continue;
    if (is_header) {
      is_header = false;
      continue;
    }
    std::vector<std::string> tokens;
    std::string token;
    bool in_quotes = false;
    for (char c : line) {
      if (c == '"') {
        in_quotes = !in_quotes;
      } else if (c == ',' && !in_quotes) {
        tokens.push_back(token);
        token.clear();
      } else {
        token += c;
      }
    }
    tokens.push_back(token);

    if (tokens.size() > 5) {
      std::string hour_tag = tokens[1];
      std::string input_order = tokens[4];
      std::string algo = tokens[5];
      std::string key = hour_tag + "|" + input_order + "|" + algo;
      g_completed_cases.insert(key);
    }
  }
  if (!g_completed_cases.empty()) {
    std::cout << "[Resume Checkpoint] Successfully loaded " << g_completed_cases.size()
              << " already completed test cases from:\n  --> " << csv_path << "\n";
  }
}

bool is_case_completed(const std::string &hour_tag, const std::string &order, const std::string &algo) {
  std::string key = hour_tag + "|" + order + "|" + algo;
  return g_completed_cases.count(key) > 0;
}

void init_hourly_csv_log(const std::string &custom_path = "") {
  if (!custom_path.empty()) {
    g_hourly_csv_log = custom_path;
    std::filesystem::path p(custom_path);
    if (p.has_parent_path()) {
      std::filesystem::create_directories(p.parent_path());
    }
    bool write_header = !std::filesystem::exists(g_hourly_csv_log) || (std::filesystem::file_size(g_hourly_csv_log) == 0);
    if (write_header) {
      std::ofstream file(g_hourly_csv_log, std::ios::out);
      file << "Timestamp,Hour_Tag,Num_Points,Min_Separation_m,Input_Order,Algorithm,Iterations,"
              "Min_Distance_m,Flight1_ID,Flight2_ID,Flight1_Epoch_UTC,Flight2_Epoch_UTC,"
              "Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,Raw_Times_ms,"
              "Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
      file.flush();
    } else {
      parse_completed_cases_from_csv(g_hourly_csv_log);
    }
    return;
  }

  std::string dir = "../opensky_experiment/results";
  if (!std::filesystem::exists("../opensky_experiment") && std::filesystem::exists("opensky_experiment")) {
    dir = "opensky_experiment/results";
  }
  std::filesystem::create_directories(dir);
  g_hourly_csv_log = dir + "/opensky_hourly_results_" + current_timestamp_file_format() + ".csv";

  std::ofstream file(g_hourly_csv_log, std::ios::out);
  file << "Timestamp,Hour_Tag,Num_Points,Min_Separation_m,Input_Order,Algorithm,Iterations,"
          "Min_Distance_m,Flight1_ID,Flight2_ID,Flight1_Epoch_UTC,Flight2_Epoch_UTC,"
          "Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,Raw_Times_ms,"
          "Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
  file.flush();
}

void log_hourly_csv(const std::string &hour_tag, size_t num_points, float min_sep,
                    const std::string &input_order, const std::string &algorithm,
                    int iterations, const FlightEncounter<4> &encounter,
                    float alpha, double t_min,
                    const Stats &time_st, const std::vector<double> &raw_times,
                    const Stats &rebuild_st, const std::vector<size_t> &raw_rebuilds) {
  std::ostringstream raw_time_ss;
  raw_time_ss << "\"[";
  for (size_t i = 0; i < raw_times.size(); ++i) {
    raw_time_ss << std::fixed << std::setprecision(5) << raw_times[i];
    if (i < raw_times.size() - 1) raw_time_ss << ", ";
  }
  raw_time_ss << "]\"";

  std::ostringstream raw_reb_ss;
  raw_reb_ss << "\"[";
  for (size_t i = 0; i < raw_rebuilds.size(); ++i) {
    raw_reb_ss << raw_rebuilds[i];
    if (i < raw_rebuilds.size() - 1) raw_reb_ss << ", ";
  }
  raw_reb_ss << "]\"";

  double flight1_epoch = t_min + (static_cast<double>(encounter.p1.coordinates[3]) / (alpha > 0.0f ? alpha : 186.45f));
  double flight2_epoch = t_min + (static_cast<double>(encounter.p2.coordinates[3]) / (alpha > 0.0f ? alpha : 186.45f));

  std::ostringstream row;
  row << current_timestamp() << "," << hour_tag << "," << num_points << "," << min_sep << ","
      << input_order << "," << algorithm << "," << iterations << ","
      << std::fixed << std::setprecision(3) << encounter.distance << ","
      << encounter.p1.flight_id << "," << encounter.p2.flight_id << ","
      << std::fixed << std::setprecision(1) << flight1_epoch << ","
      << std::fixed << std::setprecision(1) << flight2_epoch << ","
      << std::fixed << std::setprecision(3) << time_st.mean << ","
      << std::fixed << std::setprecision(3) << time_st.median << ","
      << std::fixed << std::setprecision(3) << time_st.std_dev << ","
      << raw_time_ss.str() << ","
      << std::fixed << std::setprecision(2) << rebuild_st.mean << ","
      << std::fixed << std::setprecision(2) << rebuild_st.median << ","
      << std::fixed << std::setprecision(2) << rebuild_st.std_dev << ","
      << raw_reb_ss.str() << "\n";

  if (!g_hourly_csv_log.empty()) {
    std::ofstream ver_file(g_hourly_csv_log, std::ios::app);
    ver_file << row.str();
    ver_file.flush(); // Force immediate unbuffered write to disk
  }
}

struct AlgoRunResult {
  std::string label;
  FlightEncounter<4> best_encounter;
  Stats time_st;
  Stats rebuild_st;
};

AlgoRunResult run_single_hourly_test(std::vector<FlightPoint<4>> &points,
                                     int iterations, bool is_randomized,
                                     float min_separation,
                                     const std::string &label,
                                     const std::string &hour_tag,
                                     const std::string &order_name,
                                     float alpha, double t_min) {
  std::vector<double> execution_times;
  execution_times.reserve(iterations);
  std::vector<size_t> rebuild_counts;
  rebuild_counts.reserve(iterations);

  FlightEncounter<4> encounter;
  const size_t N = points.size();

  std::vector<FlightPoint<4>> rand_buffer;
  if (is_randomized) {
    rand_buffer.resize(N);
  }

  std::random_device rd;
  std::array<std::uint32_t, 8> seed_data{};
  for (auto &v : seed_data) v = rd();
  std::seed_seq seq(seed_data.begin(), seed_data.end());
  std::mt19937 g(seq);

  for (int iter = 0; iter < iterations; ++iter) {
    double measured_ms = 0.0;
    if (is_randomized) {
      std::copy(points.begin(), points.end(), rand_buffer.begin());
      std::shuffle(rand_buffer.begin(), rand_buffer.end(), g);

      auto start = chrono::high_resolution_clock::now();
      encounter = find_min_dist_flight_grid<4>(
          std::span<const FlightPoint<4>>(rand_buffer), min_separation, false);
      auto end = chrono::high_resolution_clock::now();

      measured_ms = chrono::duration<double, milli>(end - start).count();
    } else {
      auto start = chrono::high_resolution_clock::now();
      encounter = find_min_dist_flight_grid<4>(
          std::span<const FlightPoint<4>>(points), min_separation, false);
      auto end = chrono::high_resolution_clock::now();

      measured_ms = chrono::duration<double, milli>(end - start).count();
    }

    execution_times.push_back(measured_ms);
    rebuild_counts.push_back(encounter.rebuild_count);
  }

  Stats time_st = compute_statistics(execution_times);
  Stats rebuild_st = compute_statistics(rebuild_counts);

  log_hourly_csv(hour_tag, N, min_separation, order_name, label, iterations,
                 encounter, alpha, t_min, time_st, execution_times, rebuild_st, rebuild_counts);

  std::cout << "    [Case Done -> CSV Updated] " << std::left << std::setw(12) << order_name
            << " | " << std::setw(20) << label
            << " | Mean: " << std::right << std::fixed << std::setprecision(2) << std::setw(8) << time_st.mean << " ms"
            << " | Min Dist: " << std::setw(8) << std::setprecision(2) << encounter.distance << " m"
            << " | Rebuilds: " << std::setw(5) << rebuild_st.mean << std::endl;

  return AlgoRunResult{label, encounter, time_st, rebuild_st};
}

void print_hourly_summary_table(const std::string &hour_tag, size_t num_points,
                                const AlgoRunResult &det_orig,
                                const AlgoRunResult &rand_orig,
                                const AlgoRunResult &det_sort,
                                const AlgoRunResult &rand_sort) {
  std::cout << "\n" << std::string(96, '=') << "\n";
  std::cout << "  HOUR: " << hour_tag << " | Points: " << num_points << "\n";
  std::cout << std::string(96, '=') << "\n";

  std::cout << "  " << std::left << std::setw(32) << "Test Scenario (4 Tests)"
            << std::right << std::setw(12) << "Mean Time"
            << std::setw(12) << "Median Time"
            << std::setw(12) << "StdDev"
            << std::setw(14) << "Mean Rebuilds"
            << std::setw(14) << "Min Dist (m)"
            << "\n";
  std::cout << "  " << std::string(96, '-') << "\n";

  auto print_line = [](const std::string &name, const AlgoRunResult &r) {
    std::cout << "  " << std::left << std::setw(32) << name
              << std::right << std::fixed << std::setprecision(2)
              << std::setw(9) << r.time_st.mean << " ms"
              << std::setw(9) << r.time_st.median << " ms"
              << std::setw(9) << r.time_st.std_dev << " ms"
              << std::setw(14) << r.rebuild_st.mean
              << std::setw(14) << std::setprecision(2) << r.best_encounter.distance
              << "\n";
  };

  print_line("1. Deterministic (Original)", det_orig);
  print_line("2. Randomized    (Original)", rand_orig);
  print_line("3. Deterministic (Time-Sorted)", det_sort);
  print_line("4. Randomized    (Time-Sorted)", rand_sort);
  std::cout << "  " << std::string(96, '-') << "\n";

  std::cout << "  * Hour Closest Conflict: Plane #" << det_orig.best_encounter.p1.flight_id
            << " & Plane #" << det_orig.best_encounter.p2.flight_id
            << " | Distance: " << det_orig.best_encounter.distance << " m\n";
}

int main(int argc, char *argv[]) {
  std::string hourly_dir = "../opensky_experiment/data/2019-05-27_hourly";
  if (!std::filesystem::exists(hourly_dir) && std::filesystem::exists("opensky_experiment/data/2019-05-27_hourly")) {
    hourly_dir = "opensky_experiment/data/2019-05-27_hourly";
  }
  int iterations = 10;
  float min_separation = 0.05f; // Default 5 cm to avoid sensor duplicates

  if (argc > 1) {
    hourly_dir = argv[1];
  }
  if (argc > 2) {
    iterations = std::stoi(argv[2]);
  }
  if (argc > 3) {
    min_separation = std::stof(argv[3]);
  }
  std::string custom_csv_path = "";
  if (argc > 4) {
    custom_csv_path = argv[4];
  }

  if (!std::filesystem::exists(hourly_dir) || !std::filesystem::is_directory(hourly_dir)) {
    std::cerr << "[Error] Directory does not exist: " << hourly_dir << "\n";
    std::cerr << "Please check the path or run the preprocessor first.\n";
    return 1;
  }

  // Find all .bin files in directory
  std::vector<std::string> bin_files;
  for (const auto &entry : std::filesystem::directory_iterator(hourly_dir)) {
    if (entry.path().extension() == ".bin") {
      bin_files.push_back(entry.path().string());
    }
  }
  std::sort(bin_files.begin(), bin_files.end());

  if (bin_files.empty()) {
    std::cerr << "[Error] No .bin files found in " << hourly_dir << "\n";
    std::cerr << "Run preprocess_hourly_opensky.py first to generate the 24 hourly files!\n";
    return 1;
  }

  init_hourly_csv_log(custom_csv_path);

  std::cout << "\n================================================================================\n";
  std::cout << "       OPENSKY HOURLY BENCHMARK: 24 HOURS x 4 TESTS (ORIG/SORTED x DET/RAND)   \n";
  std::cout << "================================================================================\n";
  std::cout << "Hourly Directory : " << hourly_dir << "\n";
  std::cout << "Hourly Files     : " << bin_files.size() << " files\n";
  std::cout << "Min Separation   : " << min_separation << " m\n";
  std::cout << "Iterations/test  : " << iterations << " runs\n";
  std::cout << "Results CSV log  : " << g_hourly_csv_log << "\n";
  std::cout << "================================================================================\n";

  for (size_t h_idx = 0; h_idx < bin_files.size(); ++h_idx) {
    const auto &fpath = bin_files[h_idx];
    std::string hour_tag = std::filesystem::path(fpath).stem().string();

    bool c1_done = is_case_completed(hour_tag, "Original", "Deterministic Grid");
    bool c2_done = is_case_completed(hour_tag, "Original", "Randomized Grid");
    bool c3_done = is_case_completed(hour_tag, "Sorted_Time", "Deterministic Grid");
    bool c4_done = is_case_completed(hour_tag, "Sorted_Time", "Randomized Grid");

    if (c1_done && c2_done && c3_done && c4_done) {
      std::cout << ">>> [" << (h_idx + 1) << "/" << bin_files.size() << "] "
                << hour_tag << " -> Already 100% completed in CSV (Skipping).\n";
      continue;
    }

    std::vector<FlightPoint<4>> points;
    float alpha = 0.0f;
    double t_min = 0.0;
    if (!load_flight_points_from_bin<4>(fpath, points, &alpha, &t_min)) {
      continue;
    }

    // 1. Test 1: Deterministic (Original Order)
    AlgoRunResult det_orig{};
    if (!c1_done) {
      det_orig = run_single_hourly_test(points, iterations, false, min_separation,
                                        "Deterministic Grid", hour_tag, "Original", alpha, t_min);
    } else {
      std::cout << "    [Resume] Skipping " << hour_tag << " | Original | Deterministic Grid (already in CSV)\n";
    }

    // 2. Test 2: Randomized (Original Order)
    AlgoRunResult rand_orig{};
    if (!c2_done) {
      rand_orig = run_single_hourly_test(points, iterations, true, min_separation,
                                         "Randomized Grid", hour_tag, "Original", alpha, t_min);
    } else {
      std::cout << "    [Resume] Skipping " << hour_tag << " | Original | Randomized Grid (already in CSV)\n";
    }

    // Sort along 4th Dimension (Time axis) only if sorted tests are pending
    if (!c3_done || !c4_done) {
      std::sort(std::execution::par, points.begin(), points.end(),
                [](const FlightPoint<4> &a, const FlightPoint<4> &b) {
                  return a.coordinates[3] < b.coordinates[3];
                });
    }

    // 3. Test 3: Deterministic (Time-Sorted)
    AlgoRunResult det_sort{};
    if (!c3_done) {
      det_sort = run_single_hourly_test(points, iterations, false, min_separation,
                                        "Deterministic Grid", hour_tag, "Sorted_Time", alpha, t_min);
    } else {
      std::cout << "    [Resume] Skipping " << hour_tag << " | Sorted_Time | Deterministic Grid (already in CSV)\n";
    }

    // 4. Test 4: Randomized (Time-Sorted)
    AlgoRunResult rand_sort{};
    if (!c4_done) {
      rand_sort = run_single_hourly_test(points, iterations, true, min_separation,
                                         "Randomized Grid", hour_tag, "Sorted_Time", alpha, t_min);
    } else {
      std::cout << "    [Resume] Skipping " << hour_tag << " | Sorted_Time | Randomized Grid (already in CSV)\n";
    }

    // Print clear 4-test comparison table for this hour
    print_hourly_summary_table(hour_tag, points.size(), det_orig, rand_orig, det_sort, rand_sort);
  }

  std::cout << "\n================================================================================\n";
  std::cout << "All 24 Hours Completed! All metrics saved to:\n";
  std::cout << "  " << g_hourly_csv_log << "\n";
  std::cout << "================================================================================\n";

  return 0;
}
