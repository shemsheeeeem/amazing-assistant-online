@echo off
setlocal
cd /d "%~dp0"
title Amazing Assistants Online

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo  Python is not installed on this computer.
  echo  Install it from https://www.python.org/downloads/
  echo  During setup, tick "Add python.exe to PATH", then run this file again.
  echo.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo  First run: setting up. This takes about a minute...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  Could not create the Python environment.
    pause
    exit /b 1
  )
)

.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo  Could not install the site. Check your internet connection and try again.
  pause
  exit /b 1
)

set "AAO_PORT=5070"
set "AAO_OPEN_BROWSER=1"
.venv\Scripts\python.exe app.py
pause
