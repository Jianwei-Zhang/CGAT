#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"

cd "$parent_dir"
zip -r "${bundle_name}.zip" "$bundle_name"
