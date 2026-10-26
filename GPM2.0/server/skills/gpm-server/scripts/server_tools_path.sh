#!/usr/bin/env bash
# Validate the saved binding, or explicitly bind and register this skill.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$SCRIPT_DIR/server_paths.py" "$@"
