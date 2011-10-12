project(stdiobufhack C)

cmake_minimum_required(VERSION 2.4)

add_library(stdiobufhack SHARED stdiobufhack.c)

set_target_properties(stdiobufhack PROPERTIES COMPILE_FLAGS "-O2 -std=gnu99 -Wall")
target_link_libraries(stdiobufhack dl)
