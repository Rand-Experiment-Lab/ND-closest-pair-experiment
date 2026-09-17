#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

#include "closest_pair.h"
#include "space.h"

using namespace std;

// Tolerance for floating-point comparisons
constexpr float EPSILON = 1e-4f;

inline bool is_close(float a, float b, float tol = EPSILON) {
    if (std::isinf(a) && std::isinf(b)) return true;
    return std::abs(a - b) <= tol;
}

struct TestRecord {
    string category;
    string name;
    size_t dim;
    size_t num_points;
    float det_dist;
    float rand_dist;
    float ref_dist;
    bool has_ref;
    float diff;
    bool passed;
};

static vector<TestRecord> g_records;

// Run a scale test for arbitrary dimension and point size
template <size_t Dim>
bool run_scale_test(size_t num_points, const string& test_name, uint64_t seed = 42) {
    cout << "--------------------------------------------------------" << endl;
    cout << "Scale Test: " << test_name << " [" << num_points << " points in " << Dim << "D]" << endl;

    auto space = Space<Dim>::create_uniform_space(num_points, 0.0f, 1000.0f, seed);

    bool run_brute = (Dim <= 5 && num_points <= 10000) ||
                     (Dim == 7 && num_points <= 5000) ||
                     (Dim >= 9 && num_points <= 2000);
    float min_brute = -1.0f;
    if (run_brute) {
        min_brute = find_min_dist_brute_force(space);
    }

    // Deterministic in original order
    float min_det_orig = find_min_dist_grid_based(space, false);

    // Deterministic in sorted order
    space.sort_points(SortStrategy::AxisAscending, 0);
    float min_det_sorted = find_min_dist_grid_based(space, false);

    // Randomized grid
    float min_rand = find_min_dist_grid_based_randomized(space, false);

    bool passed = false;
    float max_diff = 0.0f;

    if (run_brute) {
        float diff_orig = std::abs(min_brute - min_det_orig);
        float diff_sorted = std::abs(min_brute - min_det_sorted);
        float diff_rand = std::abs(min_brute - min_rand);
        max_diff = std::max({diff_orig, diff_sorted, diff_rand});
        passed = is_close(min_brute, min_det_orig) &&
                 is_close(min_brute, min_det_sorted) &&
                 is_close(min_brute, min_rand);

        cout << fixed << setprecision(6);
        cout << "  Brute Force Ground Truth : " << min_brute << endl;
        cout << "  Deterministic (Original) : " << min_det_orig << " (diff: " << diff_orig << ")" << endl;
        cout << "  Deterministic (Sorted)   : " << min_det_sorted << " (diff: " << diff_sorted << ")" << endl;
        cout << "  Randomized Grid          : " << min_rand << " (diff: " << diff_rand << ")" << endl;
    } else {
        float diff_det_rand = std::abs(min_det_orig - min_rand);
        float diff_sorted_rand = std::abs(min_det_sorted - min_rand);
        max_diff = std::max(diff_det_rand, diff_sorted_rand);
        passed = is_close(min_det_orig, min_rand) && is_close(min_det_sorted, min_rand);

        cout << fixed << setprecision(6);
        cout << "  Deterministic (Original) : " << min_det_orig << endl;
        cout << "  Deterministic (Sorted)   : " << min_det_sorted << endl;
        cout << "  Randomized Grid          : " << min_rand << endl;
        cout << "  Max Discrepancy          : " << max_diff << endl;
    }

    cout << "  Result                   : " << (passed ? "[PASSED]" : "[FAILED]") << endl;

    g_records.push_back({
        "Scale",
        test_name,
        Dim,
        num_points,
        min_det_orig,
        min_rand,
        min_brute,
        run_brute,
        max_diff,
        passed
    });

    return passed;
}

