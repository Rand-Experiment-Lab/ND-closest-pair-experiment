#ifndef CLOSEST_PAIR_100M_H
#define CLOSEST_PAIR_100M_H

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#include "flight_point.h"

// Pair information holding the closest encounter details
template <std::size_t Dim>
struct EncounterResult {
  float distance{std::numeric_limits<float>::infinity()};
  FlightPoint<Dim> p1{};
  FlightPoint<Dim> p2{};
  std::size_t rebuild_count{0};
  double execution_time_ms{0.0};
};

template <std::size_t Dim>
using FlightHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<FlightPoint<Dim>>, ArrayHasher>;

// Inter-flight neighbor cell search:
// 1. Skips points from the same aircraft (pi.flight_id == point.flight_id)
// 2. Skips non-physical sensor duplicates (dist <= min_separation)
template <std::size_t Dim>
[[nodiscard]] inline float find_min_in_neighbor_cells(
    const GridCell<Dim> &center_cell, const FlightHashMap<Dim> &grid_map,
    const FlightPoint<Dim> &pi, const std::vector<GridCell<Dim>> &neighbor_offsets,
    FlightPoint<Dim> *out_partner = nullptr, float min_separation = 0.05f) {
  float min_dist = std::numeric_limits<float>::infinity();

  for (const auto &offset : neighbor_offsets) {
    GridCell<Dim> neighbor_cell;
    for (std::size_t d = 0; d < Dim; ++d) {
      neighbor_cell[d] = center_cell[d] + offset[d];
    }

    auto it = grid_map.find(neighbor_cell);
    if (it != grid_map.end()) {
      for (const auto &point : it->second) {
        if (pi.flight_id == point.flight_id) {
          continue; // Ignore intra-flight telemetry
        }

        float dist = pi.distance_to(point);
        if (dist <= min_separation) {
          continue; // Filter sensor artifacts
        }

        if (dist < min_dist) {
          min_dist = dist;
          if (out_partner) {
            *out_partner = point;
          }
        }
      }
    }
  }
  return min_dist;
}

// Format duration helper (e.g. 14m 23s)
inline std::string format_seconds(double total_sec) {
  std::size_t s = static_cast<std::size_t>(total_sec);
  std::size_t mins = s / 60;
  std::size_t secs = s % 60;
  std::ostringstream oss;
  if (mins > 0) {
    oss << mins << "m " << std::setw(2) << std::setfill('0') << secs << "s";
  } else {
    oss << std::fixed << std::setprecision(1) << total_sec << "s";
  }
  return oss.str();
}

// ---------------------------------------------------------------------------
// 1. Deterministic Incremental Grid Closest Pair Algorithm (Original Order)
// ---------------------------------------------------------------------------
// Zero-overhead progress tracking using __builtin_expect branch prediction hint
template <std::size_t Dim>
[[nodiscard]] EncounterResult<Dim>
find_closest_pair_deterministic(const std::vector<FlightPoint<Dim>> &points,
                                float min_separation = 0.05f,
                                bool show_progress = true,
                                double progress_interval_pct = 5.0) {
  EncounterResult<Dim> res;
  const std::size_t size = points.size();
  if (size < 2) {
    return res;
  }

  const auto neighbor_offsets = generate_neighbor_offsets<Dim>();

  // Determine initial delta from the first distinct aircraft pair
  float delta = std::numeric_limits<float>::infinity();
  for (std::size_t i = 1; i < size; ++i) {
    if (points[i].flight_id != points[0].flight_id) {
      float d = points[0].distance_to(points[i]);
      if (d > min_separation) {
        delta = d;
        res.p1 = points[0];
        res.p2 = points[i];
        break;
      }
    }
  }

  if (delta == std::numeric_limits<float>::infinity() ||
      delta <= std::numeric_limits<float>::epsilon()) {
    delta = 10000.0f; // 10 km fallback
  }

  res.distance = delta;
  FlightHashMap<Dim> grid_map;

  // Zero-overhead progress checkpoint setup (updates every 5%)
  const std::size_t step_interval = (size >= 20) ? static_cast<std::size_t>((progress_interval_pct / 100.0) * size) : size;
  std::size_t next_milestone = step_interval;

  const auto start_time = std::chrono::steady_clock::now();

  for (std::size_t i = 0; i < size; ++i) {
    const auto &pi = points[i];
    GridCell<Dim> cell_i = to_flight_grid_cell(pi, delta);

    FlightPoint<Dim> partner{};
    float min_dist = find_min_in_neighbor_cells(
        cell_i, grid_map, pi, neighbor_offsets, &partner, min_separation);

    grid_map[cell_i].push_back(pi);

    // Rebuild hash grid when a strictly closer valid encounter is found
    if (min_dist < delta && min_dist > min_separation) {
      res.rebuild_count++;
      delta = min_dist;
      res.distance = delta;
      res.p1 = pi;
      res.p2 = partner;

      grid_map.clear();
      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[j];
        grid_map[to_flight_grid_cell(pj, delta)].push_back(pj);
      }
    }

    // Zero-overhead progress check: branch predictor assumes not taken (99.99999% false)
    if (show_progress && __builtin_expect(i >= next_milestone, 0)) {
      const auto now = std::chrono::steady_clock::now();
      double elapsed_sec = std::chrono::duration<double>(now - start_time).count();
      double pct = (static_cast<double>(i + 1) / static_cast<double>(size)) * 100.0;
      double eta_sec = (i > 0) ? (elapsed_sec * (size - i - 1) / (i + 1)) : 0.0;

      std::cout << "  [Progress " << std::fixed << std::setprecision(1) << pct << "%] "
                << (i + 1) / 1000000 << "M/" << size / 1000000 << "M pts | Min Dist: "
                << std::setprecision(3) << delta << " m | Rebuilds: " << res.rebuild_count
                << " | Elapsed: " << format_seconds(elapsed_sec)
                << " | ETA: " << format_seconds(eta_sec) << std::endl;

      next_milestone += step_interval;
    }
  }

  const auto end_time = std::chrono::steady_clock::now();
  res.execution_time_ms =
      std::chrono::duration<double, std::milli>(end_time - start_time).count();

  return res;
}

