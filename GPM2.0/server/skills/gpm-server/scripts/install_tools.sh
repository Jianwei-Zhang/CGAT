#!/usr/bin/env bash
# Install tools only after destination and environment scope are confirmed.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$SCRIPT_DIR/install_tools.py" "$@"