// Planted closest pair scale test to verify large inputs (e.g. 100k, 1M) against ground truth
template <size_t Dim>
bool run_planted_pair_test(size_t num_points, float planted_distance, const string& test_name) {
    cout << "--------------------------------------------------------" << endl;
    cout << "Planted Ground Truth Test: " << test_name << " [" << num_points << " points in " << Dim << "D]" << endl;

    auto space = Space<Dim>::create_uniform_space(num_points, 0.0f, 1000.0f, 1337);

    // Plant a pair with known exact distance strictly smaller than typical random distribution
    size_t idx1 = num_points / 4;
    size_t idx2 = (3 * num_points) / 4;
    space.points[idx2] = space.points[idx1];
    space.points[idx2].coordinates[0] += planted_distance;

    float min_det = find_min_dist_grid_based(space, false);
    float min_rand = find_min_dist_grid_based_randomized(space, false);

    float diff_det = std::abs(min_det - planted_distance);
    float diff_rand = std::abs(min_rand - planted_distance);
    float max_diff = std::max(diff_det, diff_rand);

    bool passed = is_close(min_det, planted_distance) && is_close(min_rand, planted_distance);

    cout << fixed << setprecision(6);
    cout << "  Expected Planted Dist    : " << planted_distance << endl;
    cout << "  Deterministic Grid Dist  : " << min_det << " (diff: " << diff_det << ")" << endl;
    cout << "  Randomized Grid Dist     : " << min_rand << " (diff: " << diff_rand << ")" << endl;
    cout << "  Result                   : " << (passed ? "[PASSED]" : "[FAILED]") << endl;

    g_records.push_back({
        "Planted Scale",
        test_name,
        Dim,
        num_points,
        min_det,
        min_rand,
        planted_distance,
        true,
        max_diff,
        passed
    });

    return passed;
}

// Edge case helper for arbitrary vectors of points with known expected distance
template <size_t Dim>
bool run_vector_edge_case(const vector<Point<Dim>>& points, float expected_dist, const string& test_name, bool has_expected = true) {
    cout << "--------------------------------------------------------" << endl;
    cout << "Edge Case: " << test_name << " [" << points.size() << " points in " << Dim << "D]" << endl;

    float min_brute = find_min_dist_brute_force(points);
    float min_det = find_min_dist_grid_based(points, false);
    float min_rand = find_min_dist_grid_based_randomized(points, false);

    bool passed = false;
    float max_diff = 0.0f;

    if (has_expected) {
        float diff_brute = std::abs(min_brute - expected_dist);
        float diff_det = std::abs(min_det - expected_dist);
        float diff_rand = std::abs(min_rand - expected_dist);
        max_diff = std::max({diff_brute, diff_det, diff_rand});
        passed = is_close(min_brute, expected_dist) &&
                 is_close(min_det, expected_dist) &&
                 is_close(min_rand, expected_dist);

        cout << fixed << setprecision(6);
        cout << "  Expected Target Dist     : " << expected_dist << endl;
        cout << "  Brute Force Min Dist     : " << min_brute << endl;
        cout << "  Deterministic Min Dist   : " << min_det << endl;
        cout << "  Randomized Grid Min Dist : " << min_rand << endl;
    } else {
        float diff_det = std::abs(min_det - min_brute);
        float diff_rand = std::abs(min_rand - min_brute);
        max_diff = std::max(diff_det, diff_rand);
        passed = is_close(min_det, min_brute) && is_close(min_rand, min_brute);

        cout << fixed << setprecision(6);
        cout << "  Brute Force Min Dist     : " << min_brute << endl;
        cout << "  Deterministic Min Dist   : " << min_det << endl;
        cout << "  Randomized Grid Min Dist : " << min_rand << endl;
    }

    cout << "  Result                   : " << (passed ? "[PASSED]" : "[FAILED]") << endl;

    g_records.push_back({
        "Edge Case",
        test_name,
        Dim,
        points.size(),
        min_det,
        min_rand,
        has_expected ? expected_dist : min_brute,
        true,
        max_diff,
        passed
    });

    return passed;
}