// ---------------------------------------------------------------------------
// 2. Randomized Incremental Grid Closest Pair Algorithm (Original Order + Shuffled Permutation)
// ---------------------------------------------------------------------------
// To avoid deep-copying 100M structs (saving 2 GB RAM), we shuffle index pointers
template <std::size_t Dim>
[[nodiscard]] EncounterResult<Dim>
find_closest_pair_randomized(const std::vector<FlightPoint<Dim>> &points,
                             std::uint64_t seed,
                             float min_separation = 0.05f,
                             bool show_progress = true,
                             double progress_interval_pct = 5.0) {
  EncounterResult<Dim> res;
  const std::size_t size = points.size();
  if (size < 2) {
    return res;
  }

  // Create an index permutation vector: size * 4 bytes = 400 MB (much cheaper than 2 GB point vector)
  std::vector<std::size_t> indices(size);
  for (std::size_t i = 0; i < size; ++i) {
    indices[i] = i;
  }
  std::mt19937_64 rng(seed);
  std::shuffle(indices.begin(), indices.end(), rng);

  const auto neighbor_offsets = generate_neighbor_offsets<Dim>();

  // Determine initial delta
  float delta = std::numeric_limits<float>::infinity();
  const auto &p0 = points[indices[0]];
  for (std::size_t i = 1; i < size; ++i) {
    const auto &pi = points[indices[i]];
    if (pi.flight_id != p0.flight_id) {
      float d = p0.distance_to(pi);
      if (d > min_separation) {
        delta = d;
        res.p1 = p0;
        res.p2 = pi;
        break;
      }
    }
  }

  if (delta == std::numeric_limits<float>::infinity() ||
      delta <= std::numeric_limits<float>::epsilon()) {
    delta = 10000.0f;
  }

  res.distance = delta;
  FlightHashMap<Dim> grid_map;

  const std::size_t step_interval = (size >= 20) ? static_cast<std::size_t>((progress_interval_pct / 100.0) * size) : size;
  std::size_t next_milestone = step_interval;

  const auto start_time = std::chrono::steady_clock::now();

  for (std::size_t i = 0; i < size; ++i) {
    const auto &pi = points[indices[i]];
    GridCell<Dim> cell_i = to_flight_grid_cell(pi, delta);

    FlightPoint<Dim> partner{};
    float min_dist = find_min_in_neighbor_cells(
        cell_i, grid_map, pi, neighbor_offsets, &partner, min_separation);

    grid_map[cell_i].push_back(pi);

    if (min_dist < delta && min_dist > min_separation) {
      res.rebuild_count++;
      delta = min_dist;
      res.distance = delta;
      res.p1 = pi;
      res.p2 = partner;

      grid_map.clear();
      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[indices[j]];
        grid_map[to_flight_grid_cell(pj, delta)].push_back(pj);
      }
    }

    if (show_progress && __builtin_expect(i >= next_milestone, 0)) {
      const auto now = std::chrono::steady_clock::now();
      double elapsed_sec = std::chrono::duration<double>(now - start_time).count();
      double pct = (static_cast<double>(i + 1) / static_cast<double>(size)) * 100.0;
      double eta_sec = (i > 0) ? (elapsed_sec * (size - i - 1) / (i + 1)) : 0.0;

      std::cout << "  [Progress " << std::fixed << std::setprecision(1) << pct << "%] "
                << (i + 1) / 1000000 << "M/" << size / 1000000 << "M pts | Min Dist: "
                << std::setprecision(3) << delta << " m | Rebuilds: " << res.rebuild_count
                << " | Elapsed: " << format_seconds(elapsed_sec)
                << " | ETA: " << format_seconds(eta_sec) << std::endl;

      next_milestone += step_interval;
    }
  }

  const auto end_time = std::chrono::steady_clock::now();
  res.execution_time_ms =
      std::chrono::duration<double, std::milli>(end_time - start_time).count();

  return res;
}

#endif // CLOSEST_PAIR_100M_H
