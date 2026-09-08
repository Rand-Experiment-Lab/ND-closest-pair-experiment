#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <random>
#include <string>
#include <vector>

#include "space.h"

namespace fs = std::filesystem;
using namespace std;

template <size_t Dim>
vector<Point<Dim>> generate_uniform(size_t n, uint64_t seed = 42,
                                    float min_val = 0.0f,
                                    float max_val = 1000.0f) {
  mt19937_64 gen(seed);
  uniform_real_distribution<float> dist(min_val, max_val);

  vector<Point<Dim>> points(n);
  for (size_t i = 0; i < n; i++) {
    for (size_t d = 0; d < Dim; ++d) {
      points[i].coordinates[d] = dist(gen);
    }
  }
  return points;
}

template <size_t Dim>
vector<Point<Dim>> generate_adversarial(size_t n, float min_val = 0.0f,
                                        float max_val = 1000.0f) {
  vector<Point<Dim>> points(n);
  if (n == 0) {
    return points;
  }

  float range = max_val - min_val;
  float num_pairs = static_cast<float>(n) / 2.0f;
  if (num_pairs < 1.0f) {
    num_pairs = 1.0f;
  }

  float y_spacing = range / (num_pairs + 1.0f);
  float current_pair_dist = y_spacing * 0.9f;
  float distance_decrement = current_pair_dist / (num_pairs * 2.0f);
  float current_y = min_val + y_spacing;

  for (size_t i = 0; i < n; i += 2) {
    Point<Dim> p1, p2;
    for (size_t d = 0; d < Dim; ++d) {
      p1.coordinates[d] = min_val;
      p2.coordinates[d] = min_val;
    }

    if (Dim > 1) {
      for (size_t d = 1; d < Dim; ++d) {
        p1.coordinates[d] = current_y;
        p2.coordinates[d] = current_y;
      }
      p1.coordinates[0] = min_val;
      p2.coordinates[0] = min_val + current_pair_dist;
    } else {
      p1.coordinates[0] = current_y;
      p2.coordinates[0] = current_y + current_pair_dist;
    }

    points[i] = p1;
    if (i + 1 < n) {
      points[i + 1] = p2;
    }

    current_pair_dist -= distance_decrement;
    current_y += y_spacing;
  }

  return points;
}

template <size_t Dim>
vector<Point<Dim>> generate_clustered(size_t n, size_t num_clusters = 5,
                                      uint64_t seed = 42, float min_val = 0.0f,
                                      float max_val = 1000.0f) {
  mt19937_64 gen(seed);
  uniform_real_distribution<float> center_dist(min_val + 100.0f,
                                               max_val - 100.0f);
  uniform_int_distribution<size_t> cluster_choice(0, num_clusters - 1);
  normal_distribution<float> offset_dist(0.0f, (max_val - min_val) * 0.03f);

  vector<array<float, Dim>> centers(num_clusters);
  for (size_t k = 0; k < num_clusters; ++k) {
    for (size_t d = 0; d < Dim; ++d) {
      centers[k][d] = center_dist(gen);
    }
  }

  vector<Point<Dim>> points(n);
  for (size_t i = 0; i < n; ++i) {
    size_t c = cluster_choice(gen);
    for (size_t d = 0; d < Dim; ++d) {
      float val = centers[c][d] + offset_dist(gen);
      points[i].coordinates[d] = std::clamp(val, min_val, max_val);
    }
  }

  return points;
}

template <size_t Dim>
void generate_and_save(const string &type, size_t n, const string &out_dir,
                       uint64_t seed) {
  string filename = out_dir + "/" + type + "_d" + to_string(Dim) + "_n" +
                    to_string(n) + ".bin";

  auto t0 = chrono::high_resolution_clock::now();
  vector<Point<Dim>> points;

  cout << "Generating " << type << " [Dim=" << Dim << ", N=" << n << "] -> "
       << filename << " ... " << flush;

  if (type == "uniform") {
    points = generate_uniform<Dim>(n, seed);
  } else if (type == "adversarial") {
    points = generate_adversarial<Dim>(n);
  } else if (type == "clustered") {
    points = generate_clustered<Dim>(n, 5, seed);
  } else {
    cerr << "Unknown type: " << type << "\n";
    return;
  }

  if (save_points_to_bin<Dim>(filename, points)) {
    auto t1 = chrono::high_resolution_clock::now();
    double ms = chrono::duration<double, milli>(t1 - t0).count();
    double mb = (n * Dim * sizeof(float) + 16) / (1024.0 * 1024.0);
    cout << "Done (" << ms << " ms, " << mb << " MB)\n";
  }
}

void dispatch_generation(size_t dim, const string &type, size_t n,
                         const string &out_dir, uint64_t seed) {
  switch (dim) {
  case 2:
    generate_and_save<2>(type, n, out_dir, seed);
    break;
  case 3:
    generate_and_save<3>(type, n, out_dir, seed);
    break;
  case 5:
    generate_and_save<5>(type, n, out_dir, seed);
    break;
  case 7:
    generate_and_save<7>(type, n, out_dir, seed);
    break;
  case 9:
    generate_and_save<9>(type, n, out_dir, seed);
    break;
  default:
    cerr << "Unsupported dimension: " << dim << " (Supported: 2, 3, 5, 7, 9)\n";
  }
}

int main(int argc, char *argv[]) {
  string out_dir = "datasets";
  fs::create_directories(out_dir);

  if (argc > 1 && (string(argv[1]) == "--help" || string(argv[1]) == "-h")) {
    cout << "Usage:\n"
         << "  ./data_set_generator                        # Generate all "
            "benchmark datasets\n"
         << "  ./data_set_generator <dim> <type> <n> [seed] # Generate "
            "specific dataset\n"
         << "Types: uniform, adversarial, clustered\n";
    return 0;
  }

  if (argc >= 4) {
    size_t dim = stoul(argv[1]);
    string type = argv[2];
    size_t n = stoul(argv[3]);
    uint64_t seed = (argc >= 5) ? stoull(argv[4]) : 42;

    dispatch_generation(dim, type, n, out_dir, seed);
    return 0;
  }

  cout << "=== Generating Benchmark Datasets for Closest Pair Experiments in ./"
       << out_dir << " ===\n\n";

  const vector<size_t> dims = {2, 3, 5, 7, 9};
  const vector<size_t> uniform_sizes = {100000, 200000, 300000, 400000, 500000,
                                       600000, 700000, 800000, 900000, 1000000};
  const vector<size_t> adversarial_sizes = {10000, 20000, 30000, 40000, 50000};

  uint64_t seed = 42;
  for (size_t dim : dims) {
    cout << "\n--- Dimension " << dim << "D ---\n";
    for (size_t n : uniform_sizes) {
      dispatch_generation(dim, "uniform", n, out_dir, seed++);
    }
    for (size_t n : adversarial_sizes) {
      dispatch_generation(dim, "adversarial", n, out_dir, seed++);
    }
  }

  cout << "\nAll benchmark datasets generated successfully in " << out_dir
       << "/\n";
  return 0;
}
