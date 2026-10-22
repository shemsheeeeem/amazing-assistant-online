@echo off
setlocal
title Remove amazingassistantonline.com

net session >nul 2>&1
if errorlevel 1 (
  echo Asking Windows for permission...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -Command "$h = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'; $keep = Get-Content $h | Where-Object { $_ -notmatch 'amazingassistantonline\.com' }; Set-Content -Path $h -Value $keep -Encoding ASCII"
ipconfig /flushdns >nul

echo.
echo  Done. amazingassistantonline.com no longer points to this computer.
echo.
pause
