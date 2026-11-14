#!/bin/sh
# Starts Divi Maps (only the after-flight part: make maps, continue a stopped job) and opens it in your web browser (Linux and macOS).
# Close this window, or press Ctrl+C, to stop it. Everything stays on this computer.
cd "$(dirname "$0")" || exit 1
if ! command -v uv >/dev/null 2>&1; then
  echo 'Divi needs the program "uv" to run.'
  echo "Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "Then open a NEW terminal window and run this file again."
  exit 1
fi
echo "Starting Divi Maps... your browser will open in a moment."
exec uv run divi maps