// 1. Boundary input sizes (N = 0, N = 1, N = 2, N = 3)
bool test_boundary_sizes() {
    bool passed = true;

    // N = 0
    {
        vector<Point<2>> pts0;
        float det = find_min_dist_grid_based(pts0);
        float rand = find_min_dist_grid_based_randomized(pts0);
        bool ok = std::isinf(det) && std::isinf(rand);
        cout << "--------------------------------------------------------" << endl;
        cout << "Edge Case: Empty Point Set [N = 0 in 2D]" << endl;
        cout << "  Result: " << (ok ? "[PASSED]" : "[FAILED]") << " (Returned infinity as expected)" << endl;
        passed &= ok;
        g_records.push_back({"Edge Case", "Empty Set (N = 0)", 2, 0, det, rand, std::numeric_limits<float>::infinity(), true, 0.0f, ok});
    }

    // N = 1
    {
        vector<Point<2>> pts1 = {{{10.0f, 20.0f}}};
        float det = find_min_dist_grid_based(pts1);
        float rand = find_min_dist_grid_based_randomized(pts1);
        bool ok = std::isinf(det) && std::isinf(rand);
        cout << "--------------------------------------------------------" << endl;
        cout << "Edge Case: Single Point [N = 1 in 2D]" << endl;
        cout << "  Result: " << (ok ? "[PASSED]" : "[FAILED]") << " (Returned infinity as expected)" << endl;
        passed &= ok;
        g_records.push_back({"Edge Case", "Single Point (N = 1)", 2, 1, det, rand, std::numeric_limits<float>::infinity(), true, 0.0f, ok});
    }

    // N = 2
    {
        vector<Point<2>> pts2 = {{{0.0f, 0.0f}}, {{3.0f, 4.0f}}};
        passed &= run_vector_edge_case(pts2, 5.0f, "Minimal Valid Pair (N = 2, 3-4-5)");
    }

    // N = 3 (Right Triangle 3-4-5, vertices at (0,0), (3,0), (0,4) -> min dist is 3.0)
    {
        vector<Point<2>> pts3 = {{{0.0f, 0.0f}}, {{3.0f, 0.0f}}, {{0.0f, 4.0f}}};
        passed &= run_vector_edge_case(pts3, 3.0f, "Right Triangle (N = 3, sides 3, 4, 5)");
    }

    // N = 3 Equilateral Triangle in 3D (unit basis vectors: (1,0,0), (0,1,0), (0,0,1))
    // All pairwise distances are sqrt(2) = 1.41421356f
    {
        vector<Point<3>> pts3_3d = {{{1.0f, 0.0f, 0.0f}}, {{0.0f, 1.0f, 0.0f}}, {{0.0f, 0.0f, 1.0f}}};
        passed &= run_vector_edge_case(pts3_3d, std::sqrt(2.0f), "Equilateral Triangle in 3D (N = 3)");
    }

    return passed;
}

// 2. Duplicate / Coincident Points (Distance = 0.0)
bool test_duplicate_points() {
    bool passed = true;

    // Isolated duplicate in 2D
    {
        vector<Point<2>> pts(100);
        for (size_t i = 0; i < 100; ++i) {
            pts[i].coordinates[0] = static_cast<float>(i * 5);
            pts[i].coordinates[1] = static_cast<float>(i * 7);
        }
        pts[73] = pts[12]; // Coincident pair
        passed &= run_vector_edge_case(pts, 0.0f, "Isolated Coincident Pair (2D)");
    }

    // Isolated duplicate in 3D
    {
        vector<Point<3>> pts(200);
        for (size_t i = 0; i < 200; ++i) {
            pts[i].coordinates[0] = static_cast<float>(i * 3);
            pts[i].coordinates[1] = static_cast<float>(i * 4);
            pts[i].coordinates[2] = static_cast<float>(i * 5);
        }
        pts[150] = pts[25]; // Coincident pair
        passed &= run_vector_edge_case(pts, 0.0f, "Isolated Coincident Pair (3D)");
    }

    // Multiple duplicate pairs
    {
        vector<Point<2>> pts(100);
        for (size_t i = 0; i < 100; ++i) {
            pts[i].coordinates[0] = static_cast<float>(i * 10);
            pts[i].coordinates[1] = static_cast<float>(i * 10);
        }
        pts[10] = pts[20];
        pts[30] = pts[40];
        pts[80] = pts[90];
        passed &= run_vector_edge_case(pts, 0.0f, "Multiple Duplicate Pairs (2D)");
    }

    // All points identical (N = 50, all at (42.0, 42.0))
    {
        vector<Point<2>> pts_all_same(50, Point<2>{{{42.0f, 42.0f}}});
        passed &= run_vector_edge_case(pts_all_same, 0.0f, "All Points Identical (50 points)");
    }

    return passed;
}

