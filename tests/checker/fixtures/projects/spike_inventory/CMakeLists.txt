cmake_minimum_required(VERSION 3.28)
project(spike_inventory LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(inventory STATIC src/inventory.cpp)
target_include_directories(inventory PUBLIC include)

add_executable(inventory_app app/main.cpp)
target_link_libraries(inventory_app PRIVATE inventory)

add_executable(inventory_checks checks/inventory_checks.cpp)
target_link_libraries(inventory_checks PRIVATE inventory)
