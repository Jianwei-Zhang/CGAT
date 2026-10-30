#!/usr/bin/env bash
# Noninteractive update. Internal launch modes exec fresh code after the check.
set -euo pipefail
if (( $# )) && [[ "$1" != --launch-run && "$1" != --launch-workspace ]]; then
  printf "Usage: bash update.sh (no arguments required; checks and updates automatically)\n" >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$SCRIPT_DIR/tools/update_server.py" "$SCRIPT_DIR" "$@"
