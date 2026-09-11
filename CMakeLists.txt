cmake_minimum_required(VERSION 3.10)

project(ND-closest-pair-experiment)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)

add_executable(run main.cpp)
target_link_libraries(run tbb)
add_executable(experiment experiment.cpp)
target_link_libraries(experiment tbb)
add_executable(verify verify.cpp)
target_link_libraries(verify tbb)
add_executable(data_set_generator data_set_generator.cpp)
target_link_libraries(data_set_generator tbb)
add_executable(experiment_quick experiment_quick.cpp)
target_link_libraries(experiment_quick tbb)
add_executable(benchmark_hashers benchmark_hashers.cpp)
target_link_libraries(benchmark_hashers tbb)

