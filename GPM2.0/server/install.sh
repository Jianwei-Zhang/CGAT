#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CGAT_SERVER_INSTALL_ENTRYPOINT="${SCRIPT_DIR}/install.sh"
exec "${BASH:-bash}" "${SCRIPT_DIR}/env.sh" "$@"
