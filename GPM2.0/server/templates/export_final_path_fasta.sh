#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_PATH=""

if [[ -f "${SCRIPT_DIR}/.prepare_lib/lib/final_path.sh" ]]; then
  LIB_PATH="${SCRIPT_DIR}/.prepare_lib/lib/final_path.sh"
elif [[ -f "${SCRIPT_DIR}/../lib/final_path.sh" ]]; then
  LIB_PATH="${SCRIPT_DIR}/../lib/final_path.sh"
else
  echo "ERROR: Missing final path export library" >&2
  exit 1
fi

if [[ -f "${SCRIPT_DIR}/metadata/datasets.tsv" ]]; then
  export GPM_FINAL_PATH_DEFAULT_SERVER_DIR="$SCRIPT_DIR"
fi

source "$LIB_PATH"
