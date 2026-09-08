#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <vector>

#include "closest_pair.h"
#include "space.h"

using namespace std;

std::string current_timestamp() {
  std::time_t t = std::time(nullptr);
  char mbstr[100];
  if (std::strftime(mbstr, sizeof(mbstr), "%Y-%m-%d %H:%M:%S",
                    std::localtime(&t))) {
    return mbstr;
  }
  return "Unknown";
}

struct Stats {
  double mean;
  double median;
  double std_dev;
};

void log_to_csv(const std::string &space_type, size_t dim, size_t num_points,
                const std::string &input_order, std::string algorithm,
                int iterations, float min_dist, const Stats &time_st,
                const std::vector<double> &raw_times,
                const Stats &rebuild_st,
                const std::vector<size_t> &raw_rebuilds) {
  std::string filename = "experiment_results.csv";
  std::ifstream check_file(filename);
  bool file_exists = check_file.good();
  bool has_rebuild_header = false;
  if (file_exists) {
    std::string header_line;
    if (std::getline(check_file, header_line)) {
      if (header_line.find("Mean_Rebuilds") != std::string::npos) {
        has_rebuild_header = true;
      }
    }
  }
  check_file.close();

  // If the file exists but has the older CSV header without rebuild columns,
  // migrate existing rows so column counts remain consistent for CSV parsers.
  if (file_exists && !has_rebuild_header) {
    std::ifstream in(filename);
    std::vector<std::string> lines;
    std::string line;
    bool is_first = true;
    while (std::getline(in, line)) {
      if (line.empty()) continue;
      if (is_first) {
        lines.push_back(line + ",Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds");
        is_first = false;
      } else {
        lines.push_back(line + ",\"\",\"\",\"\",\"\"");
      }
    }
    in.close();

    std::ofstream out(filename, std::ios::trunc);
    for (const auto &l : lines) {
      out << l << "\n";
    }
    out.close();
  }

  std::ofstream file(filename, std::ios::app);
  if (!file_exists) {
    file << "Timestamp,Space_Type,Dimensions,Num_Points,Input_Order,Algorithm,"
            "Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_"
            "ms,Raw_Times_ms,Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Rebuilds\n";
  }

  algorithm.erase(algorithm.find_last_not_of(" ") + 1);

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

  file << current_timestamp() << "," << space_type << "," << dim << ","
       << num_points << "," << input_order << "," << algorithm << ","
       << iterations << "," << std::fixed << std::setprecision(5) << min_dist
       << "," << std::fixed << std::setprecision(5) << time_st.mean << ","
       << std::fixed << std::setprecision(5) << time_st.median << "," << std::fixed
       << std::setprecision(5) << time_st.std_dev << "," << raw_ss.str() << ","
       << std::fixed << std::setprecision(5) << rebuild_st.mean << ","
       << std::fixed << std::setprecision(5) << rebuild_st.median << "," << std::fixed
       << std::setprecision(5) << rebuild_st.std_dev << "," << rebuilds_ss.str() << "\n";
}