// 3. Collinear & Co-Planar Points
bool test_collinear_and_coplanar() {
    bool passed = true;

    // Collinear points in 2D along X-axis with known closest pair
    {
        vector<Point<2>> pts;
        for (int i = 0; i < 80; ++i) {
            pts.push_back(Point<2>{{{static_cast<float>(i * 10), 0.0f}}});
        }
        // Plant closest pair at x = 33.5 (dist to 30.0 is 3.5)
        pts.push_back(Point<2>{{{33.5f, 0.0f}}});
        passed &= run_vector_edge_case(pts, 3.5f, "Collinear on X-Axis with Planted Pair");
    }

    // Collinear points in 3D along diagonal (x = y = z)
    {
        vector<Point<3>> pts;
        for (int i = 0; i < 80; ++i) {
            float val = static_cast<float>(i * 10);
            pts.push_back(Point<3>{{{val, val, val}}});
        }
        // Distance along diagonal between step of 10 is sqrt(3 * 100) = sqrt(300) = 17.3205f
        // Plant a point at offset 2.0 along diagonal from point i=15 (150, 150, 150)
        float pval = 150.0f + 2.0f;
        pts.push_back(Point<3>{{{pval, pval, pval}}});
        float expected = std::sqrt(3.0f * 4.0f); // sqrt(12) ~ 3.4641016f
        passed &= run_vector_edge_case(pts, expected, "Collinear on 3D Diagonal");
    }

    // Co-planar points in 3D (Z = 0)
    {
        auto space = Space<3>::create_uniform_space(300, 0.0f, 1000.0f, 777);
        for (auto& p : space.points) {
            p.coordinates[2] = 0.0f; // Force flat plane in 3D
        }
        passed &= run_vector_edge_case(space.points, 0.0f, "Co-planar 3D Points (Z = 0)", false);
    }

    return passed;
}

// 4. Coordinates with Negative Values, Extreme Scales, and Integer Lattices
bool test_scales_and_lattices() {
    bool passed = true;

    // Negative & quadrant-crossing coordinates ([-500, 500]^2)
    {
        auto space = Space<2>::create_uniform_space(400, -500.0f, 500.0f, 999);
        passed &= run_vector_edge_case(space.points, 0.0f, "Negative / Multi-Quadrant Range ([-500, 500])", false);
    }

    // Large coordinate values (10^7 scale) with exactly representable float distance
    {
        vector<Point<2>> pts = {
            {{{10000000.0f, 20000000.0f}}},
            {{{10000000.0f, 20000004.0f}}}, // dist = 4.0f (exact in float at 2*10^7)
            {{{10000500.0f, 20000500.0f}}},
            {{{10001000.0f, 20001000.0f}}}
        };
        passed &= run_vector_edge_case(pts, 4.0f, "Extreme Coordinates Scale (10^7)");
    }

    // Micro distance (delta = 0.0001)
    {
        vector<Point<2>> pts = {
            {{{100.0f, 200.0f}}},
            {{{100.0f, 200.0001f}}}, // dist = 0.0001
            {{{300.0f, 400.0f}}},
            {{{500.0f, 600.0f}}}
        };
        passed &= run_vector_edge_case(pts, 0.0001f, "Micro Distance (0.0001f)");
    }

    // Regular 2D Integer Grid Lattice (20 x 20 = 400 points)
    // Minimum distance between adjacent lattice points is strictly 1.0f
    {
        vector<Point<2>> grid_pts;
        grid_pts.reserve(400);
        for (int i = 0; i < 20; ++i) {
            for (int j = 0; j < 20; ++j) {
                grid_pts.push_back(Point<2>{{{static_cast<float>(i), static_cast<float>(j)}}});
            }
        }
        passed &= run_vector_edge_case(grid_pts, 1.0f, "Regular 2D Integer Lattice (20x20, ties)");
    }

    // Adversarial Ladder of Pairs (forcing continuous rebuilds)
    {
        auto adv_space = Space<2>::create_adversarial_space(500, 0.0f, 1000.0f);
        passed &= run_vector_edge_case(adv_space.points, 0.0f, "Adversarial Ladder of Pairs (N = 500)", false);
    }

    return passed;
}

