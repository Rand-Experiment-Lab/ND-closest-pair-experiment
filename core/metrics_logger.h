#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

namespace core {

struct SummaryStats {
  double mean{0.0};
  double median{0.0};
  double std_dev{0.0};
};

inline SummaryStats compute_stats(std::vector<double> values) {
  SummaryStats stats;
  if (values.empty()) return stats;

  const std::size_t n = values.size();
  double sum = std::accumulate(values.begin(), values.end(), 0.0);
  stats.mean = sum / static_cast<double>(n);

  double var_sum = 0.0;
  for (double v : values) {
    var_sum += (v - stats.mean) * (v - stats.mean);
  }
  stats.std_dev = std::sqrt(var_sum / static_cast<double>(n > 1 ? n - 1 : 1));

  std::sort(values.begin(), values.end());
  if (n % 2 == 0) {
    stats.median = (values[n / 2 - 1] + values[n / 2]) / 2.0;
  } else {
    stats.median = values[n / 2];
  }
  return stats;
}

inline std::string get_current_iso_timestamp() {
  std::time_t t = std::time(nullptr);
  char buf[64];
  if (std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&t))) {
    return std::string(buf);
  }
  return "1970-01-01 00:00:00";
}

inline std::string get_timestamp_file_tag() {
  std::time_t t = std::time(nullptr);
  char buf[64];
  if (std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", std::localtime(&t))) {
    return std::string(buf);
  }
  return "run";
}

class MetricsLogger {
public:
  static constexpr const char *CSV_HEADER =
      "Timestamp,Benchmark_Type,Dataset_Name,Dimensions,Num_Points,Input_Order,"
      "Algorithm,Iterations,Min_Distance,Mean_Time_ms,Median_Time_ms,StdDev_Time_ms,"
      "Mean_Rebuilds,Median_Rebuilds,StdDev_Rebuilds,Raw_Times_ms,Extra_Metadata_JSON\n";

  static void log_record(const std::string &filepath,
                         const std::string &benchmark_type,
                         const std::string &dataset_name,
                         std::size_t dimensions,
                         std::size_t num_points,
                         const std::string &input_order,
                         const std::string &algorithm,
                         int iterations,
                         float min_distance,
                         const std::vector<double> &raw_times_ms,
                         const std::vector<std::size_t> &raw_rebuilds,
                         const std::string &extra_metadata_json = "{}") {
    std::filesystem::path p(filepath);
    if (p.has_parent_path()) {
      std::filesystem::create_directories(p.parent_path());
    }

    bool file_exists = std::filesystem::exists(filepath);
    std::ofstream out(filepath, std::ios::app);
    if (!file_exists || std::filesystem::file_size(filepath) == 0) {
      out << CSV_HEADER;
    }

    SummaryStats time_stats = compute_stats(raw_times_ms);

    std::vector<double> rebuild_doubles(raw_rebuilds.begin(), raw_rebuilds.end());
    SummaryStats rebuild_stats = compute_stats(rebuild_doubles);

    // Format raw times array as a JSON string
    std::ostringstream raw_times_ss;
    raw_times_ss << "\"[";
    for (std::size_t i = 0; i < raw_times_ms.size(); ++i) {
      raw_times_ss << std::fixed << std::setprecision(5) << raw_times_ms[i];
      if (i + 1 < raw_times_ms.size()) raw_times_ss << ", ";
    }
    raw_times_ss << "]\"";

    out << get_current_iso_timestamp() << ","
        << benchmark_type << ","
        << dataset_name << ","
        << dimensions << ","
        << num_points << ","
        << input_order << ","
        << algorithm << ","
        << iterations << ","
        << std::fixed << std::setprecision(5) << min_distance << ","
        << std::fixed << std::setprecision(5) << time_stats.mean << ","
        << std::fixed << std::setprecision(5) << time_stats.median << ","
        << std::fixed << std::setprecision(5) << time_stats.std_dev << ","
        << std::fixed << std::setprecision(2) << rebuild_stats.mean << ","
        << std::fixed << std::setprecision(2) << rebuild_stats.median << ","
        << std::fixed << std::setprecision(2) << rebuild_stats.std_dev << ","
        << raw_times_ss.str() << ","
        << "\"" << escape_json_for_csv(extra_metadata_json) << "\"\n";
  }

private:
  static std::string escape_json_for_csv(const std::string &json) {
    std::string escaped;
    for (char c : json) {
      if (c == '"') escaped += "\"\"";
      else escaped += c;
    }
    return escaped;
  }
};

} // namespace core
