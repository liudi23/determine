#!/usr/bin/env bash
# Determine — quickstart: venv → install → tests → dry-run pipeline
# Usage:  bash quickstart.sh
set -euo pipefail

# always run from the folder this script lives in
cd "$(dirname "$0")"

# find a Python >= 3.11 (macOS system python3 is often 3.9, which is too old)
# note: an active venv can shadow `python3`, so leave any venv before searching
if [ -n "${VIRTUAL_ENV:-}" ]; then
    deactivate 2>/dev/null || true
fi
PY=""
for cand in python3.15 python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
            PY="$cand"
            break
        fi
    fi
done
if [ -z "$PY" ]; then
    echo "ERROR: no Python >= 3.11 found (your default python3 may be Apple's 3.9)."
    echo "Install one from https://www.python.org/downloads/ (or: brew install python@3.12),"
    echo "then re-run:  bash quickstart.sh"
    exit 1
fi
echo "Using $($PY --version) at $(command -v $PY)"

echo "==> 1/4 Creating isolated Python environment (.venv)"
if [ ! -d .venv ]; then
    "$PY" -m venv .venv
elif ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "    existing .venv uses an old Python — recreating it"
    rm -rf .venv
    "$PY" -m venv .venv
else
    echo "    .venv already exists — reusing it"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python --version

echo "==> 2/4 Installing Determine + dev tools"
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"

echo "==> 3/4 Running the test suite"
pytest

echo "==> 4/4 Dry-run pipeline on the sample corpus"
determine run "What is the W boson mass?"

echo ""
echo "Done. The full audit record is in runs/<run_id>.json (path printed above)."
echo "Tip: in future terminal sessions, activate the environment with:"
echo "    source .venv/bin/activate"