// 5. Higher-Dimensional Edge Cases (5D, 7D, 9D)
bool test_higher_dimensions_edge_cases() {
    bool passed = true;

    // 5D Minimal Valid Pair (N = 2): points (0,0,0,0,0) and (1,2,2,4,4)
    // distance = sqrt(1 + 4 + 4 + 16 + 16) = sqrt(41) = 6.403124f
    {
        vector<Point<5>> pts5 = {
            {{{0.0f, 0.0f, 0.0f, 0.0f, 0.0f}}},
            {{{1.0f, 2.0f, 2.0f, 4.0f, 4.0f}}}
        };
        passed &= run_vector_edge_case(pts5, std::sqrt(41.0f), "5D Minimal Pair (N = 2)");
    }

    // 5D Standard Basis Simplex (N = 6: origin + 5 unit basis vectors)
    // Distance to origin is 1.0f; pairwise unit vector dist is sqrt(2). Min dist is 1.0f.
    {
        vector<Point<5>> simplex(6);
        for (size_t d = 0; d < 5; ++d) {
            simplex[d + 1].coordinates[d] = 1.0f;
        }
        passed &= run_vector_edge_case(simplex, 1.0f, "5D Simplex Points (N = 6)");
    }

    // 7D Isolated Coincident Pair (N = 100)
    {
        vector<Point<7>> pts7(100);
        for (size_t i = 0; i < 100; ++i) {
            for (size_t d = 0; d < 7; ++d) {
                pts7[i].coordinates[d] = static_cast<float>(i * (d + 2));
            }
        }
        pts7[67] = pts7[19];
        passed &= run_vector_edge_case(pts7, 0.0f, "7D Isolated Duplicate Pair (N = 100)");
    }

    // 7D Negative / Multi-Quadrant Range (N = 200 in [-500, 500]^7)
    {
        auto space7 = Space<7>::create_uniform_space(200, -500.0f, 500.0f, 888);
        passed &= run_vector_edge_case(space7.points, 0.0f, "7D Multi-Quadrant Range", false);
    }

    // 9D Minimal Pair (N = 2): unit step across all 9 dimensions
    // distance = sqrt(9 * 1^2) = 3.0f
    {
        Point<9> p1{}, p2{};
        for (size_t d = 0; d < 9; ++d) {
            p1.coordinates[d] = 0.0f;
            p2.coordinates[d] = 1.0f;
        }
        passed &= run_vector_edge_case(vector<Point<9>>{p1, p2}, 3.0f, "9D Minimal Pair (N = 2, dist 3.0)");
    }

    // 9D Isolated Coincident Pair (N = 80)
    {
        vector<Point<9>> pts9(80);
        for (size_t i = 0; i < 80; ++i) {
            for (size_t d = 0; d < 9; ++d) {
                pts9[i].coordinates[d] = static_cast<float>(i * (d + 3));
            }
        }
        pts9[55] = pts9[11];
        passed &= run_vector_edge_case(pts9, 0.0f, "9D Isolated Duplicate Pair (N = 80)");
    }

    // 9D Collinear on Main Diagonal (N = 50) with planted closest pair
    {
        vector<Point<9>> diag9;
        for (int i = 0; i < 50; ++i) {
            Point<9> p{};
            for (size_t d = 0; d < 9; ++d) p.coordinates[d] = static_cast<float>(i * 20);
            diag9.push_back(p);
        }
        // Plant point at offset 1.0 along diagonal from point 10
        Point<9> p_plant{};
        for (size_t d = 0; d < 9; ++d) p_plant.coordinates[d] = 201.0f;
        diag9.push_back(p_plant);
        float expected_diag = std::sqrt(9.0f * 1.0f); // 3.0f
        passed &= run_vector_edge_case(diag9, expected_diag, "9D Collinear on Main Diagonal");
    }

    return passed;
}

