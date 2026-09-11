#include <chrono>
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <vector>

#include "closest_pair.h"
#include "space.h"

using namespace std;

// Tolerance for comparing floating-point minimum distance results
constexpr float EPSILON = 1e-4f;

template <size_t Dim, size_t NumPoints>
bool run_validation_test(const string& test_name) {
    cout << "--------------------------------------------------------" << endl;
    cout << "Running Test: " << test_name << " [" << NumPoints << " points in " << Dim << "D]" << endl;

    Space<Dim, NumPoints> space;

    auto start_brute = chrono::high_resolution_clock::now();
    float min_brute = find_min_dist_brute_force(space);
    auto end_brute = chrono::high_resolution_clock::now();
    chrono::duration<double, milli> brute_ms = end_brute - start_brute;

    space.sort_points(SortStrategy::AxisAscending, 0);
    auto start_grid = chrono::high_resolution_clock::now();
    float min_grid = find_min_dist_grid_based(space, false);
    auto end_grid = chrono::high_resolution_clock::now();
    chrono::duration<double, milli> grid_ms = end_grid - start_grid;

    space.sort_points(SortStrategy::Adversarial);
    auto start_adv = chrono::high_resolution_clock::now();
    float min_adv = find_min_dist_grid_based(space, false);
    auto end_adv = chrono::high_resolution_clock::now();
    chrono::duration<double, milli> adv_ms = end_adv - start_adv;

    auto start_rand = chrono::high_resolution_clock::now();
    float min_rand = find_min_dist_grid_based_randomized(space, false);
    auto end_rand = chrono::high_resolution_clock::now();
    chrono::duration<double, milli> rand_ms = end_rand - start_rand;

    float diff_grid = abs(min_brute - min_grid);
    float diff_adv = abs(min_brute - min_adv);
    float diff_rand = abs(min_brute - min_rand);
    bool passed = (min_brute > 0.0f) && (diff_grid <= EPSILON) && (diff_adv <= EPSILON) && (diff_rand <= EPSILON);

    cout << fixed << setprecision(5);
    cout << "  Brute Force Min Dist     : " << min_brute << " (" << brute_ms.count() << " ms)" << endl;
    cout << "  Grid (Axis Sorted)       : " << min_grid << " (" << grid_ms.count() << " ms)" << endl;
    cout << "  Grid (Adversarial)       : " << min_adv << " (" << adv_ms.count() << " ms)" << endl;
    cout << "  Grid (Randomized)        : " << min_rand << " (" << rand_ms.count() << " ms)" << endl;
    cout << "  Diff (Brute vs Axis)     : " << diff_grid << endl;
    cout << "  Diff (Brute vs Adv)      : " << diff_adv << endl;
    cout << "  Diff (Brute vs RandGrid) : " << diff_rand << endl;

    if (passed) {
        cout << "  Result                   : [PASSED]" << endl;
    } else {
        cout << "  Result                   : [FAILED]" << endl;
    }
    return passed;
}

// Edge case test for duplicate / identical points (min distance = 0)
template <size_t Dim>
bool run_duplicate_points_test() {
    cout << "--------------------------------------------------------" << endl;
    cout << "Running Edge Case Test: Duplicate points (0 distance) in " << Dim << "D" << endl;

    vector<Point<Dim>> points(100);
    for (size_t i = 0; i < points.size(); ++i) {
        for (size_t d = 0; d < Dim; ++d) {
            points[i].coordinates[d] = static_cast<float>((i + 1) * 10);
        }
    }
    // Force points 10 and 50 to be identical
    points[50] = points[10];

    float min_brute = find_min_dist_brute_force<Dim>(points);
    float min_grid = find_min_dist_grid_based<Dim>(points, false);
    float min_rand = find_min_dist_grid_based_randomized<Dim>(points, false);

    bool passed = (min_brute == 0.0f) && (min_grid == 0.0f) && (min_rand == 0.0f);

    cout << "  Brute Force Min Dist     : " << min_brute << endl;
    cout << "  Grid-Based Min Dist      : " << min_grid << endl;
    cout << "  Randomized Grid Min Dist : " << min_rand << endl;
    cout << "  Result                   : " << (passed ? "[PASSED]" : "[FAILED]") << endl;

    return passed;
}

int main() {
    cout << "========================================================" << endl;
    cout << "          N-Dimensional Closest Pair Validation         " << endl;
    cout << "========================================================" << endl;

    bool all_passed = true;

    // Run tests across different dimensions and sizes
    all_passed &= run_validation_test<2, 100>("2D Small Set");
    all_passed &= run_validation_test<2, 2000>("2D Medium Set");
    all_passed &= run_validation_test<3, 100>("3D Small Set");
    all_passed &= run_validation_test<3, 2000>("3D Medium Set");
    all_passed &= run_validation_test<4, 500>("4D Medium Set");

    // Run edge case tests
    all_passed &= run_duplicate_points_test<2>();
    all_passed &= run_duplicate_points_test<3>();

    cout << "========================================================" << endl;
    if (all_passed) {
        cout << " ALL VALIDATION TESTS PASSED SUCCESSFULLY! " << endl;
        cout << "========================================================" << endl;
        return 0;
    } else {
        cout << " SOME VALIDATION TESTS FAILED. CHECK LOGS ABOVE. " << endl;
        cout << "========================================================" << endl;
        return 1;
    }
}
