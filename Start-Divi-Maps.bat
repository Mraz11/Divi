@echo off
rem Starts Divi Maps (only the after-flight part: make maps, continue a stopped job) and opens it in your web browser.
rem Close this window to stop Divi. Everything stays on this computer.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Divi needs the program "uv" to run.
  echo Install it from https://docs.astral.sh/uv/ and then double-click this file again.
  pause
  exit /b 1
)
echo Starting Divi Maps... your browser will open in a moment.
uv run divi maps
pause
