#!/usr/bin/env bash
# One interactive entrypoint. Keep the caller cwd for project detection.
set -euo pipefail
if (( $# )); then
  printf "Usage: bash update.sh (no arguments; checks first, then asks [y/N])\n" >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$SCRIPT_DIR/tools/update_server.py" "$SCRIPT_DIR"
