#!/usr/bin/env bash
set -euo pipefail
if (( $# )); then
  printf "Usage: bash scripts/update.sh (no arguments)\n" >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SERVER="$(bash "$SCRIPT_DIR/server_tools_path.sh")"
if [[ ! -f "$SERVER/update.sh" ]]; then
  printf "ERROR: This older Server has no update.sh. Use the documented verified legacy bootstrap; do not reinstall over it.\n" >&2
  exit 2
fi
export GPM_SERVER_SKILL_DIR="$(dirname -- "$SCRIPT_DIR")"
exec bash "$SERVER/update.sh"
