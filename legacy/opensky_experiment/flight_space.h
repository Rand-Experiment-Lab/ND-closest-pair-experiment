#ifndef FLIGHT_SPACE_H
#define FLIGHT_SPACE_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <execution>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <span>
#include <string>
#include <vector>

#include "../space.h"

// Tagged Point for OpenSky flight tracking:
// Contains coordinates [x, y, z, alpha * (t - t_min)] in meters, plus a unique flight_id
template <std::size_t Dim>
struct FlightPoint {
  std::array<float, Dim> coordinates{};
  std::uint32_t flight_id{0};

  [[nodiscard]] float distance_to(const FlightPoint<Dim> &other) const noexcept {
    float sum_of_squares = 0.0f;
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coordinates[i] - other.coordinates[i];
      sum_of_squares += diff * diff;
    }
    return std::sqrt(sum_of_squares);
  }
};

// Binary loader for OpenSky preprocessed .bin files
// Safely reads t_min (double precision) and alpha
template <std::size_t Dim>
bool load_flight_points_from_bin(const std::string &filepath,
                                 std::vector<FlightPoint<Dim>> &points,
                                 float *out_alpha = nullptr,
                                 double *out_t_min = nullptr) {
  std::ifstream in(filepath, std::ios::binary);
  if (!in.is_open()) {
    std::cerr << "[FlightIO] Cannot open binary file: " << filepath << "\n";
    return false;
  }

  char magic[4];
  in.read(magic, 4);
  std::string magic_str(magic, 4);

  std::uint32_t file_dim = 0;
  std::uint64_t count = 0;
  float alpha = 0.0f;
  double t_min = 0.0;

  if (magic_str == "OPS2") {
    // Format v2: includes double t_min
    in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
    in.read(reinterpret_cast<char *>(&count), sizeof(count));
    in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
    in.read(reinterpret_cast<char *>(&t_min), sizeof(t_min));
  } else if (magic_str == "OPSK") {
    // Format v1 legacy fallback
    in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
    in.read(reinterpret_cast<char *>(&count), sizeof(count));
    in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
  } else {
    std::cerr << "[FlightIO] Error: Invalid magic bytes in " << filepath << " (expected 'OPS2' or 'OPSK')\n";
    return false;
  }

  if (out_alpha) {
    *out_alpha = alpha;
  }
  if (out_t_min) {
    *out_t_min = t_min;
  }

  if (file_dim != Dim) {
    std::cerr << "[FlightIO] Dimension mismatch: file has " << file_dim << ", program expects " << Dim << "\n";
    return false;
  }

  points.resize(count);

#pragma pack(push, 1)
  struct BinaryRecord {
    std::uint32_t id;
    float coords[Dim];
  };
#pragma pack(pop)

  std::vector<BinaryRecord> buffer(count);
  in.read(reinterpret_cast<char *>(buffer.data()), count * sizeof(BinaryRecord));
  if (!in.good()) {
    std::cerr << "[FlightIO] Error reading binary payload from " << filepath << "\n";
    return false;
  }

  for (std::size_t i = 0; i < count; ++i) {
    points[i].flight_id = buffer[i].id;
    for (std::size_t d = 0; d < Dim; ++d) {
      points[i].coordinates[d] = buffer[i].coords[d];
    }
  }

  std::cout << "[FlightIO] Successfully loaded " << count << " points from " << filepath
            << " (alpha: " << alpha << " m/s, t_min: " << std::fixed << std::setprecision(1) << t_min << " s)\n";
  return true;
}

#endif // FLIGHT_SPACE_H
