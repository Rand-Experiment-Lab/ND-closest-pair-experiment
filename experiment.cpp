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

#include "closest_pair.h"
#include "space.h"

using namespace std;

std::string g_current_run_csv_filename = "";

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

struct Stats {
  double mean;
  double median;
  double std_dev;
};

void init_csv_file() {
  std::filesystem::create_directories("results");
  g_current_run_csv_filename = "results/experiment_results_" + current_timestamp_file_format() + ".csv";
  
  std::ofstream file(g_current_run_csv_filename, std::ios::out);
  file << "Timestamp,Space_Type,Dimensions,Num_Points,Input_Order,Algorithm,"
          "Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,"
          "Raw_Times_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
  file.close();

  // Also ensure the primary aggregate experiment_results.csv exists
  std::ifstream check_agg("experiment_results.csv");
  if (!check_agg.good()) {
    std::ofstream agg("experiment_results.csv", std::ios::out);
    agg << "Timestamp,Space_Type,Dimensions,Num_Points,Input_Order,Algorithm,"
           "Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,"
           "Raw_Times_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
  }
}

void log_to_csv(const std::string &space_type, size_t dim, size_t num_points,
                const std::string &input_order, std::string algorithm,
                int iterations, float min_dist, const Stats &time_st,
                const std::vector<double> &raw_times, const Stats &rebuild_st,
                const std::vector<size_t> &raw_rebuilds) {
  // Trim trailing spaces from algorithm name
  algorithm.erase(algorithm.find_last_not_of(" ") + 1);

  // Format raw times as a JSON-like array inside quotes
  std::ostringstream raw_ss;
  raw_ss << "\"[";
  for (size_t i = 0; i < raw_times.size(); ++i) {
    raw_ss << std::fixed << std::setprecision(5) << raw_times[i];
    if (i < raw_times.size() - 1)
      raw_ss << ", ";
  }
  raw_ss << "]\"";

  // Format raw rebuilds as a JSON-like array inside quotes
  std::ostringstream rebuilds_ss;
  rebuilds_ss << "\"[";
  for (size_t i = 0; i < raw_rebuilds.size(); ++i) {
    rebuilds_ss << raw_rebuilds[i];
    if (i < raw_rebuilds.size() - 1)
      rebuilds_ss << ", ";
  }
  rebuilds_ss << "]\"";

  std::ostringstream row;
  row << current_timestamp() << "," << space_type << "," << dim << ","
      << num_points << "," << input_order << "," << algorithm << ","
      << iterations << "," << std::fixed << std::setprecision(5) << min_dist
      << "," << std::fixed << std::setprecision(5) << time_st.mean << ","
      << std::fixed << std::setprecision(5) << time_st.median << ","
      << std::fixed << std::setprecision(5) << time_st.std_dev << ","
      << raw_ss.str() << "," << std::fixed << std::setprecision(5)
      << rebuild_st.mean << "," << std::fixed << std::setprecision(5)
      << rebuild_st.median << "," << std::fixed << std::setprecision(5)
      << rebuild_st.std_dev << "," << rebuilds_ss.str() << "\n";

  // 1. Write to versioned file for this specific run
  if (!g_current_run_csv_filename.empty()) {
    std::ofstream ver_file(g_current_run_csv_filename, std::ios::app);
    ver_file << row.str();
  }

  // 2. Also append to the primary aggregate experiment_results.csv
  std::ofstream agg_file("experiment_results.csv", std::ios::app);
  agg_file << row.str();
}

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

struct AlgoRunResult {
  std::string label;
  float min_dist;
  Stats time_st;
  Stats rebuild_st;
  std::vector<double> raw_times;
  std::vector<size_t> raw_rebuilds;
};

