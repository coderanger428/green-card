#!/usr/bin/env bash
# Optional: live-reload UI while editing frontend/.
# Daily use / after Python or template changes: ./start.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/start.sh" watch
