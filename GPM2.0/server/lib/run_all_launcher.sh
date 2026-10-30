#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
tools_dir=""
if [[ -f "${server_dir}/.prepare_lib/server-tools.path" ]]; then
  IFS= read -r tools_dir < "${server_dir}/.prepare_lib/server-tools.path" || true
fi
if [[ -n "$tools_dir" && -f "$tools_dir/update.sh" ]]; then
  exec bash "$tools_dir/update.sh" --launch-workspace "$server_dir" "$@"
fi
printf "[UPDATE] Original installation unavailable; using the prepared runtime.\n" >&2
exec python3 "${server_dir}/.prepare_lib/tools/run_all_runner.py" --server-dir "$server_dir" "$@"
