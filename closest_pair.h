#ifndef CLOSEST_PAIR_H
#define CLOSEST_PAIR_H

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <random>
#include <ranges>
#include <span>
#include <unordered_map>
#include <vector>

#include "space.h"

// represents grid cell indices in n-dimensional space.
template <std::size_t Dim> using GridCell = std::array<std::int64_t, Dim>;

// custom hash functor for GridCell<Dim> allowing use as std::unordered_map
// keys.
struct ArrayHasher {
  template <std::size_t Dim>
  std::size_t operator()(const GridCell<Dim> &arr) const noexcept {
    std::size_t hash_val = 0;
    for (const auto elem : arr) {
      // Boost hash_combine formula
      hash_val ^= std::hash<std::int64_t>{}(elem) + 0x9e3779b9 +
                  (hash_val << 6) + (hash_val >> 2);
    }
    return hash_val;
  }
};

// type alias for the spatial grid hash map.
template <std::size_t Dim>
using GridHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<Point<Dim>>, ArrayHasher>;

namespace detail {

// recursively populates neighbor grid cell offsets.
template <std::size_t Dim>
void build_neighbor_offsets_recursive(GridCell<Dim> &current,
                                      std::size_t current_dim,
                                      std::vector<GridCell<Dim>> &offsets) {
  if (current_dim == 0) {
    offsets.push_back(current);
    return;
  }
  for (std::int64_t offset : {-1, 0, 1}) {
    current[current_dim - 1] = offset;
    build_neighbor_offsets_recursive(current, current_dim - 1, offsets);
  }
}
} // namespace detail

// generates all 3**Dim relative cell offsets for neighboring grid cells.
template <std::size_t Dim>
[[nodiscard]] std::vector<GridCell<Dim>> generate_neighbor_offsets() {
  std::vector<GridCell<Dim>> offsets;
  offsets.reserve(static_cast<std::size_t>(std::pow(3, Dim)));
  GridCell<Dim> current{};
  detail::build_neighbor_offsets_recursive(current, Dim, offsets);
  return offsets;
}

// maps a point coordinates to its corresponding grid cell index
template <std::size_t Dim>
[[nodiscard]] GridCell<Dim> to_grid_cell(const Point<Dim> &point,
                                         float delta) noexcept {
  GridCell<Dim> cell{};
  constexpr float min_delta = std::numeric_limits<float>::epsilon();
  float safe_delta = (std::isnan(delta) || delta < min_delta) ? min_delta : delta;

  constexpr double max_safe_int = static_cast<double>(std::numeric_limits<std::int64_t>::max() - 1024);
  constexpr double min_safe_int = static_cast<double>(std::numeric_limits<std::int64_t>::min() + 1024);

  for (std::size_t d = 0; d < Dim; ++d) {
    double val = std::floor(static_cast<double>(point.coordinates[d]) / static_cast<double>(safe_delta));
    if (std::isnan(val)) {
      cell[d] = 0;
    } else if (val >= max_safe_int) {
      cell[d] = std::numeric_limits<std::int64_t>::max() - 1024;
    } else if (val <= min_safe_int) {
      cell[d] = std::numeric_limits<std::int64_t>::min() + 1024;
    } else {
      cell[d] = static_cast<std::int64_t>(val);
    }
  }
  return cell;
}

// searches neighboring grid cells to find the minimum distance from point 'pi'
// to existing points in grid.
template <std::size_t Dim>
[[nodiscard]] float find_min_in_neighbor_cells(
    const GridCell<Dim> &center_cell, const GridHashMap<Dim> &grid_map,
    const Point<Dim> &pi, const std::vector<GridCell<Dim>> &neighbor_offsets) {
  float min_dist = std::numeric_limits<float>::infinity();

  for (const auto &offset : neighbor_offsets) {
    GridCell<Dim> neighbor_cell;
    for (std::size_t d = 0; d < Dim; ++d) {
      neighbor_cell[d] = center_cell[d] + offset[d];
    }

    auto it = grid_map.find(neighbor_cell);
    if (it != grid_map.end()) {
      for (const auto &point : it->second) {
        float dist = pi.distance_to(point);
        if (dist < min_dist) {
          min_dist = dist;
        }
      }
    }
  }
  return min_dist;
}

