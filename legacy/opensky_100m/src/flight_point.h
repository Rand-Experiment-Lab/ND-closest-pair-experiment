#ifndef FLIGHT_POINT_H
#define FLIGHT_POINT_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

// 4D Cartesian Point for ADS-B tracking: [x, y, z, w = alpha * (t - t_ref)]
template <std::size_t Dim>
struct FlightPoint {
  std::array<float, Dim> coordinates{};
  std::uint32_t flight_id{0};

  [[nodiscard]] inline float distance_to(const FlightPoint<Dim> &other) const noexcept {
    float sum_of_squares = 0.0f;
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coordinates[i] - other.coordinates[i];
      sum_of_squares += diff * diff;
    }
    return std::sqrt(sum_of_squares);
  }

  [[nodiscard]] inline float squared_distance_to(const FlightPoint<Dim> &other) const noexcept {
    float sum_of_squares = 0.0f;
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coordinates[i] - other.coordinates[i];
      sum_of_squares += diff * diff;
    }
    return sum_of_squares;
  }
};

template <std::size_t Dim>
using GridCell = std::array<std::int64_t, Dim>;

// 64-bit high dispersion hash function for N-D grid coordinate cells
struct ArrayHasher {
  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &a) const noexcept {
    std::size_t h = 0;
    for (std::size_t i = 0; i < Dim; ++i) {
      std::uint64_t x = static_cast<std::uint64_t>(a[i]);
      x ^= x >> 30;
      x *= 0xbf58476d1ce4e5b9ULL;
      x ^= x >> 27;
      x *= 0x94d049bb133111ebULL;
      x ^= x >> 31;
      h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    }
    return h;
  }
};

// Generates the 3^Dim neighbor offset vector (81 cells for 4D)
template <std::size_t Dim>
std::vector<GridCell<Dim>> generate_neighbor_offsets() {
  std::vector<GridCell<Dim>> offsets;
  std::size_t total_combinations = 1;
  for (std::size_t i = 0; i < Dim; ++i) {
    total_combinations *= 3;
  }
  offsets.reserve(total_combinations);

  GridCell<Dim> current_offset{};
  auto generate_recursive = [&](auto &self, std::size_t dim_index) -> void {
    if (dim_index == Dim) {
      offsets.push_back(current_offset);
      return;
    }
    for (std::int64_t val = -1; val <= 1; ++val) {
      current_offset[dim_index] = val;
      self(self, dim_index + 1);
    }
  };

  generate_recursive(generate_recursive, 0);
  return offsets;
}

// Coordinate mapping into spatial grid index with overflow guards
template <std::size_t Dim>
[[nodiscard]] inline GridCell<Dim> to_flight_grid_cell(const FlightPoint<Dim> &point,
                                                       float delta) noexcept {
  GridCell<Dim> cell{};
  const float safe_delta = std::max(delta, std::numeric_limits<float>::epsilon());
  const double inv_delta = 1.0 / static_cast<double>(safe_delta);

  constexpr double max_safe = static_cast<double>(std::numeric_limits<std::int64_t>::max() - 1000);
  constexpr double min_safe = static_cast<double>(std::numeric_limits<std::int64_t>::min() + 1000);

  for (std::size_t d = 0; d < Dim; ++d) {
    double scaled = std::floor(static_cast<double>(point.coordinates[d]) * inv_delta);
    if (std::isnan(scaled) || scaled > max_safe) {
      cell[d] = std::numeric_limits<std::int64_t>::max() - 1000;
    } else if (scaled < min_safe) {
      cell[d] = std::numeric_limits<std::int64_t>::min() + 1000;
    } else {
      cell[d] = static_cast<std::int64_t>(scaled);
    }
  }
  return cell;
}

// Header metadata from binary dataset file
struct DatasetMeta {
  std::uint32_t dim{0};
  std::uint64_t count{0};
  float alpha{0.0f};
  double t_ref{0.0};
  std::size_t file_size_bytes{0};
};

// Binary loader supporting OPS2 (4D OpenSky Binary Format with double precision t_ref)
template <std::size_t Dim>
bool load_flight_dataset_bin(const std::string &filepath,
                             std::vector<FlightPoint<Dim>> &points,
                             DatasetMeta &meta) {
  std::ifstream in(filepath, std::ios::binary);
  if (!in.is_open()) {
    std::cerr << "[Error] Cannot open binary file: " << filepath << "\n";
    return false;
  }

  in.seekg(0, std::ios::end);
  meta.file_size_bytes = static_cast<std::size_t>(in.tellg());
  in.seekg(0, std::ios::beg);

  char magic[4];
  in.read(magic, 4);
  std::string magic_str(magic, 4);

  if (magic_str != "OPS2" && magic_str != "OPS1") {
    std::cerr << "[Error] Invalid magic header '" << magic_str << "'! Expected 'OPS2'.\n";
    return false;
  }

  std::uint32_t file_dim = 0;
  std::uint64_t count = 0;
  float alpha = 0.0f;
  double t_ref = 0.0;

  if (magic_str == "OPS2") {
    in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
    in.read(reinterpret_cast<char *>(&count), sizeof(count));
    in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
    in.read(reinterpret_cast<char *>(&t_ref), sizeof(t_ref));
  } else {
    // OPS1 legacy format
    in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
    in.read(reinterpret_cast<char *>(&count), sizeof(count));
    in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
    t_ref = 0.0;
  }

  if (file_dim != Dim) {
    std::cerr << "[Error] Dimension mismatch: file has Dim=" << file_dim
              << ", expected Dim=" << Dim << "\n";
    return false;
  }

  meta.dim = file_dim;
  meta.count = count;
  meta.alpha = alpha;
  meta.t_ref = t_ref;

  std::cout << "[Dataset Loader] Found " << count << " points (Dim=" << file_dim
            << ", Alpha=" << alpha << " m/s, t_ref=" << std::fixed << t_ref << ")\n";

  try {
    points.resize(count);
  } catch (const std::bad_alloc &e) {
    std::cerr << "[Fatal Error] Out of Memory! Failed to allocate vector for "
              << count << " points (" << (count * sizeof(FlightPoint<Dim>)) / (1024 * 1024)
              << " MB): " << e.what() << "\n";
    return false;
  }

  in.read(reinterpret_cast<char *>(points.data()), count * sizeof(FlightPoint<Dim>));
  if (!in) {
    std::cerr << "[Error] Failed to read full point data from " << filepath << "\n";
    return false;
  }

  return true;
}

#endif // FLIGHT_POINT_H
