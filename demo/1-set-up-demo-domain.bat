@echo off
setlocal
title Set up amazingassistantonline.com

net session >nul 2>&1
if errorlevel 1 (
  echo Asking Windows for permission...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "HOSTS=%SystemRoot%\System32\drivers\etc\hosts"
findstr /i /c:"amazingassistantonline.com" "%HOSTS%" >nul
if errorlevel 1 (
  >>"%HOSTS%" echo(
  >>"%HOSTS%" echo 127.0.0.1 amazingassistantonline.com www.amazingassistantonline.com # Amazing Assistant Online demo
)
ipconfig /flushdns >nul

echo.
echo  Done. On this computer, amazingassistantonline.com now opens your demo site.
echo  Next: double-click 2-run-demo.bat
echo.
echo  This only affects this computer. To undo it, run 4-remove-demo-domain.bat
echo.
pause
