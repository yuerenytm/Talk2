#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/build.py
fi
exec python3 scripts/build.py
