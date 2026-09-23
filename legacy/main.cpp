#include <chrono>
#include <cstddef>
#include <iomanip>
#include <iostream>

#include "closest_pair.h"
#include "space.h"

using namespace std;

int main() {
    constexpr size_t Dim = 3;
    constexpr size_t NumPoints = 1'000'000;

    cout << "Generating " << NumPoints << " points in " << Dim << "D space..." << endl;
    auto start_gen = chrono::high_resolution_clock::now();
    Space<Dim, NumPoints> space;
    auto end_gen = chrono::high_resolution_clock::now();
    chrono::duration<double> gen_time = end_gen - start_gen;
    cout << "Space generated in " << gen_time.count() << " s." << endl;

    cout << fixed << setprecision(6);

    cout << "\n--- Scenario 1: Axis Sorted Grid-based Closest Pair ---" << endl;
    space.sort_points(SortStrategy::AxisAscending, 0);
    auto start_axis = chrono::high_resolution_clock::now();
    float min_dist_axis = find_min_dist_grid_based(space, false);
    auto end_axis = chrono::high_resolution_clock::now();
    chrono::duration<double> axis_time = end_axis - start_axis;
    cout << "Minimum distance (Axis Sorted)  : " << min_dist_axis << endl;
    cout << "Completed in                     : " << axis_time.count() << " s." << endl;

    cout << "\n--- Scenario 2: Distance to Origin Sorted Grid-based Closest Pair ---" << endl;
    space.sort_points(SortStrategy::DistanceToOriginAscending);
    auto start_dist_orig = chrono::high_resolution_clock::now();
    float min_dist_orig = find_min_dist_grid_based(space, false);
    auto end_dist_orig = chrono::high_resolution_clock::now();
    chrono::duration<double> dist_orig_time = end_dist_orig - start_dist_orig;
    cout << "Minimum distance (Origin Sorted): " << min_dist_orig << endl;
    cout << "Completed in                     : " << dist_orig_time.count() << " s." << endl;

    cout << "\n--- Scenario 3: Adversarial Sorted Grid-based Closest Pair ---" << endl;
    space.sort_points(SortStrategy::Adversarial);
    auto start_adv = chrono::high_resolution_clock::now();
    float min_dist_adv = find_min_dist_grid_based(space, false);
    auto end_adv = chrono::high_resolution_clock::now();
    chrono::duration<double> adv_time = end_adv - start_adv;
    cout << "Minimum distance (Adversarial)  : " << min_dist_adv << endl;
    cout << "Completed in                     : " << adv_time.count() << " s." << endl;

    cout << "\n--- Scenario 4: Randomized (Shuffled) Grid-based Closest Pair ---" << endl;
    auto start_rand = chrono::high_resolution_clock::now();
    float min_dist_rand = find_min_dist_grid_based_randomized(space, false);
    auto end_rand = chrono::high_resolution_clock::now();
    chrono::duration<double> rand_time = end_rand - start_rand;
    cout << "Minimum distance (Randomized Grid): " << min_dist_rand << endl;
    cout << "Completed in                     : " << rand_time.count() << " s." << endl;

    return 0;
}
