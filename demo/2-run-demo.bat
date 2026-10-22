@echo off
setlocal
cd /d "%~dp0"
title Amazing Assistant Online - demo

if not exist "%~dp0python\python.exe" (
  echo.
  echo  The "python" folder is missing. Extract the whole zip again and keep
  echo  every file and folder together.
  echo.
  pause
  exit /b 1
)

findstr /i /c:"amazingassistantonline.com" "%SystemRoot%\System32\drivers\etc\hosts" >nul
if errorlevel 1 (
  echo.
  echo  The demo address is not set up on this computer yet.
  echo  Double-click 1-set-up-demo-domain.bat first, then run this again.
  echo.
  pause
  exit /b 1
)

set "HANAP_PORT=80"
set "HANAP_DOMAIN=amazingassistantonline.com"
set "HANAP_OPEN_BROWSER=1"
"%~dp0python\python.exe" app.py
echo.
echo  The site has stopped. If you see an error above, send a screenshot of this window.
pause