// Print comprehensive summary table
void print_summary() {
    cout << "\n========================================================================================================\n";
    cout << "                                  VERIFICATION SUMMARY REPORT                                           \n";
    cout << "========================================================================================================\n";
    cout << left << setw(14) << "Category"
         << setw(35) << "Test Name"
         << right << setw(5) << "Dim"
         << setw(9) << "Points"
         << setw(13) << "Det Dist"
         << setw(13) << "Rand Dist"
         << setw(13) << "Reference"
         << setw(12) << "Max Diff"
         << setw(10) << "Status" << "\n";
    cout << string(124, '-') << "\n";

    size_t total_passed = 0;
    for (const auto& r : g_records) {
        if (r.passed) total_passed++;

        cout << left << setw(14) << r.category
             << setw(35) << (r.name.length() > 33 ? r.name.substr(0, 31) + ".." : r.name)
             << right << setw(5) << r.dim
             << setw(9) << r.num_points;

        cout << fixed << setprecision(5);
        if (std::isinf(r.det_dist)) {
            cout << setw(13) << "inf";
        } else {
            cout << setw(13) << r.det_dist;
        }

        if (std::isinf(r.rand_dist)) {
            cout << setw(13) << "inf";
        } else {
            cout << setw(13) << r.rand_dist;
        }

        if (!r.has_ref) {
            cout << setw(13) << "N/A";
        } else if (std::isinf(r.ref_dist)) {
            cout << setw(13) << "inf";
        } else {
            cout << setw(13) << r.ref_dist;
        }

        cout << scientific << setprecision(2) << setw(12) << r.diff;
        cout << right << setw(10) << (r.passed ? "[PASSED]" : "[FAILED]") << "\n";
    }

    cout << string(124, '=') << "\n";
    cout << "Total Tests Run : " << g_records.size() << "\n";
    cout << "Passed          : " << total_passed << "\n";
    cout << "Failed          : " << (g_records.size() - total_passed) << "\n";
    cout << "========================================================================================================\n";

    if (total_passed == g_records.size()) {
        cout << " >>> VERIFICATION SUCCESS: All scale tests and edge cases passed! <<<\n";
        cout << " >>> Both Deterministic Grid and Randomized Grid algorithms are CONFIRMED CORRECT. <<<\n";
    } else {
        cout << " >>> VERIFICATION FAILURE: One or more tests failed! Check logs above. <<<\n";
    }
    cout << "========================================================================================================\n";
}

