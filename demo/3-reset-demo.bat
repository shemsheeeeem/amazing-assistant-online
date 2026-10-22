@echo off
setlocal
cd /d "%~dp0"
title Reset demo

echo.
echo  This deletes every account, job, application, and review made on this
echo  computer, and brings back the sample data.
echo  Close the black window of the running site before you continue.
echo.
choice /c YN /m "Reset the demo now"
if errorlevel 2 exit /b

if exist "%~dp0data" rmdir /s /q "%~dp0data"
if exist "%~dp0data" (
  echo.
  echo  Could not delete the data folder. Close the running site's black window
  echo  and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo  Done. Start the site again with 2-run-demo.bat
echo.
pause