// finds minimum distance between any pair of points using incremental grid
// algorithm.
template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based(std::span<const Point<Dim>> points,
                         bool verbose = false,
                         std::size_t *out_rebuilds = nullptr) {
  if (out_rebuilds) {
    *out_rebuilds = 0;
  }

  const std::size_t size = points.size();
  if (size < 2) {
    return std::numeric_limits<float>::infinity();
  }

  const auto neighbor_offsets = generate_neighbor_offsets<Dim>();

  // initial grid parameter distance between the first two points
  float delta = points[0].distance_to(points[1]);
  if (delta <= std::numeric_limits<float>::epsilon()) {
    if (delta == 0.0f) {
      return 0.0f;
    }
  }

  GridHashMap<Dim> grid_map;

  for (std::size_t i = 0; i < size; ++i) {
    const auto &pi = points[i];
    GridCell<Dim> cell_i = to_grid_cell(pi, delta);

    // find minimum distance between pi and points already inserted in
    // surrounding cells
    float min_dist =
        find_min_in_neighbor_cells(cell_i, grid_map, pi, neighbor_offsets);

    // insert current point into the grid
    grid_map[cell_i].push_back(pi);

    // if a closer pair is found, update delta and rebuild grid with points seen
    // so far
    if (min_dist < delta) {
      if (out_rebuilds) {
        (*out_rebuilds)++;
      }
      if (verbose) {
        std::cout << "[GridAlgorithm] New min distance: " << min_dist
                  << " -> Rebuilding grid..." << std::endl;
      }
      delta = min_dist;
      grid_map.clear();
      if (delta <= std::numeric_limits<float>::epsilon()) {
        return delta;
      }

      for (std::size_t j = 0; j <= i; ++j) {
        const auto &pj = points[j];
        grid_map[to_grid_cell(pj, delta)].push_back(pj);
      }
    }
  }
  return delta;
}

// vector overload for find_min_dist_grid_based
template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based(const std::vector<Point<Dim>> &points,
                         bool verbose = false,
                         std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based<Dim>(std::span<const Point<Dim>>(points),
                                       verbose, out_rebuilds);
}

// overload for Space<Dim, Size> container.
template <std::size_t Dim, std::size_t Size>
[[nodiscard]] float
find_min_dist_grid_based(const Space<Dim, Size> &space, bool verbose = false,
                         std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based<Dim>(space.points, verbose, out_rebuilds);
}

using TimePoint = std::chrono::time_point<std::chrono::high_resolution_clock>;

// Pre-shuffled span interface separating shuffle latency and memory allocation from core grid timing
template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based_pre_shuffled(std::span<const Point<Dim>> points,
                                      bool verbose = false,
                                      std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based<Dim>(points, verbose, out_rebuilds);
}

// Pre-shuffled span overload of find_min_dist_grid_based_randomized
template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based_randomized(std::span<const Point<Dim>> pre_shuffled_points,
                                    bool verbose = false,
                                    std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based<Dim>(pre_shuffled_points, verbose, out_rebuilds);
}

// Full randomized grid function with separated timing hooks
template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based_randomized(std::vector<Point<Dim>> points,
                                    TimePoint *out_start, bool verbose = false,
                                    std::size_t *out_rebuilds = nullptr,
                                    TimePoint *out_end = nullptr) {
  thread_local std::random_device rd;
  std::array<std::uint32_t, 8> seed_data{};
  for (auto &v : seed_data) {
    v = rd();
  }
  std::seed_seq seq(seed_data.begin(), seed_data.end());
  std::mt19937 g(seq);
  std::shuffle(points.begin(), points.end(), g);

  // Record start time strictly AFTER copy and shuffle, directly preceding core grid algorithm
  if (out_start) {
    *out_start = std::chrono::high_resolution_clock::now();
  }

  float result = find_min_dist_grid_based<Dim>(std::span<const Point<Dim>>(points), verbose, out_rebuilds);

  // Record end time strictly BEFORE points deallocation on function return
  if (out_end) {
    *out_end = std::chrono::high_resolution_clock::now();
  }

  return result;
}

template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_grid_based_randomized(std::vector<Point<Dim>> points,
                                    bool verbose = false,
                                    std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based_randomized<Dim>(std::move(points), nullptr,
                                                  verbose, out_rebuilds);
}

template <std::size_t Dim, std::size_t Size>
[[nodiscard]] float
find_min_dist_grid_based_randomized(const Space<Dim, Size> &space,
                                    TimePoint *out_start, bool verbose = false,
                                    std::size_t *out_rebuilds = nullptr,
                                    TimePoint *out_end = nullptr) {
  return find_min_dist_grid_based_randomized<Dim>(space.points, out_start,
                                                  verbose, out_rebuilds, out_end);
}

template <std::size_t Dim, std::size_t Size>
[[nodiscard]] float
find_min_dist_grid_based_randomized(const Space<Dim, Size> &space,
                                    bool verbose = false,
                                    std::size_t *out_rebuilds = nullptr) {
  return find_min_dist_grid_based_randomized<Dim>(space.points, nullptr,
                                                  verbose, out_rebuilds);
}

template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_brute_force(std::span<const Point<Dim>> points) {
  const std::size_t size = points.size();
  float min_dist = std::numeric_limits<float>::infinity();
  for (std::size_t i = 0; i < size; ++i) {
    for (std::size_t j = i + 1; j < size; ++j) {
      float dist = points[i].distance_to(points[j]);
      if (dist < min_dist) {
        min_dist = dist;
      }
    }
  }
  return min_dist;
}

template <std::size_t Dim>
[[nodiscard]] float
find_min_dist_brute_force(const std::vector<Point<Dim>> &points) {
  return find_min_dist_brute_force<Dim>(std::span<const Point<Dim>>(points));
}

template <std::size_t Dim, std::size_t Size>
[[nodiscard]] float find_min_dist_brute_force(const Space<Dim, Size> &space) {
  return find_min_dist_brute_force<Dim>(space.points);
}

#endif // CLOSEST_PAIR_H