template <typename T>
Stats compute_statistics(const std::vector<T> &values) {
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

template <size_t Dim, size_t NumPoints>
float run_algorithm_multipleTimes(Space<Dim, NumPoints> &s, int k, bool isRand,
                                  const string &label, const string &space_type,
                                  const string &input_order) {
  std::vector<double> execution_times;
  execution_times.reserve(k);
  std::vector<size_t> rebuild_counts;
  rebuild_counts.reserve(k);
  float min_val = 0.0f;

  for (int i = 0; i < k; i++) {
    size_t rebuilds = 0;
    auto start = chrono::high_resolution_clock::now();
    if (isRand) {
      TimePoint inner_start;
      min_val = find_min_dist_grid_based_randomized(s, &inner_start, false, &rebuilds);
      start = inner_start;
    } else {
      min_val = find_min_dist_grid_based(s, false, &rebuilds);
    }
    auto end = chrono::high_resolution_clock::now();
    chrono::duration<double, milli> ms = end - start;
    execution_times.push_back(ms.count());
    rebuild_counts.push_back(rebuilds);
  }

  Stats time_st = compute_statistics(execution_times);
  Stats rebuild_st = compute_statistics(rebuild_counts);

  std::cout << "  > " << label << " | Min Dist: " << min_val << "\n";
  std::cout << "    Execution Time (ms):\n";
  std::cout << "      Mean     : " << time_st.mean << " ms\n";
  std::cout << "      Median   : " << time_st.median << " ms\n";
  std::cout << "      Std Dev  : " << time_st.std_dev << " ms\n";
  std::cout << "    Grid Rebuilds:\n";
  std::cout << "      Mean     : " << rebuild_st.mean << "\n";
  std::cout << "      Median   : " << rebuild_st.median << "\n";
  std::cout << "      Std Dev  : " << rebuild_st.std_dev << "\n";
  std::cout << "\n";

  log_to_csv(space_type, Dim, NumPoints, input_order, label, k, min_val,
             time_st, execution_times, rebuild_st, rebuild_counts);

  return min_val;
}

template <size_t Dim, size_t NumPoints>
void run_normal_space_test(const string &test_name, int iterations = 3) {
  cout << "==============================================================================\n";
  cout << "[NORMAL SPACE] " << test_name << " [" << NumPoints << " points in " << Dim << "D]\n";
  cout << "==============================================================================\n";

  auto space = Space<Dim, NumPoints>::get_or_create("uniform");

  cout << "--- 1. Original Generation Order ---\n";
  run_algorithm_multipleTimes(space, iterations, false, "Deterministic Grid", "Normal", "Original");
  run_algorithm_multipleTimes(space, iterations, true, "Randomized Grid   ", "Normal", "Original");

  cout << "--- 2. Sorted Order (Axis Ascending) ---\n";
  space.sort_points(SortStrategy::AxisAscending, 0);
  run_algorithm_multipleTimes(space, iterations, false, "Deterministic Grid", "Normal", "Sorted_X_Axis");
  run_algorithm_multipleTimes(space, iterations, true, "Randomized Grid   ", "Normal", "Sorted_X_Axis");
}

template <size_t Dim, size_t NumPoints>
void run_adversarial_space_test(const string &test_name, int iterations = 3) {
  cout << "==============================================================================\n";
  cout << "[ADVERSARIAL SPACE] " << test_name << " [" << NumPoints << " points in " << Dim << "D]\n";
  cout << "==============================================================================\n";

  auto space = Space<Dim, NumPoints>::get_or_create("adversarial");

  cout << "--- 1. Adversarial Generation Order ---\n";
  run_algorithm_multipleTimes(space, iterations, false, "Deterministic Grid", "Adversarial", "Ladder_of_Pairs");
  run_algorithm_multipleTimes(space, iterations, true, "Randomized Grid   ", "Adversarial", "Ladder_of_Pairs");
}

void print_usage(const char* prog_name) {
  cout << "Usage:\n"
       << "  " << prog_name << "               # Run all quick experiments (Normal + Adversarial)\n"
       << "  " << prog_name << " normal        # Run only Normal space quick experiments\n"
       << "  " << prog_name << " adversarial   # Run only Adversarial space quick experiments\n";
}

int main(int argc, char* argv[]) {
  bool run_normal = true;
  bool run_adversarial = true;

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

  cout << fixed << setprecision(5);
  cout << "\n=== Running Quick Closest Pair Experiment (Verification) ===\n";
  if (run_normal && run_adversarial) {
    cout << "Mode: ALL QUICK EXPERIMENTS (Normal + Adversarial)\n";
  } else if (run_normal) {
    cout << "Mode: NORMAL SPACE ONLY\n";
  } else {
    cout << "Mode: ADVERSARIAL SPACE ONLY\n";
  }
  cout << "Testing dataset creation / loading and algorithm execution...\n\n";

  int iters = 3;

  if (run_normal) {
    run_normal_space_test<2, 2000>("2D Small Set", iters);
    run_normal_space_test<3, 2000>("3D Small Set", iters);
  }

  if (run_adversarial) {
    run_adversarial_space_test<2, 2000>("2D Small Set", iters);
    run_adversarial_space_test<3, 2000>("3D Small Set", iters);
  }

  cout << "\nQuick experiment completed successfully!\n";
  return 0;
}
