#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture_root="${repo_root}/tests/fixtures/grt_contract_v1/valid/gpm_server"
task_tmp_dir="$(mktemp -d /tmp/gpm2-grt-server-app-e2e.XXXXXX)"
task_cargo_target="${GPM_GRT_E2E_CARGO_TARGET_DIR:-/tmp/gpm2-grt-e2e-cargo-target}"

cleanup() {
  rm -rf -- "${task_tmp_dir}"
}
trap cleanup EXIT

assert_contains() {
  local value="$1"
  local expected="$2"
  if [[ "${value}" != *"${expected}"* ]]; then
    echo "missing expected output: ${expected}" >&2
    exit 1
  fi
}

cd "${repo_root}"

python3 server/tools/grt_contract.py \
  --bundle "${fixture_root}" \
  --schema server/contracts/grt_precomputed_v1.json >/dev/null

CARGO_TARGET_DIR="${task_cargo_target}" cargo build \
  --locked \
  --manifest-path app/backend/Cargo.toml >/dev/null
backend_exe="${task_cargo_target}/debug/gpm_next_backend"

workspace="${task_tmp_dir}/valid/gpm_server"
mkdir -p "$(dirname "${workspace}")"
cp -a "${fixture_root}" "${workspace}"
"${backend_exe}" import-extracted "${workspace}" >/dev/null

initializer_output="$("${backend_exe}" list-project-initializer-options "${workspace}")"
assert_contains "${initializer_output}" '"recipe_id":"recipe-test"'
assert_contains "${initializer_output}" '"packageMode":"full"'

initialize_output="$("${backend_exe}" initialize-project "${workspace}" e2e-project)"
assert_contains "${initialize_output}" "project_id=1"
assert_contains "${initialize_output}" "reference_genome_id=1"
assert_contains "${initialize_output}" "primary_dataset_id=1"
assert_contains "${initialize_output}" "support_dataset_ids=2"
assert_contains "${initialize_output}" "materialized_source_card_count=1"
assert_contains "${initialize_output}" '"recipe_id":"recipe-test"'

project_view="$("${backend_exe}" get-grt-project-view "${workspace}" 1)"
assert_contains "${project_view}" '"segment_id":"seg-patch-1"'
assert_contains "${project_view}" '"source_card_key":"support:donor1:Chr01:grt_promoted"'

source_trace="$("${backend_exe}" get-grt-source-card-trace \
  "${workspace}" 1 support:donor1:Chr01:grt_promoted)"
assert_contains "${source_trace}" '"event_id":"evt-step1-round1"'
assert_contains "${source_trace}" '"evidence_id":"ev-display-donor1"'

event_trace="$("${backend_exe}" get-grt-event-trace "${workspace}" 1 evt-step1-round1)"
assert_contains "${event_trace}" '"segment_id":"seg-patch-1"'
assert_contains "${event_trace}" '"source_card_key":"support:donor1:Chr01:grt_promoted"'

evidence_trace="$("${backend_exe}" get-grt-evidence "${workspace}" 1 ev-display-donor1)"
assert_contains "${evidence_trace}" '"evidence_id":"ev-display-donor1"'
assert_contains "${evidence_trace}" '"stage":"display_pairwise"'

if "${backend_exe}" get-grt-project-view "${workspace}" 999 >/dev/null 2>&1; then
  echo "missing project unexpectedly returned a GRT project view" >&2
  exit 1
fi

legacy_workspace="${task_tmp_dir}/legacy/gpm_server"
mkdir -p "$(dirname "${legacy_workspace}")"
cp -a "${fixture_root}" "${legacy_workspace}"
python3 - "${legacy_workspace}/metadata/package.tsv" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = path.read_text(encoding="utf-8")
path.write_text(
    value.replace("gpm_grt_precomputed_v1", "gpm_legacy", 1),
    encoding="utf-8",
    newline="",
)
PY
if "${backend_exe}" import-extracted "${legacy_workspace}" >/dev/null 2>&1; then
  echo "legacy package unexpectedly imported" >&2
  exit 1
fi
if [[ -e "${legacy_workspace}/project.sqlite" ]]; then
  echo "rejected legacy package left project.sqlite behind" >&2
  exit 1
fi

node --test \
  app/frontend/src/services/__tests__/workflow-api.test.mjs \
  app/frontend/src/ui/pages/__tests__/workspace-i18n.test.mjs \
  app/frontend/src/ui/pages/assembly/__tests__/grt-state.test.mjs \
  app/frontend/src/ui/pages/assembly/__tests__/grt-visualization.test.mjs >/dev/null

echo "GRT Server-to-App E2E passed"
