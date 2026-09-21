#ifndef SPACE_H
#define SPACE_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <execution>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <vector>

// represents a point in N-dimensional space.
template <std::size_t Dim> struct Point {
  std::array<float, Dim> coordinates{};

  // calculates the euclidean distance from this point to another point.
  [[nodiscard]] float distance_to(const Point<Dim> &other) const noexcept {
    float sum_of_squares = 0.0f;
    for (std::size_t i = 0; i < Dim; ++i) {
      float diff = coordinates[i] - other.coordinates[i];
      sum_of_squares += diff * diff;
    }
    return std::sqrt(sum_of_squares);
  }

  [[nodiscard]] static float euclidean_distance(const Point<Dim> &p1,
                                                const Point<Dim> &p2) noexcept {
    return p1.distance_to(p2);
  }
};

// defines the strategy used to order/sort points within n-dimensional space.
enum class SortStrategy {
  AxisAscending,
  AxisDescending,
  RandomShuffle,
  DistanceToOriginAscending,
  DistanceToOriginDescending,
  Adversarial
};

// binary helpers for point datasets
template <std::size_t Dim>
bool save_points_to_bin(const std::string &filepath,
                        const std::vector<Point<Dim>> &points) {
  std::ofstream out(filepath, std::ios::binary);
  if (!out.is_open()) {
    std::cerr << "[DatasetIO] Error opening file for writing: " << filepath
              << "\n";
    return false;
  }

  const char magic[4] = {'N', 'D', 'P', 'T'};
  uint32_t dim = static_cast<uint32_t>(Dim);
  uint64_t count = static_cast<uint64_t>(points.size());

  out.write(magic, sizeof(magic));
  out.write(reinterpret_cast<const char *>(&dim), sizeof(dim));
  out.write(reinterpret_cast<const char *>(&count), sizeof(count));
  out.write(reinterpret_cast<const char *>(points.data()),
            count * sizeof(Point<Dim>));

  return out.good();
}

template <std::size_t Dim>
bool load_points_from_bin(const std::string &filepath,
                          std::vector<Point<Dim>> &points) {
  std::ifstream in(filepath, std::ios::binary);
  if (!in.is_open()) {
    return false;
  }

  char magic[4];
  uint32_t dim = 0;
  uint64_t count = 0;

  in.read(magic, 4);
  if (std::string(magic, 4) != "NDPT") {
    std::cerr << "[DatasetIO] Error: invalid magic bytes in " << filepath
              << "\n";
    return false;
  }

  in.read(reinterpret_cast<char *>(&dim), sizeof(dim));
  in.read(reinterpret_cast<char *>(&count), sizeof(count));

  if (dim != Dim) {
    std::cerr << "[DatasetIO] Error: Dimension mismatch in " << filepath
              << " (file: " << dim << ", expected: " << Dim << ")\n";
    return false;
  }

  points.resize(count);
  in.read(reinterpret_cast<char *>(points.data()), count * sizeof(Point<Dim>));
  return in.good();
}

