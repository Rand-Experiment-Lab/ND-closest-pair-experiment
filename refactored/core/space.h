#pragma once

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

#include "point.h"

namespace core {

enum class SortStrategy {
  AxisAscending,
  AxisDescending,
  DistanceAscending,
  DistanceDescending
};

template <std::size_t Dim, typename Payload = EmptyPayload>
struct Space {
  using PointType = Point<Dim, Payload>;
  std::vector<PointType> points;

  Space() = default;
  explicit Space(std::size_t count) : points(count) {}

  [[nodiscard]] std::size_t size() const noexcept { return points.size(); }
  [[nodiscard]] bool empty() const noexcept { return points.empty(); }

  [[nodiscard]] PointType &operator[](std::size_t i) noexcept { return points[i]; }
  [[nodiscard]] const PointType &operator[](std::size_t i) const noexcept { return points[i]; }

  void sort_points(SortStrategy strategy = SortStrategy::AxisAscending,
                   std::size_t axis = 0) {
    if (points.empty()) return;
    if (axis >= Dim) axis = 0;

    switch (strategy) {
    case SortStrategy::AxisAscending:
      std::sort(std::execution::par, points.begin(), points.end(),
                [axis](const PointType &a, const PointType &b) {
                  return a[axis] < b[axis];
                });
      break;
    case SortStrategy::AxisDescending:
      std::sort(std::execution::par, points.begin(), points.end(),
                [axis](const PointType &a, const PointType &b) {
                  return a[axis] > b[axis];
                });
      break;
    case SortStrategy::DistanceAscending: {
      PointType origin{};
      std::sort(std::execution::par, points.begin(), points.end(),
                [&origin](const PointType &a, const PointType &b) {
                  return a.squared_dist(origin) < b.squared_dist(origin);
                });
      break;
    }
    case SortStrategy::DistanceDescending: {
      PointType origin{};
      std::sort(std::execution::par, points.begin(), points.end(),
                [&origin](const PointType &a, const PointType &b) {
                  return a.squared_dist(origin) > b.squared_dist(origin);
                });
      break;
    }
    }
  }

  // Uniform Space Generator
  [[nodiscard]] static Space<Dim, Payload>
  create_uniform_space(std::size_t count, float min_val = 0.0f,
                       float max_val = 1000.0f, unsigned int seed = 42) {
    Space<Dim, Payload> space(count);
    if (count == 0) return space;

    std::mt19937_64 g(seed);
    std::uniform_real_distribution<float> dist(min_val, max_val);

    for (std::size_t i = 0; i < count; ++i) {
      for (std::size_t d = 0; d < Dim; ++d) {
        space.points[i][d] = dist(g);
      }
    }
    return space;
  }

  // Adversarial "Ladder of Pairs" Generator (strictly forces O(N^2) grid rebuilds)
  [[nodiscard]] static Space<Dim, Payload>
  create_adversarial_space(std::size_t count, float min_val = 0.0f,
                           float max_val = 1000.0f) {
    Space<Dim, Payload> space(count);
    if (count == 0) return space;

    std::size_t num_pairs = count / 2;
    if (num_pairs == 0) return space;

    float total_span = max_val - min_val;
    float y_spacing = total_span / static_cast<float>(num_pairs);
    float current_pair_dist = y_spacing * 0.9f;
    float distance_decrement = current_pair_dist / (static_cast<float>(num_pairs) * 2.0f);

    float current_y = min_val;

    for (std::size_t i = 0; i < num_pairs; ++i) {
      std::size_t idx1 = 2 * i;
      std::size_t idx2 = 2 * i + 1;

      // Point 1
      space.points[idx1][0] = min_val;
      if constexpr (Dim > 1) {
        space.points[idx1][1] = current_y;
      }
      for (std::size_t d = 2; d < Dim; ++d) {
        space.points[idx1][d] = min_val;
      }

      // Point 2 (separated by strictly shrinking current_pair_dist along x)
      space.points[idx2][0] = min_val + current_pair_dist;
      if constexpr (Dim > 1) {
        space.points[idx2][1] = current_y;
      }
      for (std::size_t d = 2; d < Dim; ++d) {
        space.points[idx2][d] = min_val;
      }

      current_y += y_spacing;
      current_pair_dist -= distance_decrement;
      if (current_pair_dist <= 1e-7f) {
        current_pair_dist = 1e-7f;
      }
    }

    if (count % 2 != 0) {
      for (std::size_t d = 0; d < Dim; ++d) {
        space.points[count - 1][d] = max_val * 2.0f;
      }
    }

    return space;
  }

  // Binary IO Serialization for zero-overhead disk caching
  bool save_to_binary(const std::string &filepath) const {
    std::filesystem::path p(filepath);
    if (p.has_parent_path()) {
      std::filesystem::create_directories(p.parent_path());
    }

    std::ofstream out(filepath, std::ios::binary);
    if (!out) return false;

    std::uint32_t dim_val = static_cast<std::uint32_t>(Dim);
    std::uint64_t count_val = static_cast<std::uint64_t>(points.size());
    out.write(reinterpret_cast<const char *>(&dim_val), sizeof(dim_val));
    out.write(reinterpret_cast<const char *>(&count_val), sizeof(count_val));

    // Raw points dump
    out.write(reinterpret_cast<const char *>(points.data()),
              points.size() * sizeof(PointType));
    return out.good();
  }

  bool load_from_binary(const std::string &filepath) {
    std::ifstream in(filepath, std::ios::binary);
    if (!in) return false;

    std::uint32_t dim_val = 0;
    std::uint64_t count_val = 0;
    in.read(reinterpret_cast<char *>(&dim_val), sizeof(dim_val));
    in.read(reinterpret_cast<char *>(&count_val), sizeof(count_val));

    if (dim_val != Dim) {
      std::cerr << "[SpaceIO] Dimension mismatch: file has " << dim_val
                << ", program expects " << Dim << "\n";
      return false;
    }

    points.resize(count_val);
    in.read(reinterpret_cast<char *>(points.data()),
            count_val * sizeof(PointType));
    return in.good();
  }

  [[nodiscard]] static Space<Dim, Payload>
  get_or_create(const std::string &type, std::size_t count,
                const std::string &dir = "storage/datasets/synthetic",
                unsigned int seed = 42) {
    std::string filename =
        dir + "/" + type + "_d" + std::to_string(Dim) + "_n" + std::to_string(count) + ".bin";

    // Legacy fallback check if file already exists in datasets/
    std::string legacy_filename =
        "datasets/" + type + "_d" + std::to_string(Dim) + "_n" + std::to_string(count) + ".bin";

    Space<Dim, Payload> space;
    if (std::filesystem::exists(filename)) {
      if (space.load_from_binary(filename)) {
        return space;
      }
    } else if (std::filesystem::exists(legacy_filename)) {
      if (space.load_from_binary(legacy_filename)) {
        return space;
      }
    }

    // Generate fresh
    if (type == "adversarial") {
      space = create_adversarial_space(count);
    } else if (type == "uniform_shuffled") {
      space = get_or_create("uniform", count, dir, seed);
      std::mt19937_64 g(seed + 999);
      std::shuffle(space.points.begin(), space.points.end(), g);
    } else {
      space = create_uniform_space(count, 0.0f, 1000.0f, seed);
    }

    space.save_to_binary(filename);
    return space;
  }
};

} // namespace core
