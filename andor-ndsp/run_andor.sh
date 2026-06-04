#!/usr/bin/env bash
# Andor SDK3 NDSP controller launcher (Linux/macOS — handy for --simulation tests).
#   ./run_andor.sh --simulation
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python3"
[ -x "$PY" ] || PY=python3
exec "$PY" "$HERE/aqctl_andor.py" -p "${PORT:-3287}" --bind '*' -v "$@"
