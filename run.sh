#!/usr/bin/env bash
# Run C++ Helper from source, setting up a local virtualenv on first use.
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "First run: creating .venv and installing dependencies…" >&2
    python3 -m venv .venv
    "$PY" -m pip install --upgrade pip >/dev/null
    "$PY" -m pip install -e .
fi

exec "$PY" -m cppjudge "$@"
