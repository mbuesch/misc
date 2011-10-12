project(stdiobufhack C)

add_library(stdiobufhack SHARED stdiobufhack.c)

target_link_libraries(stdiobufhack dl)
