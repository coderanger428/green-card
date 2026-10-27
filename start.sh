#!/usr/bin/env bash
# The launcher to open. Default = run the app.
#   ./start.sh          scraper + dashboard  ->  http://127.0.0.1:8007
#   ./start.sh watch    live UI reload       ->  http://127.0.0.1:5173
#   ./start.sh stop     shut everything down

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY=""
fi
if [[ -z "$PY" ]] || ! "$PY" -c "import sys" >/dev/null 2>&1; then
  echo "Project .venv is missing or its Python is gone." >&2
  echo "Recreate it with this machine's Python, then re-run ./start.sh:" >&2
  echo "  python -m venv .venv" >&2
  echo "  .venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows" >&2
  echo "  .venv/bin/python -m pip install -r requirements.txt            # Linux/macOS" >&2
  exit 1
fi

exec "$PY" "$ROOT/launch.py" "$@"
