#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
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

  // Fast binary loader reading preprocessed OpenSky .bin files (supports OPS2 and OPSK formats)
  static bool load_binary_dataset(const std::string &filepath,
                                  std::vector<FlightPoint4D> &points,
                                  float *out_alpha = nullptr,
                                  double *out_t_min = nullptr) {
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

    points.resize(count);

#pragma pack(push, 1)
    struct BinaryRecord {
      std::uint32_t id;
      float coords[4];
    };
#pragma pack(pop)

    std::vector<BinaryRecord> buffer(count);
    in.read(reinterpret_cast<char *>(buffer.data()), count * sizeof(BinaryRecord));
    if (!in.good()) {
      std::cerr << "[OpenSkyAdapter] Error reading payload from " << filepath << "\n";
      return false;
    }

    for (std::size_t i = 0; i < count; ++i) {
      points[i].payload.flight_id = buffer[i].id;
      points[i].payload.epoch_utc = t_min + (static_cast<double>(buffer[i].coords[3]) / alpha);
      for (std::size_t d = 0; d < 4; ++d) {
        points[i].coords[d] = buffer[i].coords[d];
      }
    }

    std::cout << "[OpenSkyAdapter] Loaded " << count << " points from " << filepath
              << " (alpha: " << alpha << " m/s, t_min: " << t_min << " s)\n";
    return true;
  }
};

} // namespace adapters::opensky