int main() {
    cout << "========================================================================" << endl;
    cout << "      N-Dimensional Closest Pair Rigorous Correctness Verification      " << endl;
    cout << "========================================================================" << endl;
    cout << "Verification Scope:\n";
    cout << " - Point sizes : 10, 100, 200, 500, 1000, 5000, 10000, 50000, 100000,\n";
    cout << "                 200000, 500000, 1000000 (2D and 3D)\n";
    cout << " - Scale check : Brute Force ground truth (N <= 10000), Det vs Rand consistency\n";
    cout << " - Planted pair: Large scale planted ground truth needle verification (100k, 1M)\n";
    cout << " - Edge cases  : N=0, N=1, N=2, N=3, Duplicates, Collinear, Co-planar, Large coords,\n";
    cout << "                 Micro distance, Negative coords, 2D Grid Lattice, Adversarial\n";
    cout << " - Timing      : Removed completely (pure correctness evaluation)\n";
    cout << "========================================================================\n" << endl;

    bool all_passed = true;

    // =========================================================================
    // PART 1: 2D SCALE TESTS (10 to 1,000,000 points)
    // =========================================================================
    cout << "\n========================================================" << endl;
    cout << " PART 1: 2D Point Scale Verification (10 to 1,000,000)  " << endl;
    cout << "========================================================" << endl;
    const vector<size_t> scale_sizes = {
        10, 100, 200, 500, 1000, 5000, 10000, 50000, 100000, 200000, 500000, 1000000
    };

    for (size_t n : scale_sizes) {
        all_passed &= run_scale_test<2>(n, "2D Scale Set");
    }

    // =========================================================================
    // PART 2: 3D SCALE TESTS (Sample & High Scale Verification)
    // =========================================================================
    cout << "\n========================================================" << endl;
    cout << " PART 2: 3D Point Scale Verification                    " << endl;
    cout << "========================================================" << endl;
    const vector<size_t> scale_sizes_3d = {10, 100, 1000, 10000, 100000, 1000000};
    for (size_t n : scale_sizes_3d) {
        all_passed &= run_scale_test<3>(n, "3D Scale Set");
    }

    // =========================================================================
    // PART 3: HIGHER DIMENSIONS SCALE TESTS (5D, 7D, 9D)
    // =========================================================================
    cout << "\n========================================================" << endl;
    cout << " PART 3: Higher Dimensions Scale Verification (5D, 7D, 9D)" << endl;
    cout << "========================================================" << endl;
    const vector<size_t> scale_sizes_5d = {10, 100, 500, 1000, 5000, 10000, 50000, 100000};
    for (size_t n : scale_sizes_5d) {
        all_passed &= run_scale_test<5>(n, "5D Scale Set");
    }

    const vector<size_t> scale_sizes_7d = {10, 100, 500, 1000, 5000, 10000};
    for (size_t n : scale_sizes_7d) {
        all_passed &= run_scale_test<7>(n, "7D Scale Set");
    }

    const vector<size_t> scale_sizes_9d = {10, 100, 500, 1000, 2000};
    for (size_t n : scale_sizes_9d) {
        all_passed &= run_scale_test<9>(n, "9D Scale Set");
    }

    // =========================================================================
    // PART 4: LARGE-SCALE & HIGH-DIM PLANTED GROUND TRUTH TESTS
    // =========================================================================
    cout << "\n========================================================" << endl;
    cout << " PART 4: Planted Needle-in-Haystack Ground Truth Tests  " << endl;
    cout << "========================================================" << endl;
    all_passed &= run_planted_pair_test<2>(100000, 0.0005f, "Planted Needle (100k pts in 2D)");
    all_passed &= run_planted_pair_test<2>(1000000, 0.00005f, "Planted Needle (1M pts in 2D)");
    all_passed &= run_planted_pair_test<3>(1000000, 0.005f, "Planted Needle (1M pts in 3D)");
    all_passed &= run_planted_pair_test<5>(10000, 0.05f, "Planted Needle (10k pts in 5D)");
    all_passed &= run_planted_pair_test<7>(5000, 0.2f, "Planted Needle (5k pts in 7D)");
    all_passed &= run_planted_pair_test<9>(1000, 0.5f, "Planted Needle (1k pts in 9D)");

    // =========================================================================
    // PART 5: COMPREHENSIVE EDGE CASES (2D, 3D, 5D, 7D, 9D)
    // =========================================================================
    cout << "\n========================================================" << endl;
    cout << " PART 5: Comprehensive Edge Cases (2D, 3D, 5D, 7D, 9D)  " << endl;
    cout << "========================================================" << endl;
    all_passed &= test_boundary_sizes();
    all_passed &= test_duplicate_points();
    all_passed &= test_collinear_and_coplanar();
    all_passed &= test_scales_and_lattices();
    all_passed &= test_higher_dimensions_edge_cases();

    // =========================================================================
    // PART 6: SUMMARY REPORT
    // =========================================================================
    print_summary();

    return all_passed ? 0 : 1;
}
