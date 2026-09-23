#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "../../core/point.h"

namespace adapters::opensky {

struct OpenSkyMetadata {
  std::uint32_t flight_id{0};
  double epoch_utc{0.0};
};

using FlightPoint4D = core::Point<4, OpenSkyMetadata>;

// Strategy 2 Intra-Flight Exclusion Filter:
// 1. Skips identical aircraft (pi.flight_id == pj.flight_id)
// 2. Skips duplicate radar sensor artifacts below min_separation (default 0.05m)
struct Strategy2FlightFilter {
  static constexpr bool is_trivial = false;
  float min_separation{0.05f};

  [[nodiscard]] inline bool operator()(const FlightPoint4D &a,
                                       const FlightPoint4D &b) const noexcept {
    if (a.payload.flight_id == b.payload.flight_id) {
      return false;
    }
    if (min_separation > 0.0f) {
      return a.squared_dist(b) > (min_separation * min_separation);
    }
    return true;
  }
};

class OpenSkyAdapter {
public:
  // Converts GPS WGS-84 (lat, lon, alt) to Earth-Centered Earth-Fixed (ECEF) Cartesian (x, y, z) in meters
  static inline void wgs84_to_ecef(double lat_deg, double lon_deg, double alt_m,
                                   double &x, double &y, double &z) noexcept {
    constexpr double a = 6378137.0;          // WGS-84 semi-major axis (m)
    constexpr double f = 1.0 / 298.257223563; // Flattening
    constexpr double e2 = f * (2.0 - f);     // First eccentricity squared
    constexpr double deg2rad = 3.14159265358979323846 / 180.0;

    const double lat_rad = lat_deg * deg2rad;
    const double lon_rad = lon_deg * deg2rad;

    const double sin_lat = std::sin(lat_rad);
    const double cos_lat = std::cos(lat_rad);
    const double sin_lon = std::sin(lon_rad);
    const double cos_lon = std::cos(lon_rad);

    const double N = a / std::sqrt(1.0 - e2 * sin_lat * sin_lat);

    x = (N + alt_m) * cos_lat * cos_lon;
    y = (N + alt_m) * cos_lat * sin_lon;
    z = (N * (1.0 - e2) + alt_m) * sin_lat;
  }

  // Construct a FlightPoint4D directly from raw telemetry
  static inline FlightPoint4D make_point(double lat_deg, double lon_deg,
                                         double alt_m, double epoch_sec,
                                         double t_min, float alpha_m_s,
                                         std::uint32_t flight_id) noexcept {
    double x = 0.0, y = 0.0, z = 0.0;
    wgs84_to_ecef(lat_deg, lon_deg, alt_m, x, y, z);
    float w = static_cast<float>(alpha_m_s * (epoch_sec - t_min));

    FlightPoint4D pt;
    pt.coords = {static_cast<float>(x), static_cast<float>(y),
                 static_cast<float>(z), w};
    pt.payload = {flight_id, epoch_sec};
    return pt;
  }

