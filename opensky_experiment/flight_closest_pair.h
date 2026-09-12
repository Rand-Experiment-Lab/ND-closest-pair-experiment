#ifndef FLIGHT_CLOSEST_PAIR_H
#define FLIGHT_CLOSEST_PAIR_H

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <span>
#include <unordered_map>
#include <vector>

#include "flight_space.h"
#include "../closest_pair.h"

// Pair information holding the closest encounter details
template <std::size_t Dim>
struct FlightEncounter {
  float distance{std::numeric_limits<float>::infinity()};
  FlightPoint<Dim> p1{};
  FlightPoint<Dim> p2{};
  std::size_t rebuild_count{0};
};

template <std::size_t Dim>
using FlightGridHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<FlightPoint<Dim>>, ArrayHasher>;

// Maps a 4D FlightPoint coordinates to its corresponding grid cell index
template <std::size_t Dim>
[[nodiscard]] inline GridCell<Dim> to_flight_grid_cell(const FlightPoint<Dim> &point,
                                                       float delta) noexcept {
  GridCell<Dim> cell{};
  const float safe_delta = std::max(delta, std::numeric_limits<float>::epsilon());
  const double inv_delta = 1.0 / static_cast<double>(safe_delta);

  constexpr double max_safe_int = static_cast<double>(std::numeric_limits<std::int64_t>::max() - 1000);
  constexpr double min_safe_int = static_cast<double>(std::numeric_limits<std::int64_t>::min() + 1000);

  for (std::size_t d = 0; d < Dim; ++d) {
    double scaled = std::floor(static_cast<double>(point.coordinates[d]) * inv_delta);
    if (std::isnan(scaled) || scaled > max_safe_int) {
      cell[d] = std::numeric_limits<std::int64_t>::max() - 1000;
    } else if (scaled < min_safe_int) {
      cell[d] = std::numeric_limits<std::int64_t>::min() + 1000;
    } else {
      cell[d] = static_cast<std::int64_t>(scaled);
    }
  }
  return cell;
}

// Inter-flight neighbor cell search with optional min_separation threshold:
// 1. Skips identical aircraft (pi.flight_id == point.flight_id)
// 2. Skips non-physical duplicate sensor artifacts below min_separation (e.g. d <= 0.05m)
template <std::size_t Dim>
[[nodiscard]] float find_min_in_neighbor_cells_flight(
    const GridCell<Dim> &center_cell, const FlightGridHashMap<Dim> &grid_map,
    const FlightPoint<Dim> &pi, const std::vector<GridCell<Dim>> &neighbor_offsets,
    FlightPoint<Dim> *out_closest_partner = nullptr,
    float min_separation = 0.0f) {
  float min_dist = std::numeric_limits<float>::infinity();

  for (const auto &offset : neighbor_offsets) {
    GridCell<Dim> neighbor_cell;
    for (std::size_t d = 0; d < Dim; ++d) {
      neighbor_cell[d] = center_cell[d] + offset[d];
    }

    auto it = grid_map.find(neighbor_cell);
    if (it != grid_map.end()) {
      for (const auto &point : it->second) {
        // STRATEGY 2: Skip identical aircraft!
        if (pi.flight_id == point.flight_id) {
          continue;
        }

        float dist = pi.distance_to(point);

        // Optional filter: Ignore sensor artifacts / duplicates below min_separation
        if (dist <= min_separation) {
          continue;
        }

        if (dist < min_dist) {
          min_dist = dist;
          if (out_closest_partner) {
            *out_closest_partner = point;
          }
        }
      }
    }
  }
  return min_dist;
}

// Incremental grid-based 4D closest pair with intra-flight exclusion
// min_separation: minimum physical distance threshold (default: 0.0f = accept all)
template <std::size_t Dim>
[[nodiscard]] FlightEncounter<Dim>
find_min_dist_flight_grid(std::span<const FlightPoint<Dim>> points,
                          float min_separation = 0.0f,
                          bool verbose = false) {
  FlightEncounter<Dim> encounter;
  const std::size_t size = points.size();
  if (size < 2) {
    return encounter;
  }

  const auto neighbor_offsets = generate_neighbor_offsets<Dim>();

  // Find initial inter-flight delta between first two distinct aircraft
  float delta = std::numeric_limits<float>::infinity();
  for (std::size_t i = 1; i < size; ++i) {
    if (points[i].flight_id != points[0].flight_id) {
      float d = points[0].distance_to(points[i]);
      if (d > min_separation) {
        delta = d;
        encounter.p1 = points[0];
        encounter.p2 = points[i];
        break;
      }
    }
  }

  if (delta == std::numeric_limits<float>::infinity() || delta <= std::numeric_limits<float>::epsilon()) {
    delta = 10000.0f; // Fallback initial delta in meters (10 km)
  }

  encounter.distance = delta;
  FlightGridHashMap<Dim> grid_map;

  for (std::size_t i = 0; i < size; ++i) {
    const auto &pi = points[i];
    GridCell<Dim> cell_i = to_flight_grid_cell(pi, delta);

    FlightPoint<Dim> closest_partner{};
    float min_dist = find_min_in_neighbor_cells_flight(
        cell_i, grid_map, pi, neighbor_offsets, &closest_partner, min_separation);

    grid_map[cell_i].push_back(pi);

    // Only rebuild if we found a strictly closer VALID encounter
    if (min_dist < delta && min_dist > min_separation) {
      encounter.rebuild_count++;
      delta = min_dist;
      encounter.distance = delta;
      encounter.p1 = pi;
      encounter.p2 = closest_partner;

      if (verbose) {
        std::cout << "[FlightGrid] Step " << i << " | New Min Dist: " << delta
                  << " m between Flight " << encounter.p1.flight_id
                  << " and Flight " << encounter.p2.flight_id
                  << " -> Rebuilding..." << std::endl;
      }

      grid_map.clear();

      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[j];
        grid_map[to_flight_grid_cell(pj, delta)].push_back(pj);
      }
    }
  }

  return encounter;
}

#endif // FLIGHT_CLOSEST_PAIR_H
