cmake_minimum_required(VERSION 3.16)
project(OpenSky100M VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

message(STATUS "OpenSky 100M Benchmark - Build Type: ${CMAKE_BUILD_TYPE}")

# High performance compiler optimization flags (compatible with GCC 9+ and native AVX2)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG -Wall -Wextra")

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

add_executable(benchmark_100m src/main_100m.cpp)

find_package(Threads REQUIRED)
target_link_libraries(benchmark_100m PRIVATE Threads::Threads)
