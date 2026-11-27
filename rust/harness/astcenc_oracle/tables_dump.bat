@echo off
rem Build and run tables_dump.cpp against the pinned sdist: tables_dump.bat <sdist folder> <out folder>
rem Writes rust\hokace\astcenc\src\tables.rs and rust\hokace\astcenc\data\percentile.bin and sincos.bin.
setlocal
set SRC=%~1\src\astc-encoder\Source
set OUT=%~2
set CRATE=%~dp0..\..\hokace\astcenc
if not exist "%OUT%" mkdir "%OUT%"
if not exist "%CRATE%\data" mkdir "%CRATE%\data"
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cl /nologo /std:c++14 /EHsc /fp:precise /O2 /wd4324 /DNDEBUG ^
  /DASTCENC_NEON=0 /DASTCENC_SVE=0 /DASTCENC_SSE=0 /DASTCENC_AVX=0 /DASTCENC_POPCNT=0 /DASTCENC_F16C=0 ^
  /I"%SRC%" /Fo"%OUT%\\" /Fe"%OUT%\tables_dump.exe" "%~dp0tables_dump.cpp" ^
  "%SRC%\astcenc_quantization.cpp" "%SRC%\astcenc_weight_quant_xfer_tables.cpp" "%SRC%\astcenc_percentile_tables.cpp" ^
  "%SRC%\astcenc_mathlib_softfloat.cpp" || exit /b 1
"%OUT%\tables_dump.exe" "%CRATE%\src\tables.rs" "%CRATE%\data\percentile.bin" "%CRATE%\data\sincos.bin" || exit /b 1