template <size_t Dim>
AlgoRunResult run_algorithm_multipleTimes(Space<Dim> &s, int k, bool isRand,
                                         const string &label, const string &space_type,
                                         const string &input_order) {
  std::vector<double> execution_times;
  execution_times.reserve(k);
  std::vector<size_t> rebuild_counts;
  rebuild_counts.reserve(k);
  float min_val = 0.0f;
  size_t num_points = s.points.size();

  std::vector<Point<Dim>> rand_buffer;
  if (isRand) {
    rand_buffer.resize(num_points);
  }

  std::random_device rd;
  std::array<std::uint32_t, 8> seed_data{};
  for (auto &v : seed_data) {
    v = rd();
  }
  std::seed_seq seq(seed_data.begin(), seed_data.end());
  std::mt19937 g(seq);

  for (int i = 0; i < k; i++) {
    size_t rebuilds = 0;
    double measured_ms = 0.0;

    if (isRand) {
      std::copy(s.points.begin(), s.points.end(), rand_buffer.begin());
      std::shuffle(rand_buffer.begin(), rand_buffer.end(), g);

      auto start = chrono::high_resolution_clock::now();
      min_val = find_min_dist_grid_based<Dim>(
          std::span<const Point<Dim>>(rand_buffer), false, &rebuilds);
      auto end = chrono::high_resolution_clock::now();

      chrono::duration<double, milli> ms = end - start;
      measured_ms = ms.count();
    } else {
      auto start = chrono::high_resolution_clock::now();
      min_val = find_min_dist_grid_based<Dim>(
          std::span<const Point<Dim>>(s.points), false, &rebuilds);
      auto end = chrono::high_resolution_clock::now();

      chrono::duration<double, milli> ms = end - start;
      measured_ms = ms.count();
    }

    execution_times.push_back(measured_ms);
    rebuild_counts.push_back(rebuilds);
  }

  Stats time_st = compute_statistics(execution_times);
  Stats rebuild_st = compute_statistics(rebuild_counts);

  log_to_csv(space_type, Dim, num_points, input_order, label, k, min_val,
             time_st, execution_times, rebuild_st, rebuild_counts);

  return AlgoRunResult{label, min_val, time_st, rebuild_st, execution_times, rebuild_counts};
}

void print_comparison_table(const std::string &scenario_title,
                            const AlgoRunResult &det,
                            const AlgoRunResult &rand) {
  std::cout << "\n  [" << scenario_title << "]\n";
  std::cout << "  " << std::string(86, '-') << "\n";
  std::cout << "  " << std::left << std::setw(22) << "Algorithm"
            << std::right << std::setw(12) << "Mean Time"
            << std::setw(12) << "Median Time"
            << std::setw(12) << "StdDev Time"
            << std::setw(14) << "Mean Rebuilds"
            << std::setw(14) << "Min Distance"
            << "\n";
  std::cout << "  " << std::string(86, '-') << "\n";

  auto print_row = [](const AlgoRunResult &r) {
    std::cout << "  " << std::left << std::setw(22) << r.label
              << std::right << std::fixed << std::setprecision(2)
              << std::setw(9) << r.time_st.mean << " ms"
              << std::setw(9) << r.time_st.median << " ms"
              << std::setw(9) << r.time_st.std_dev << " ms"
              << std::setw(14) << r.rebuild_st.mean
              << std::setw(14) << std::setprecision(4) << r.min_dist
              << "\n";
  };

  print_row(det);
  print_row(rand);
  std::cout << "  " << std::string(86, '-') << "\n";

  if (rand.rebuild_st.mean > 0 && det.rebuild_st.mean > rand.rebuild_st.mean) {
    double reb_reduction = det.rebuild_st.mean / rand.rebuild_st.mean;
    std::cout << "  => Rebuild Reduction: " << std::fixed << std::setprecision(1)
              << reb_reduction << "x fewer rebuilds with Randomization!\n";
  }
}

