@echo off
rem Create .venv with Python 3.12 and install dependencies.
rem Override the interpreter with:  set PYTHON=C:\path\to\python.exe
cd /d "%~dp0"
if "%PYTHON%"=="" set PYTHON=py -3.12
%PYTHON% -m venv .venv || exit /b 1
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
