@echo off
rem Build the ASTC oracle (oracle.cpp) from the hash-pinned astc-encoder-py 0.1.12 sdist's astcenc source.
rem   build.bat <sdist folder> <out folder> [extra cl flags, e.g. /DASTCENC_DIAGNOSTICS]
rem Flags mirror the sdist's setup.py for MSVC: /std:c++14 /EHsc /fp:precise, scalar ISA (all ASTCENC_* 0), /O2.
setlocal
set SRC=%~1\src\astc-encoder\Source
set OUT=%~2
if not exist "%OUT%" mkdir "%OUT%"
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cl /nologo /std:c++14 /EHsc /fp:precise /O2 /wd4324 /DNDEBUG /D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR ^
  /DASTCENC_NEON=0 /DASTCENC_SVE=0 /DASTCENC_SSE=0 /DASTCENC_AVX=0 /DASTCENC_POPCNT=0 /DASTCENC_F16C=0 %~3 ^
  /I"%SRC%" /Fo"%OUT%\\" /Fe"%OUT%\oracle.exe" "%~dp0oracle.cpp" ^
  "%SRC%\astcenc_averages_and_directions.cpp" "%SRC%\astcenc_block_sizes.cpp" "%SRC%\astcenc_color_quantize.cpp" ^
  "%SRC%\astcenc_color_unquantize.cpp" "%SRC%\astcenc_compress_symbolic.cpp" "%SRC%\astcenc_compute_variance.cpp" ^
  "%SRC%\astcenc_decompress_symbolic.cpp" "%SRC%\astcenc_diagnostic_trace.cpp" "%SRC%\astcenc_entry.cpp" ^
  "%SRC%\astcenc_find_best_partitioning.cpp" "%SRC%\astcenc_ideal_endpoints_and_weights.cpp" "%SRC%\astcenc_image.cpp" ^
  "%SRC%\astcenc_integer_sequence.cpp" "%SRC%\astcenc_mathlib.cpp" "%SRC%\astcenc_mathlib_softfloat.cpp" ^
  "%SRC%\astcenc_partition_tables.cpp" "%SRC%\astcenc_percentile_tables.cpp" "%SRC%\astcenc_pick_best_endpoint_format.cpp" ^
  "%SRC%\astcenc_quantization.cpp" "%SRC%\astcenc_symbolic_physical.cpp" "%SRC%\astcenc_weight_align.cpp" ^
  "%SRC%\astcenc_weight_quant_xfer_tables.cpp" || exit /b 1
