#!/usr/bin/env bash
# macOS / Linux setup: create/reuse an isolated local Python environment.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# A user can override selection with PYTHON_BIN=/path/to/python3.12.
PYTHON=""
for candidate in "${PYTHON_BIN:-}" python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
  [[ -n "$candidate" ]] || continue
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: Python 3.10+ is required. Install it before running setup." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "[AuditProxy] Creating local environment: .venv"
  "$PYTHON" -m venv .venv || {
    echo "ERROR: Could not create .venv. Ensure python3-venv is installed (Linux)." >&2
    exit 1
  }
else
  echo "[AuditProxy] Reusing existing .venv"
fi

# Activation is intentionally explicit; the script also uses the venv interpreter.
# shellcheck disable=SC1091
source .venv/bin/activate
python - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit('ERROR: AuditProxy requires Python 3.10 or later.')
print('[AuditProxy] Python:', sys.version.split()[0])
PY

if python -c 'from PyQt6.QtWidgets import QApplication' >/dev/null 2>&1; then
  echo "[AuditProxy] PyQt6 already installed; no downloads needed."
else
  if [[ -d wheels ]] && find wheels -maxdepth 1 -name '*.whl' -print -quit | grep -q .; then
    echo "[AuditProxy] Installing from bundled OFFLINE wheels/"
    python -m pip install --no-index --find-links "$(pwd)/wheels" -r requirements.txt
  else
    echo "[AuditProxy] No local wheels/ found; installing dependencies via pip."
    echo "             This first-time step needs internet/package-index access."
    echo "             For fully offline setup, pre-populate wheels/ for this OS and Python."
    python -m pip install -r requirements.txt
  fi
fi
python -c 'from PyQt6.QtWidgets import QApplication; print("[AuditProxy] PyQt6 ready")'
echo "[AuditProxy] Setup complete. Start the app with ./run.sh"
