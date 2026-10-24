# The wireless debugging provider's SPAKE2 step, ported from Shizuku's adb_pairing.cpp (Apache-2.0):
# the rest of pairing (TLS, HKDF, AES-GCM) runs in Kotlin. See android/native/THIRD_PARTY.md.
cmake_minimum_required(VERSION 3.22.1)
project("hokace_adb")

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-fno-exceptions -fno-rtti -fvisibility=hidden)
# 16 KiB pages, as for the codec builds.
add_link_options(-Wl,-z,max-page-size=16384 -Wl,--exclude-libs,ALL -Wl,--gc-sections)

find_package(boringssl REQUIRED CONFIG)

add_library(hokace_adb SHARED adb_pairing.cpp)
target_link_libraries(hokace_adb boringssl::crypto_static)
