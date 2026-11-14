@echo off
rem Starts Divi and opens it in your web browser.
rem Close this window to stop Divi. Everything stays on this computer.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Divi needs the program "uv" to run.
  echo Install it from https://docs.astral.sh/uv/ and then double-click this file again.
  pause
  exit /b 1
)
echo Starting Divi... your browser will open in a moment.
uv run divi ui
pause
