#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'error: required command is unavailable: %s\n' "$command_name" >&2
    exit 127
  fi
}

run_group() {
  local name="$1"
  shift
  printf '::group::%s\n' "$name"
  "$@"
  printf '::endgroup::\n'
}

require_cmd bash
require_cmd python3

if [[ "${GPM_SKIP_GRT_SERVER_APP_E2E:-0}" != "1" ]]; then
  require_cmd cargo
  require_cmd node
  require_cmd zip
fi

cd "$project_root"

run_group "Tracked LF line endings" python3 scripts/check_line_endings.py

printf '::group::Shell syntax\n'
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find server tests/gpm_server -type f -name '*.sh' -print0)
printf '::endgroup::\n'

run_group "Python server tests" \
  python3 -m unittest discover -s server/tests -p 'test_*.py'

shell_tests=(
  tests/gpm_server/blast6_to_paf_test.sh
  tests/gpm_server/fake_command_control_test.sh
  tests/gpm_server/env_test.sh
  tests/gpm_server/package_templates_test.sh
  tests/gpm_server/prepare_metadata_test.sh
  tests/gpm_server/prepare_full_test.sh
  tests/gpm_server/final_path_test.sh
  tests/gpm_server/add_dataset_test.sh
  tests/gpm_server/add_ctg_test.sh
)

for shell_test in "${shell_tests[@]}"; do
  run_group "Shell test: $shell_test" bash "$shell_test"
done

if [[ "${GPM_SKIP_GRT_SERVER_APP_E2E:-0}" == "1" ]]; then
  printf '%s\n' \
    'SKIP: GRT server-to-app E2E was explicitly disabled with GPM_SKIP_GRT_SERVER_APP_E2E=1.' \
    'This local run is incomplete; CI and the canonical server gate do not set this override.'
else
  run_group "GRT server-to-app E2E" bash tests/gpm_server/grt_server_to_app_e2e.sh
fi

printf 'GPM2.0 server quality gate passed.\n'