// ----------------------------------------------------------------------------
// Normal Space Test Suite (Original Order vs. Pre-Shuffled Stored & Loaded)
// ----------------------------------------------------------------------------
template <size_t Dim>
void run_normal_space_test(size_t num_points, int iterations = 5) {
  std::cout << "\n" << std::string(90, '=') << "\n";
  std::cout << "  [NORMAL SPACE: STORE & LOAD SHUFFLED] Dimension: " << Dim << "D | Points: " << num_points << "\n";
  std::cout << std::string(90, '=') << "\n";

  // 1. Load original uniform dataset from disk
  auto space = Space<Dim>::get_or_create("uniform", num_points);

  // 2. Load pre-shuffled uniform dataset from disk (stored & loaded fresh, zero in-loop shuffle)
  auto rand_space = Space<Dim>::get_or_create("uniform_shuffled", num_points);

  // 1. Original Generation Order vs Pre-Shuffled Loaded
  auto det_orig = run_algorithm_multipleTimes(space, iterations, false,
                                             "Deterministic Grid", "Normal", "Original");
  auto rand_orig = run_algorithm_multipleTimes(rand_space, iterations, false,
                                              "Randomized Grid", "Normal", "Original");
  print_comparison_table("1. Original Order vs. Pre-Shuffled Stored/Loaded (" + std::to_string(iterations) + " runs)", det_orig, rand_orig);

  // 2. Sorted Order (Axis Ascending along Axis 0) vs Pre-Shuffled Loaded
  space.sort_points(SortStrategy::AxisAscending, 0);
  auto det_sort = run_algorithm_multipleTimes(space, iterations, false,
                                             "Deterministic Grid", "Normal", "Sorted_X_Axis");
  auto rand_sort = run_algorithm_multipleTimes(rand_space, iterations, false,
                                              "Randomized Grid", "Normal", "Sorted_X_Axis");
  print_comparison_table("2. Sorted X-Axis vs. Pre-Shuffled Stored/Loaded (" + std::to_string(iterations) + " runs)", det_sort, rand_sort);
}

// ----------------------------------------------------------------------------
// Adversarial Space Test Suite (Geometric Ladder of Decreasing Pairs)
// ----------------------------------------------------------------------------
template <size_t Dim>
void run_adversarial_space_test(size_t num_points) {
  std::cout << "\n" << std::string(90, '=') << "\n";
  std::cout << "  [ADVERSARIAL SPACE] Dimension: " << Dim << "D | Points: " << num_points << "\n";
  std::cout << std::string(90, '=') << "\n";

  auto space = Space<Dim>::get_or_create("adversarial", num_points);
  int iterations = 10;

  // 1. Adversarial Ladder of Pairs
  auto det_adv = run_algorithm_multipleTimes(space, iterations, false,
                                            "Deterministic Grid", "Adversarial", "Ladder_of_Pairs");
  auto rand_adv = run_algorithm_multipleTimes(space, iterations, true,
                                             "Randomized Grid", "Adversarial", "Ladder_of_Pairs");
  print_comparison_table("1. Adversarial Ladder of Pairs (10 runs)", det_adv, rand_adv);

  // 2. Sorted X-Axis on Adversarial Space
  space.sort_points(SortStrategy::AxisAscending, 0);
  auto det_sort = run_algorithm_multipleTimes(space, iterations, false,
                                             "Deterministic Grid", "Adversarial", "Sorted_X_Axis");
  auto rand_sort = run_algorithm_multipleTimes(space, iterations, true,
                                              "Randomized Grid", "Adversarial", "Sorted_X_Axis");
  print_comparison_table("2. Sorted X-Axis on Adversarial Space (10 runs)", det_sort, rand_sort);
}

