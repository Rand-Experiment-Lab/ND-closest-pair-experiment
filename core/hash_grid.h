#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <unordered_map>
#include <vector>

namespace core {

template <std::size_t Dim>
using GridCell = std::array<std::int64_t, Dim>;

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

template <std::size_t Dim, typename PointType>
[[nodiscard]] inline GridCell<Dim> to_grid_cell(const PointType &point,
                                                float delta) noexcept {
  GridCell<Dim> cell{};
  const float safe_delta = std::max(delta, std::numeric_limits<float>::epsilon());
  const double inv_delta = 1.0 / static_cast<double>(safe_delta);

  constexpr double max_safe_int =
      static_cast<double>(std::numeric_limits<std::int64_t>::max() - 1000);
  constexpr double min_safe_int =
      static_cast<double>(std::numeric_limits<std::int64_t>::min() + 1000);

  for (std::size_t d = 0; d < Dim; ++d) {
    double scaled = std::floor(static_cast<double>(point[d]) * inv_delta);
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

template <std::size_t Dim>
[[nodiscard]] inline std::vector<GridCell<Dim>> compute_neighbor_offsets() {
  std::size_t total_neighbors = 1;
  for (std::size_t d = 0; d < Dim; ++d) {
    total_neighbors *= 3;
  }

  std::vector<GridCell<Dim>> offsets(total_neighbors);
  for (std::size_t idx = 0; idx < total_neighbors; ++idx) {
    std::size_t temp = idx;
    for (std::size_t d = 0; d < Dim; ++d) {
      offsets[idx][d] = static_cast<std::int64_t>(temp % 3) - 1;
      temp /= 3;
    }
  }
  return offsets;
}

template <std::size_t Dim, typename PointType>
using GridHashMap =
    std::unordered_map<GridCell<Dim>, std::vector<PointType>, ArrayHasher>;

} // namespace core
