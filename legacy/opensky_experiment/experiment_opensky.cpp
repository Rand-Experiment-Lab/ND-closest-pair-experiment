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
#include <span>
#include <sstream>
#include <string>
#include <vector>

#include "flight_closest_pair.h"
#include "flight_space.h"

using namespace std;

std::string g_current_run_csv = "";

std::string current_timestamp() {
  std::time_t t = std::time(nullptr);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y-%m-%d %H:%M:%S",
                    std::localtime(&t))) {
    return mbstr;
  }
  return "Unknown";
}

std::string format_epoch_to_utc(double epoch_seconds) {
  std::time_t t = static_cast<std::time_t>(epoch_seconds);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y-%m-%d %H:%M:%S UTC", std::gmtime(&t))) {
    return mbstr;
  }
  return to_string(epoch_seconds);
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

void init_csv_file() {
  std::string dir = "../opensky_experiment/results";
  if (!std::filesystem::exists("../opensky_experiment") && std::filesystem::exists("opensky_experiment")) {
    dir = "opensky_experiment/results";
  }
  std::filesystem::create_directories(dir);
  g_current_run_csv = dir + "/opensky_results_" + current_timestamp_file_format() + ".csv";

  std::ofstream file(g_current_run_csv, std::ios::out);
  file << "Timestamp,Dataset,Dimensions,Num_Points,Min_Separation_m,Input_Order,Algorithm,Iterations,"
          "Min_Distance_m,Flight1_ID,Flight2_ID,Flight1_Epoch_UTC,Flight2_Epoch_UTC,"
          "Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,Raw_Times_ms,"
          "Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
}

void log_to_csv(const std::string &dataset, size_t dim, size_t num_points, float min_sep,
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

  double flight1_epoch = t_min + (static_cast<double>(encounter.p1.coordinates[3]) / (alpha > 0.0f ? alpha : 240.0f));
  double flight2_epoch = t_min + (static_cast<double>(encounter.p2.coordinates[3]) / (alpha > 0.0f ? alpha : 240.0f));

  std::ostringstream row;
  row << current_timestamp() << "," << dataset << "," << dim << "," << num_points << "," << min_sep << ","
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

  if (!g_current_run_csv.empty()) {
    std::ofstream ver_file(g_current_run_csv, std::ios::app);
    ver_file << row.str();
  }
}

struct AlgoRunResult {
  std::string label;
  FlightEncounter<4> best_encounter;
  Stats time_st;
  Stats rebuild_st;
};

AlgoRunResult run_experiment_scenario(std::vector<FlightPoint<4>> &points,
                                     int iterations, bool is_randomized,
                                     float min_separation,
                                     const std::string &label,
                                     const std::string &dataset_name,
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

  log_to_csv(dataset_name, 4, N, min_separation, order_name, label, iterations,
             encounter, alpha, t_min, time_st, execution_times, rebuild_st, rebuild_counts);

  return AlgoRunResult{label, encounter, time_st, rebuild_st};
}

void print_comparison_table(const std::string &scenario_title,
                            const AlgoRunResult &det,
                            const AlgoRunResult &rand,
                            float alpha, double t_min) {
  std::cout << "\n  [" << scenario_title << "]\n";
  std::cout << "  " << std::string(92, '-') << "\n";
  std::cout << "  " << std::left << std::setw(22) << "Algorithm"
            << std::right << std::setw(12) << "Mean Time"
            << std::setw(12) << "Median Time"
            << std::setw(12) << "StdDev Time"
            << std::setw(14) << "Mean Rebuilds"
            << std::setw(18) << "Min 4D Dist (m)"
            << "\n";
  std::cout << "  " << std::string(92, '-') << "\n";

  auto print_row = [](const AlgoRunResult &r) {
    std::cout << "  " << std::left << std::setw(22) << r.label
              << std::right << std::fixed << std::setprecision(2)
              << std::setw(9) << r.time_st.mean << " ms"
              << std::setw(9) << r.time_st.median << " ms"
              << std::setw(9) << r.time_st.std_dev << " ms"
              << std::setw(14) << r.rebuild_st.mean
              << std::setw(18) << std::setprecision(2) << r.best_encounter.distance
              << "\n";
  };

  print_row(det);
  print_row(rand);
  std::cout << "  " << std::string(92, '-') << "\n";

  double t1_epoch = t_min + (static_cast<double>(det.best_encounter.p1.coordinates[3]) / alpha);
  double t2_epoch = t_min + (static_cast<double>(det.best_encounter.p2.coordinates[3]) / alpha);

  std::cout << "  * Critical Separation Encounter:\n"
            << "    - Aircraft #1: Flight ID " << det.best_encounter.p1.flight_id
            << " at " << format_epoch_to_utc(t1_epoch) << "\n"
            << "    - Aircraft #2: Flight ID " << det.best_encounter.p2.flight_id
            << " at " << format_epoch_to_utc(t2_epoch) << "\n"
            << "    - 4D Separation Distance: " << det.best_encounter.distance << " meters\n";

  if (rand.rebuild_st.mean > 0 && det.rebuild_st.mean > rand.rebuild_st.mean) {
    double reb_reduction = det.rebuild_st.mean / rand.rebuild_st.mean;
    std::cout << "  => Rebuild Reduction: " << std::fixed << std::setprecision(1)
              << reb_reduction << "x fewer rebuilds with Randomization!\n";
  }
}