  // Fast binary loader reading preprocessed OpenSky .bin files (supports OPS2 and OPSK formats, auto-detecting layout)
  static bool load_binary_dataset(const std::string &filepath,
                                  std::vector<FlightPoint4D> &points,
                                  float *out_alpha = nullptr,
                                  double *out_t_min = nullptr,
                                  std::size_t max_points = 0) {
    std::ifstream in(filepath, std::ios::binary);
    if (!in.is_open()) {
      std::cerr << "[OpenSkyAdapter] Cannot open file: " << filepath << "\n";
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
      in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
      in.read(reinterpret_cast<char *>(&count), sizeof(count));
      in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
      in.read(reinterpret_cast<char *>(&t_min), sizeof(t_min));
    } else if (magic_str == "OPSK") {
      in.read(reinterpret_cast<char *>(&file_dim), sizeof(file_dim));
      in.read(reinterpret_cast<char *>(&count), sizeof(count));
      in.read(reinterpret_cast<char *>(&alpha), sizeof(alpha));
    } else {
      std::cerr << "[OpenSkyAdapter] Error: Invalid magic in " << filepath << "\n";
      return false;
    }

    if (out_alpha) *out_alpha = alpha;
    if (out_t_min) *out_t_min = t_min;

    if (file_dim != 4) {
      std::cerr << "[OpenSkyAdapter] Dimension mismatch: expected 4, got " << file_dim << "\n";
      return false;
    }

    // Auto-detect layout from first 20-byte record:
    // Layout A (Hourly): flight_id (4B), x (4B), y (4B), z (4B), w (4B)
    // Layout B (100M/133M): x (4B), y (4B), z (4B), w (4B), flight_id (4B)
    std::array<char, 20> sample_raw{};
    in.read(sample_raw.data(), 20);
    if (!in) {
      std::cerr << "[OpenSkyAdapter] Error reading first record from " << filepath << "\n";
      return false;
    }

    std::uint32_t u_first = 0;
    std::uint32_t u_last = 0;
    std::memcpy(&u_first, sample_raw.data(), 4);
    std::memcpy(&u_last, sample_raw.data() + 16, 4);

    bool id_first = true;
    if (u_first > 0x00FFFFFF && u_last <= 0x00FFFFFF) {
      id_first = false; // coords first (x, y, z, w, id)
    }

    // Seek back to start of records (offset 28)
    in.seekg(28, std::ios::beg);

    std::size_t num_to_load = count;
    if (max_points > 0 && max_points < count) {
      num_to_load = max_points;
      std::cout << "[OpenSkyAdapter] Capping point loading to " << num_to_load
                << " of " << count << " points (via max_points limit)\n";
    }

    try {
      points.resize(num_to_load);
    } catch (const std::bad_alloc &e) {
      std::cerr << "[OpenSkyAdapter] Out of memory allocating " << num_to_load
                << " points (" << (num_to_load * sizeof(FlightPoint4D)) / (1024 * 1024)
                << " MB): " << e.what() << "\n";
      return false;
    }

    constexpr std::size_t CHUNK_SIZE = 1000000;
    std::vector<char> raw_chunk(CHUNK_SIZE * 20);
    std::size_t loaded = 0;

    while (loaded < num_to_load) {
      std::size_t batch = std::min(CHUNK_SIZE, num_to_load - loaded);
      in.read(raw_chunk.data(), static_cast<std::streamsize>(batch * 20));
      if (!in && !in.eof()) {
        std::cerr << "[OpenSkyAdapter] Error reading chunk at " << loaded << "\n";
        return false;
      }

      for (std::size_t b = 0; b < batch; ++b) {
        std::size_t idx = loaded + b;
        const char *rec = raw_chunk.data() + b * 20;

        if (id_first) {
          std::uint32_t flight_id = 0;
          std::memcpy(&flight_id, rec, 4);
          points[idx].payload.flight_id = flight_id;

          float w_coord = 0.0f;
          std::memcpy(&w_coord, rec + 16, 4);
          points[idx].payload.epoch_utc = t_min + (static_cast<double>(w_coord) / alpha);
          std::memcpy(points[idx].coords.data(), rec + 4, 16);
        } else {
          std::uint32_t flight_id = 0;
          std::memcpy(&flight_id, rec + 16, 4);
          points[idx].payload.flight_id = flight_id;

          float w_coord = 0.0f;
          std::memcpy(&w_coord, rec + 12, 4);
          points[idx].payload.epoch_utc = t_min + (static_cast<double>(w_coord) / alpha);
          std::memcpy(points[idx].coords.data(), rec, 16);
        }
      }
      loaded += batch;
    }

    std::cout << "[OpenSkyAdapter] Loaded " << num_to_load << " points from " << filepath
              << " (format: " << (id_first ? "ID-first" : "Coords-first")
              << ", alpha: " << alpha << " m/s, t_min: " << std::fixed << t_min << " s)\n";
    return true;
  }
};

} // namespace adapters::opensky
