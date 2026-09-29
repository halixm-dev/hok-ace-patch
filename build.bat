@echo off
rem Build dist\HOK ACE Mobile English Patcher.exe
cd /d "%~dp0"
.venv\Scripts\python.exe app\build_exe.py || exit /b 1
echo.
echo Done: dist\HOK ACE Mobile English Patcher.exe