// container representing an n-dimensional space.
template <std::size_t Dim, std::size_t Size = 0> struct Space {
  static constexpr std::size_t dimension = Dim;
  static constexpr std::size_t points_size = Size;

  std::vector<Point<Dim>> points;

  Space() : points(Size) {
    if constexpr (Size > 0) {
      init_uniform(Size, 1.0f, 1000.0f, 42);
    }
  }
  explicit Space(std::size_t count) : points(count) {}

  // initializes points with uniform random coordinates.
  explicit Space(float min_val, float max_val, uint64_t seed = 42)
      : points(Size) {
    init_uniform(Size, min_val, max_val, seed);
  }

  explicit Space(std::size_t count, float min_val, float max_val, uint64_t seed = 42)
      : points(count) {
    init_uniform(count, min_val, max_val, seed);
  }

  void init_uniform(std::size_t count, float min_val = 0.0f, float max_val = 1000.0f, uint64_t seed = 42) {
    points.resize(count);
    std::mt19937_64 gen(seed);
    std::uniform_real_distribution<float> dist(min_val, max_val);

    for (auto &point : points) {
      for (auto &coord : point.coordinates) {
        coord = dist(gen);
      }
    }
  }

  [[nodiscard]] static Space<Dim, Size>
  create_uniform_space(std::size_t count, float min_val = 0.0f, float max_val = 1000.0f,
                       uint64_t seed = 42) {
    Space<Dim, Size> space(count);
    space.init_uniform(count, min_val, max_val, seed);
    return space;
  }

  [[nodiscard]] static Space<Dim, Size>
  create_uniform_space(float min_val = 0.0f, float max_val = 1000.0f,
                       uint64_t seed = 42) {
    return create_uniform_space(Size, min_val, max_val, seed);
  }

  [[nodiscard]] static Space<Dim, Size>
  create_adversarial_space(std::size_t count, float min_val = 0.0f, float max_val = 1000.0f) {
    Space<Dim, Size> space(count);
    if (count == 0)
      return space;
    space.points.resize(count);

    float range = max_val - min_val;
    std::size_t num_pairs = count / 2;
    if (num_pairs == 0) {
      for (std::size_t d = 0; d < Dim; ++d) {
        space.points[0].coordinates[d] = min_val + range * 0.5f;
      }
      return space;
    }

    // Determine grid resolution M per dimension so M^Dim >= num_pairs
    std::size_t M = 1;
    while (true) {
      std::size_t cap = 1;
      bool overflow = false;
      for (std::size_t d = 0; d < Dim; ++d) {
        if (__builtin_mul_overflow(cap, M, &cap)) {
          overflow = true;
          break;
        }
      }
      if (overflow || cap >= num_pairs) {
        break;
      }
      ++M;
    }

    float step = range / static_cast<float>(M + 1);
    float d_max = step * 0.4f;
    float d_min = std::max(d_max * 0.01f, 1e-4f);

    for (std::size_t k = 0; k < num_pairs; ++k) {
      Point<Dim> center;
      std::size_t temp = k;
      for (std::size_t d = 0; d < Dim; ++d) {
        std::size_t coord_idx = temp % M;
        temp /= M;
        center.coordinates[d] = min_val + static_cast<float>(coord_idx + 1) * step;
      }

      float pair_dist = d_max;
      if (num_pairs > 1) {
        float frac = static_cast<float>(k) / static_cast<float>(num_pairs - 1);
        pair_dist = d_max - (d_max - d_min) * frac;
      }

      Point<Dim> p1 = center;
      Point<Dim> p2 = center;
      std::size_t offset_dim = k % Dim;
      p1.coordinates[offset_dim] -= pair_dist * 0.5f;
      p2.coordinates[offset_dim] += pair_dist * 0.5f;

      space.points[2 * k] = p1;
      space.points[2 * k + 1] = p2;
    }

    if (count % 2 != 0) {
      Point<Dim> p_last;
      std::size_t temp = num_pairs;
      for (std::size_t d = 0; d < Dim; ++d) {
        std::size_t coord_idx = temp % M;
        temp /= M;
        p_last.coordinates[d] = min_val + static_cast<float>(coord_idx + 1) * step;
      }
      space.points[count - 1] = p_last;
    }

    return space;
  }

  [[nodiscard]] static Space<Dim, Size>
  create_adversarial_space(float min_val = 0.0f, float max_val = 1000.0f) {
    return create_adversarial_space(Size, min_val, max_val);
  }

  // loads or creates the point from dataset with runtime size count
  [[nodiscard]] static Space<Dim, Size>
  get_or_create(const std::string &type, std::size_t count,
                const std::string &dir = "datasets", uint64_t seed = 42) {
    std::filesystem::create_directories(dir);
    std::string filename = dir + "/" + type + "_d" + std::to_string(Dim) +
                           "_n" + std::to_string(count) + ".bin";

    Space<Dim, Size> space(count);
    if (std::filesystem::exists(filename)) {
      if (load_points_from_bin<Dim>(filename, space.points) &&
          space.points.size() == count) {
        std::cout << "[Dataset] Loaded existing cached dataset: " << filename
                  << "\n";
        return space;
      }
      std::cout << "[Dataset] Warning: Failed reading " << filename
                << ", regenerating...\n";
    }

    std::cout << "[Dataset] Generating and caching dataset: " << filename
              << "\n";
    if (type == "adversarial") {
      space = create_adversarial_space(count);
    } else if (type == "uniform_shuffled") {
      auto base_space = get_or_create("uniform", count, dir, seed);
      space = base_space;
      std::mt19937_64 g(seed + 999);
      std::shuffle(space.points.begin(), space.points.end(), g);
    } else {
      space = create_uniform_space(count, 0.0f, 1000.0f, seed);
    }

    save_points_to_bin<Dim>(filename, space.points);
    return space;
  }

  // loads or creates the point from dataset using template Size
  [[nodiscard]] static Space<Dim, Size>
  get_or_create(const std::string &type = "uniform",
                const std::string &dir = "datasets", uint64_t seed = 42) {
    return get_or_create(type, Size, dir, seed);
  }

  /// @param strategy
  /// @param axis
  void sort_points(SortStrategy strategy, std::size_t axis = 0) {
    if (axis >= Dim) {
      axis = 0;
    }

    constexpr std::size_t PAR_SORT_THRESHOLD = 32768;

    auto squared_norm = [](const Point<Dim> &p) noexcept -> float {
      float sum = 0.0f;
      for (std::size_t d = 0; d < Dim; ++d) {
        sum += p.coordinates[d] * p.coordinates[d];
      }
      return sum;
    };

    switch (strategy) {
    case SortStrategy::AxisAscending: {
      auto comp = [axis](const Point<Dim> &a, const Point<Dim> &b) noexcept {
        return a.coordinates[axis] < b.coordinates[axis];
      };
      if (points.size() >= PAR_SORT_THRESHOLD) {
        std::sort(std::execution::par, points.begin(), points.end(), comp);
      } else {
        std::sort(points.begin(), points.end(), comp);
      }
      break;
    }

    case SortStrategy::AxisDescending: {
      auto comp = [axis](const Point<Dim> &a, const Point<Dim> &b) noexcept {
        return a.coordinates[axis] > b.coordinates[axis];
      };
      if (points.size() >= PAR_SORT_THRESHOLD) {
        std::sort(std::execution::par, points.begin(), points.end(), comp);
      } else {
        std::sort(points.begin(), points.end(), comp);
      }
      break;
    }

    case SortStrategy::RandomShuffle: {
      std::random_device rd;
      std::array<std::uint32_t, 8> seed_data{};
      for (auto &val : seed_data) {
        val = rd();
      }
      std::seed_seq seq(seed_data.begin(), seed_data.end());
      std::mt19937 g(seq);
      std::shuffle(points.begin(), points.end(), g);
      break;
    }

    case SortStrategy::DistanceToOriginAscending: {
      auto comp = [squared_norm](const Point<Dim> &a, const Point<Dim> &b) noexcept {
        return squared_norm(a) < squared_norm(b);
      };
      if (points.size() >= PAR_SORT_THRESHOLD) {
        std::sort(std::execution::par, points.begin(), points.end(), comp);
      } else {
        std::sort(points.begin(), points.end(), comp);
      }
      break;
    }

    case SortStrategy::DistanceToOriginDescending: {
      auto comp = [squared_norm](const Point<Dim> &a, const Point<Dim> &b) noexcept {
        return squared_norm(a) > squared_norm(b);
      };
      if (points.size() >= PAR_SORT_THRESHOLD) {
        std::sort(std::execution::par, points.begin(), points.end(), comp);
      } else {
        std::sort(points.begin(), points.end(), comp);
      }
      break;
    }

    case SortStrategy::Adversarial: {
      generate_adversarial_ordering();
      break;
    }
    }
  }

private:
  void generate_adversarial_ordering() {
    if (points.size() <= 2)
      return;

    constexpr std::size_t PAR_SORT_THRESHOLD = 32768;

    // Sort points lexicographically across all dimensions
    auto lex_comp = [](const Point<Dim> &a, const Point<Dim> &b) noexcept {
      for (std::size_t d = 0; d < Dim; ++d) {
        if (a.coordinates[d] < b.coordinates[d]) return true;
        if (a.coordinates[d] > b.coordinates[d]) return false;
      }
      return false;
    };

    if (points.size() >= PAR_SORT_THRESHOLD) {
      std::sort(std::execution::par, points.begin(), points.end(), lex_comp);
    } else {
      std::sort(points.begin(), points.end(), lex_comp);
    }

    std::size_t num_pairs = points.size() / 2;

    struct PairEntry {
      Point<Dim> p1;
      Point<Dim> p2;
      float dist_sq;
    };

    std::vector<PairEntry> pairs;
    pairs.reserve(num_pairs);

    for (std::size_t k = 0; k < num_pairs; ++k) {
      const auto &p1 = points[2 * k];
      const auto &p2 = points[2 * k + 1];
      float d_sq = 0.0f;
      for (std::size_t d = 0; d < Dim; ++d) {
        float diff = p1.coordinates[d] - p2.coordinates[d];
        d_sq += diff * diff;
      }
      pairs.push_back(PairEntry{p1, p2, d_sq});
    }

    // Sort pairs in descending order of squared distance so that closest-pair grid
    // starts with large delta and encounters progressively smaller distances,
    // maximizing incremental rebuild operations.
    auto pair_comp = [](const PairEntry &a, const PairEntry &b) noexcept {
      return a.dist_sq > b.dist_sq;
    };

    if (pairs.size() >= PAR_SORT_THRESHOLD) {
      std::sort(std::execution::par, pairs.begin(), pairs.end(), pair_comp);
    } else {
      std::sort(pairs.begin(), pairs.end(), pair_comp);
    }

    bool has_odd = (points.size() % 2 != 0);
    Point<Dim> odd_point{};
    if (has_odd) {
      odd_point = points.back();
    }

    points.clear();
    points.reserve(num_pairs * 2 + (has_odd ? 1 : 0));

    for (const auto &pair : pairs) {
      points.push_back(pair.p1);
      points.push_back(pair.p2);
    }

    if (has_odd) {
      points.push_back(odd_point);
    }
  }
};

#endif // SPACE_H
