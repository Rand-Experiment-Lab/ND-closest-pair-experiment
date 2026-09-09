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

  Space() : points(Size) {}
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
    float num_pairs = static_cast<float>(count) / 2.0f;
    if (num_pairs < 1.0f)
      num_pairs = 1.0f;

    // distribute pairs evenly across the available space on the Y-axis
    float y_spacing = range / (num_pairs + 1.0f);

    // the distance inside the pair must be smaller than the distance between
    // pairs!
    // otherwise, a point from pair 1 would be closer to pair 2 than to its own
    // partner, breaking the logic.
    float current_pair_dist = y_spacing * 0.9f;
    float distance_decrement = current_pair_dist / (num_pairs * 2.0f);
    float current_y = min_val + y_spacing;
    for (std::size_t i = 0; i < count; i += 2) {
      Point<Dim> p1, p2;

      for (std::size_t d = 0; d < Dim; ++d) {
        p1.coordinates[d] = min_val;
        p2.coordinates[d] = min_val;
      }

      if (Dim > 1) {
        for (std::size_t d = 1; d < Dim; ++d) {
          p1.coordinates[d] = current_y;
          p2.coordinates[d] = current_y;
        }
        p1.coordinates[0] = min_val;
        p2.coordinates[0] = min_val + current_pair_dist;
      } else {
        p1.coordinates[0] = current_y;
        p2.coordinates[0] = current_y + current_pair_dist;
      }

      space.points[i] = p1;
      if (i + 1 < count) {
        space.points[i + 1] = p2;
      }
      current_pair_dist -= distance_decrement;
      current_y += y_spacing;
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

    switch (strategy) {
    case SortStrategy::AxisAscending:
      std::sort(std::execution::par, points.begin(), points.end(),
                [axis](const Point<Dim> &a, const Point<Dim> &b) {
                  return a.coordinates[axis] < b.coordinates[axis];
                });
      break;

    case SortStrategy::AxisDescending:
      std::sort(std::execution::par, points.begin(), points.end(),
                [axis](const Point<Dim> &a, const Point<Dim> &b) {
                  return a.coordinates[axis] > b.coordinates[axis];
                });
      break;

    case SortStrategy::RandomShuffle: {
      std::random_device rd;
      std::mt19937 g(rd());
      std::shuffle(points.begin(), points.end(), g);
      break;
    }

    case SortStrategy::DistanceToOriginAscending: {
      Point<Dim> origin{};
      std::sort(std::execution::par, points.begin(), points.end(),
                [&origin](const Point<Dim> &a, const Point<Dim> &b) {
                  return a.distance_to(origin) < b.distance_to(origin);
                });
      break;
    }

    case SortStrategy::DistanceToOriginDescending: {
      Point<Dim> origin{};
      std::sort(std::execution::par, points.begin(), points.end(),
                [&origin](const Point<Dim> &a, const Point<Dim> &b) {
                  return a.distance_to(origin) > b.distance_to(origin);
                });
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

    // sort points along primary axis
    std::sort(points.begin(), points.end(),
              [](const Point<Dim> &a, const Point<Dim> &b) {
                return a.coordinates[0] < b.coordinates[0];
              });

    // construct adversarial sequence
    std::vector<Point<Dim>> adversarial_seq;
    adversarial_seq.reserve(points.size());

    std::size_t left = 0;
    std::size_t right = points.size() - 1;

    while (left <= right) {
      if (left == right) {
        adversarial_seq.push_back(points[left]);
        break;
      }
      adversarial_seq.push_back(points[left++]);
      adversarial_seq.push_back(points[right--]);

      if (left < right) {
        std::size_t mid = left + (right - left) / 2;
        adversarial_seq.push_back(points[mid]);
        std::swap(points[mid], points[left]);
        left++;
      }
    }

    points = std::move(adversarial_seq);
  }
};

#endif // SPACE_H
