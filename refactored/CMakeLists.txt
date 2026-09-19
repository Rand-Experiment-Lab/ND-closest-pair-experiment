cmake_minimum_required(VERSION 3.16)

project(ND-closest-pair-refactored VERSION 2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Optimized release flags for modern SIMD / AVX2
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG -Wall -Wextra")

find_package(TBB REQUIRED)
find_package(Threads REQUIRED)

include_directories(${CMAKE_CURRENT_SOURCE_DIR})

# ==============================================================================
# Modular Core & Experiment Targets
# ==============================================================================
add_executable(bin_synthetic experiments/synthetic/benchmark_synthetic.cpp)
target_link_libraries(bin_synthetic PRIVATE TBB::tbb Threads::Threads)

add_executable(bin_opensky experiments/opensky/benchmark_opensky.cpp)
target_link_libraries(bin_opensky PRIVATE TBB::tbb Threads::Threads)

add_executable(bin_cache experiments/cache/benchmark_cache.cpp)
target_link_libraries(bin_cache PRIVATE TBB::tbb Threads::Threads)
