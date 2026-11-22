#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
runtime_dir="${server_dir}/.prepare_lib"
if [[ -e "${server_dir}/.runtime/workspace.json" || -L "${server_dir}/.runtime/workspace.json" ]]; then
  runtime_area="$(python3 -I - "$server_dir" <<'PYRUNTIME'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
marker = root / ".runtime/workspace.json"
if marker.is_symlink() or marker.parent.is_symlink():
    sys.exit("ERROR: invalid Server workspace marker")
declaration = json.loads(marker.read_text(encoding="utf-8"))
print(".lib" if declaration.get("prepared_runtime") == ".lib" else ".runtime/prepared")
PYRUNTIME
)"
  runtime_dir="${server_dir}/${runtime_area}"
fi
if [[ -L "$runtime_dir" || -L "${runtime_dir}/tools" ]]; then
  printf 'ERROR: prepared runtime must not traverse a symlink.\n' >&2
  exit 2
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
