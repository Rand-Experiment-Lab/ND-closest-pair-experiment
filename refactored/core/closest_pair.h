#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <random>
#include <span>
#include <vector>

#include "hash_grid.h"
#include "point.h"

namespace core {

using TimePoint = std::chrono::time_point<std::chrono::high_resolution_clock>;

template <typename PointType>
struct ClosestPairResult {
  float min_distance{std::numeric_limits<float>::infinity()};
  PointType p1{};
  PointType p2{};
  std::size_t rebuild_count{0};
  std::size_t rebuild_work{0}; // Sum of (i + 1) points re-inserted across all rebuilds
  std::vector<std::size_t> rebuild_indices{}; // Exact insertion indices where rebuilds triggered
  double execution_time_ms{0.0};
};

struct DefaultPairFilter {
  static constexpr bool is_trivial = true;
  template <typename P>
  [[nodiscard]] constexpr bool operator()(const P &, const P &) const noexcept {
    return true;
  }
};

/**
 * @brief Core Closest Pair Engine using Rabin's Hash Grid
 *
 * @tparam Dim Spatial dimensionality
 * @tparam PointType Concrete point structure (e.g. Point<Dim, Payload>)
 * @tparam Filter Callable policy to accept/reject candidate pairs
 */
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
[[nodiscard]] ClosestPairResult<PointType>
find_closest_pair_grid(std::span<const PointType> points,
                       Filter filter = Filter{},
                       bool verbose = false) {
  ClosestPairResult<PointType> result;
  result.rebuild_indices.reserve(64); // Pre-allocate to prevent any reallocations
  const std::size_t n = points.size();

  if (n < 2) {
    result.min_distance = 0.0f;
    return result;
  }

  // Precompute 3^Dim neighbor cell offsets once
  static const std::vector<GridCell<Dim>> neighbor_offsets =
      compute_neighbor_offsets<Dim>();

  // Find the first valid pair to establish initial delta
  float delta = std::numeric_limits<float>::infinity();
  std::size_t first_pair_i = 0;
  std::size_t first_pair_j = 1;
  bool found_first_pair = false;

  for (std::size_t i = 0; i < n && !found_first_pair; ++i) {
    for (std::size_t j = i + 1; j < n && !found_first_pair; ++j) {
      if constexpr (!Filter::is_trivial) {
        if (!filter(points[i], points[j])) {
          continue;
        }
      }
      delta = points[i].distance_to(points[j]);
      result.p1 = points[i];
      result.p2 = points[j];
      first_pair_i = i;
      first_pair_j = j;
      found_first_pair = true;
    }
  }

  if (!found_first_pair) {
    result.min_distance = 0.0f;
    return result;
  }

  if (delta <= 0.0f) {
    result.min_distance = 0.0f;
    return result;
  }

  GridHashMap<Dim, PointType> grid_map;
  grid_map.reserve(n);

  // Insert points up to the initial pair
  const std::size_t init_limit = std::max(first_pair_i, first_pair_j);
  for (std::size_t i = 0; i <= init_limit && i < n; ++i) {
    grid_map[to_grid_cell<Dim>(points[i], delta)].push_back(points[i]);
  }

  std::size_t rebuild_count = 0;

  // Stream remaining points
  for (std::size_t i = init_limit + 1; i < n; ++i) {
    const auto &pi = points[i];
    const GridCell<Dim> current_cell = to_grid_cell<Dim>(pi, delta);

    bool rebuild = false;
    float delta_sq = delta * delta;

    // Check all 3^Dim neighboring cells
    for (const auto &offset : neighbor_offsets) {
      GridCell<Dim> neighbor_cell;
      for (std::size_t d = 0; d < Dim; ++d) {
        neighbor_cell[d] = current_cell[d] + offset[d];
      }

      auto it = grid_map.find(neighbor_cell);
      if (it != grid_map.end()) {
        for (const auto &pj : it->second) {
          if constexpr (!Filter::is_trivial) {
            if (!filter(pi, pj)) {
              continue;
            }
          }

          float dist_sq = pi.squared_dist(pj);
          if (dist_sq < delta_sq) {
            delta_sq = dist_sq;
            delta = std::sqrt(delta_sq);
            result.p1 = pi;
            result.p2 = pj;
            rebuild = true;
          }
        }
      }
    }

    if (delta <= 0.0f) {
      result.min_distance = 0.0f;
      result.rebuild_count = rebuild_count;
      return result;
    }

    if (rebuild) {
      rebuild_count++;
      result.rebuild_indices.push_back(i);
      result.rebuild_work += (i + 1);
      if (verbose) {
        std::cout << "[Grid] Rebuild #" << rebuild_count << " at point " << i
                  << " -> new delta: " << delta << "\n";
      }
      grid_map.clear();
      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[j];
        grid_map[to_grid_cell<Dim>(pj, delta)].push_back(pj);
      }
    } else {
      grid_map[current_cell].push_back(pi);
    }
  }

  result.min_distance = delta;
  result.rebuild_count = rebuild_count;
  return result;
}

/**
 * @brief Deterministic Grid Solver (evaluates points in provided order)
 */
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
[[nodiscard]] ClosestPairResult<PointType>
find_closest_pair_deterministic(std::span<const PointType> points,
                                Filter filter = Filter{},
                                bool verbose = false) {
  auto start = std::chrono::high_resolution_clock::now();
  auto result = find_closest_pair_grid<Dim, PointType, Filter>(points, filter, verbose);
  auto end = std::chrono::high_resolution_clock::now();
  result.execution_time_ms =
      std::chrono::duration<double, std::milli>(end - start).count();
  return result;
}

/**
 * @brief Randomized Grid Solver with zero-overhead timing hooks
 */
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
[[nodiscard]] ClosestPairResult<PointType>
find_closest_pair_randomized(std::vector<PointType> points_copy,
                             Filter filter = Filter{},
                             TimePoint *out_start = nullptr,
                             TimePoint *out_end = nullptr,
                             bool verbose = false) {
  // 1. Thread-safe random device and shuffle
  thread_local std::random_device rd;
  std::array<std::uint32_t, 8> seed_data{};
  for (auto &v : seed_data) {
    v = rd();
  }
  std::seed_seq seq(seed_data.begin(), seed_data.end());
  std::mt19937 g(seq);
  std::shuffle(points_copy.begin(), points_copy.end(), g);

  // 2. High resolution stopwatch strictly excluding copy & shuffle latency
  auto start = std::chrono::high_resolution_clock::now();
  if (out_start) {
    *out_start = start;
  }

  auto result = find_closest_pair_grid<Dim, PointType, Filter>(
      std::span<const PointType>(points_copy), filter, verbose);

  auto end = std::chrono::high_resolution_clock::now();
  if (out_end) {
    *out_end = end;
  }

  result.execution_time_ms =
      std::chrono::duration<double, std::milli>(end - start).count();
  return result;
}

/**
 * @brief Randomized Grid Solver on pre-shuffled span (pure grid execution)
 */
template <std::size_t Dim, typename PointType, typename Filter = DefaultPairFilter>
[[nodiscard]] ClosestPairResult<PointType>
find_closest_pair_pre_shuffled(std::span<const PointType> pre_shuffled_points,
                               Filter filter = Filter{},
                               bool verbose = false) {
  return find_closest_pair_deterministic<Dim, PointType, Filter>(
      pre_shuffled_points, filter, verbose);
}

} // namespace core