int main(int argc, char *argv[]) {
  std::string binary_path = "../opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin";
  if (!std::filesystem::exists(binary_path) && std::filesystem::exists("opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin")) {
    binary_path = "opensky_experiment/data/opensky_2019-05-27_full_day_4d.bin";
  }
  int iterations = 10;
  float min_separation = 0.05f; // Default 5 cm to eliminate duplicate sensor artifacts

  if (argc > 1) {
    binary_path = argv[1];
  }
  if (argc > 2) {
    iterations = std::stoi(argv[2]);
  }
  if (argc > 3) {
    min_separation = std::stof(argv[3]);
  }

  std::vector<FlightPoint<4>> points;
  float alpha = 0.0f;
  double t_min = 0.0;
  if (!load_flight_points_from_bin<4>(binary_path, points, &alpha, &t_min)) {
    std::cerr << "[Error] Cannot run experiment without binary dataset: " << binary_path << "\n";
    std::cerr << "Run preprocess_opensky.py first to convert your CSV into the binary format.\n";
    return 1;
  }

  init_csv_file();

  std::cout << "\n================================================================================\n";
  std::cout << "         REAL-WORLD OPENSKY 4D CLOSEST PAIR PERFORMANCE EXPERIMENT              \n";
  std::cout << "================================================================================\n";
  std::cout << "Dataset          : " << binary_path << "\n";
  std::cout << "Loaded 4D Points : " << points.size() << "\n";
  std::cout << "Velocity Alpha   : " << alpha << " m/s\n";
  std::cout << "Temporal Origin  : " << format_epoch_to_utc(t_min) << " (" << std::fixed << std::setprecision(1) << t_min << " s)\n";
  std::cout << "Min Separation   : " << min_separation << " meters (filters sensor duplicate artifacts)\n";
  std::cout << "Iterations/test  : " << iterations << " runs\n";
  std::cout << "Results saved to : " << g_current_run_csv << "\n";
  std::cout << "================================================================================\n\n";

  // Test 1: Original Given Order
  auto det_orig = run_experiment_scenario(points, iterations, false, min_separation,
                                         "Deterministic Grid", "OpenSky", "Original", alpha, t_min);
  auto rand_orig = run_experiment_scenario(points, iterations, true, min_separation,
                                          "Randomized Grid", "OpenSky", "Original", alpha, t_min);
  print_comparison_table("1. Original Radar Chronological Order (" + to_string(iterations) + " runs)", det_orig, rand_orig, alpha, t_min);

  // Test 2: Sorted Order based on 4th Dimension (Time axis: w_time = alpha * (t - t_min))
  std::cout << "\nSorting points along 4th Dimension (Time)...\n";
  std::sort(std::execution::par, points.begin(), points.end(),
            [](const FlightPoint<4> &a, const FlightPoint<4> &b) {
              return a.coordinates[3] < b.coordinates[3];
            });

  auto det_time_sort = run_experiment_scenario(points, iterations, false, min_separation,
                                              "Deterministic Grid", "OpenSky", "Sorted_Time_Axis", alpha, t_min);
  auto rand_time_sort = run_experiment_scenario(points, iterations, true, min_separation,
                                               "Randomized Grid", "OpenSky", "Sorted_Time_Axis", alpha, t_min);
  print_comparison_table("2. Sorted Order (4th Dimension: Time Ascending) (" + to_string(iterations) + " runs)", det_time_sort, rand_time_sort, alpha, t_min);

  std::cout << "\n================================================================================\n";
  std::cout << "OpenSky Experiment Completed Successfully!\n";
  std::cout << "Detailed logs written to: " << g_current_run_csv << "\n";
  std::cout << "================================================================================\n";

  return 0;
}
