#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
runtime_dir="${server_dir}/.prepare_lib"
if [[ -e "${server_dir}/.runtime/workspace.json" || -L "${server_dir}/.runtime/workspace.json" ]]; then
  runtime_dir="${server_dir}/.runtime/prepared"
fi
if [[ -f "${runtime_dir}/tools/workspace_layout.py" ]]; then
  runtime_dir="$(python3 "${runtime_dir}/tools/workspace_layout.py" --server-dir "$server_dir" --path .prepare_lib)"
elif [[ -e "${server_dir}/.runtime/workspace.json" || -e "${server_dir}/.runtime/migration.json" ]]; then
  printf 'ERROR: numbered/migrating workspace has no layout-aware prepared runtime; recover migration before running.\n' >&2
  exit 2
fi
tools_dir=""
if [[ -f "${runtime_dir}/server-tools.path" ]]; then
  IFS= read -r tools_dir < "${runtime_dir}/server-tools.path" || true
fi
if [[ -n "$tools_dir" && -f "$tools_dir/update.sh" ]]; then
  exec bash "$tools_dir/update.sh" --launch-workspace "$server_dir" "$@"
fi
printf "[UPDATE] Original installation unavailable; using the prepared runtime.\n" >&2
exec python3 "${runtime_dir}/tools/run_all_runner.py" --server-dir "$server_dir" "$@"