// ----------------------------------------------------------------------------
// Dimension Drivers (Dimensions: 2D, 3D, 5D, 7D)
// ----------------------------------------------------------------------------
// ----------------------------------------------------------------------------
// Dimension Drivers (Dimensions: 2D, 3D, 5D, 7D)
// ----------------------------------------------------------------------------
template <size_t Dim> void run_all_normal_tests_for_dim(int iterations = 5) {
  std::cout << "\n" << std::string(90, '#') << "\n";
  std::cout << "  STARTING " << Dim << "D NORMAL SPACE EXPERIMENTS (50k -> 500k)\n";
  std::cout << std::string(90, '#') << "\n";
  // Uniform point counts calibrated for benchmark suite:
  const std::vector<size_t> point_counts = {50'000, 100'000, 200'000, 350'000, 500'000};
  for (size_t n : point_counts) {
    run_normal_space_test<Dim>(n, iterations);
  }
}

template <size_t Dim> void run_all_adversarial_tests_for_dim() {
  std::cout << "\n" << std::string(90, '#') << "\n";
  std::cout << "  STARTING " << Dim << "D ADVERSARIAL SPACE EXPERIMENTS (5k -> 25k)\n";
  std::cout << std::string(90, '#') << "\n";
  // Uniform point counts calibrated for quadratic rebuilds under 5 hours:
  const std::vector<size_t> point_counts = {5'000, 10'000, 15'000, 20'000, 25'000};
  for (size_t n : point_counts) {
    run_adversarial_space_test<Dim>(n);
  }
}

void print_usage(const char* prog_name) {
  cout << "Usage:\n"
       << "  " << prog_name << "                           # Run all experiments (Normal + Adversarial)\n"
       << "  " << prog_name << " normal [iterations]       # Run Normal space experiments (Pre-Shuffled Store/Load, default 5)\n"
       << "  " << prog_name << " adversarial [iterations]  # Run Adversarial space experiments\n";
}

int main(int argc, char* argv[]) {
  bool run_normal = true;
  bool run_adversarial = true;
  int iterations = 5;

  if (argc > 1) {
    string mode = argv[1];
    transform(mode.begin(), mode.end(), mode.begin(), ::tolower);

    if (mode == "normal") {
      run_normal = true;
      run_adversarial = false;
    } else if (mode == "adversarial") {
      run_normal = false;
      run_adversarial = true;
    } else if (mode == "all" || mode == "both") {
      run_normal = true;
      run_adversarial = true;
    } else if (mode == "--help" || mode == "-h") {
      print_usage(argv[0]);
      return 0;
    } else {
      cerr << "Unknown mode: " << argv[1] << "\n";
      print_usage(argv[0]);
      return 1;
    }
  }

  if (argc > 2 && std::isdigit(argv[2][0])) {
    iterations = std::max(1, std::stoi(argv[2]));
  }

  // Initialize versioned CSV file in results/ folder
  init_csv_file();

  cout << fixed << setprecision(5);
  cout << "\n================================================================================\n";
  cout << "            SCIENTIFIC CLOSEST PAIR PERFORMANCE EXPERIMENT SUITE                \n";
  cout << "================================================================================\n";
  if (run_normal && run_adversarial) {
    cout << "Mode: ALL EXPERIMENTS (Normal: 50k->500k + Adversarial: 5k->25k across 2D, 3D, 5D, 7D)\n";
  } else if (run_normal) {
    cout << "Mode: NORMAL SPACE (Pre-Shuffled Store & Load vs. Original: 50k -> 500k)\n";
  } else {
    cout << "Mode: ADVERSARIAL SPACE ONLY (Ladder of Pairs & Sorted: 5k -> 25k)\n";
  }
  cout << "Iterations per test: " << iterations << " runs\n";
  cout << "Logging results to:\n";
  cout << "  - Versioned run file : " << g_current_run_csv_filename << "\n";
  cout << "  - Primary aggregate  : experiment_results.csv\n";
  cout << "================================================================================\n\n";

  // =========================================================================
  // PHASE 1: NORMAL SPACE EXPERIMENTS (50k -> 500k across 2D, 3D, 5D, 7D)
  // =========================================================================
  if (run_normal) {
    run_all_normal_tests_for_dim<2>(iterations);
    run_all_normal_tests_for_dim<3>(iterations);
    run_all_normal_tests_for_dim<5>(iterations);
    run_all_normal_tests_for_dim<7>(iterations);
  }

  // =========================================================================
  // PHASE 2: ADVERSARIAL SPACE EXPERIMENTS (5k -> 25k across 2D, 3D, 5D, 7D)
  // =========================================================================
  if (run_adversarial) {
    run_all_adversarial_tests_for_dim<2>();
    run_all_adversarial_tests_for_dim<3>();
    run_all_adversarial_tests_for_dim<5>();
    run_all_adversarial_tests_for_dim<7>();
  }

  cout << "\n================================================================================\n";
  cout << "All selected experiments completed successfully!\n";
  cout << "Results saved to: " << g_current_run_csv_filename << "\n";
  cout << "================================================================================\n";
  return 0;
}
