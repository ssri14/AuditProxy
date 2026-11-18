#!/usr/bin/env bash
# macOS / Linux launcher. Works from any working directory.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import PyQt6.QtWidgets' >/dev/null 2>&1; then
  echo "[AuditProxy] Environment missing or incomplete. Running setup first..."
  bash ./setup.sh
fi
# shellcheck disable=SC1091
source .venv/bin/activate
exec python app.py "$@"
