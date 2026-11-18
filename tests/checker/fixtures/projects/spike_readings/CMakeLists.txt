cmake_minimum_required(VERSION 3.28)
project(spike_readings LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(readings STATIC src/readings.cpp)
target_include_directories(readings PUBLIC include)

add_executable(readings_app app/main.cpp)
target_link_libraries(readings_app PRIVATE readings)

add_executable(readings_checks checks/readings_checks.cpp)
target_link_libraries(readings_checks PRIVATE readings)
