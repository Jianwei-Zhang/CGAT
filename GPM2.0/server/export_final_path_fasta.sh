#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${BASH:-bash}" "${SCRIPT_DIR}/templates/export_final_path_fasta.sh" "$@"
