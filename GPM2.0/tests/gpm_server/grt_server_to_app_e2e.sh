#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture_root="${repo_root}/tests/fixtures/grt_contract_v2/valid/gpm_server"
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
  --schema server/contracts/grt_precomputed_v2.json >/dev/null

CARGO_TARGET_DIR="${task_cargo_target}" cargo build \
  --locked \
  --manifest-path app/backend/Cargo.toml >/dev/null
backend_exe="${task_cargo_target}/debug/gpm_next_backend"

app_full_stage="${task_tmp_dir}/app-full/gpm_server"
app_no_fasta_stage="${task_tmp_dir}/app-no-fasta/gpm_server"
python3 server/tools/grt_app_package.py \
  --source "${fixture_root}" \
  --staging "${app_full_stage}" \
  --include-fasta >/dev/null
python3 server/tools/grt_app_package.py \
  --source "${fixture_root}" \
  --staging "${app_no_fasta_stage}" \
  --no-fasta >/dev/null
(cd "${task_tmp_dir}/app-full" && zip -qr "${task_tmp_dir}/gpm_server.zip" gpm_server)
(cd "${task_tmp_dir}/app-no-fasta" && zip -qr "${task_tmp_dir}/gpm_server.no_fasta.zip" gpm_server)
legacy_app_stage="${task_tmp_dir}/app-v1/gpm_server"
mkdir -p "$(dirname "${legacy_app_stage}")"
cp -a "${app_full_stage}" "${legacy_app_stage}"
python3 - "${legacy_app_stage}" <<'PY'
import csv
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
package_path = root / "metadata/package.tsv"
with package_path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    rows = list(reader)
    fields = list(reader.fieldnames or [])
rows[0]["workflow"] = "gpm_grt_app_precomputed_v1"
rows[0]["schema_version"] = "1"
with package_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

for name in ("grt_app_manifest.json", "grt_final_path.json"):
    path = root / "metadata" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["workflow"] = "gpm_grt_app_precomputed_v1"
    if name == "grt_app_manifest.json":
        payload["schema_version"] = "1"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="")
PY
(cd "${task_tmp_dir}/app-v1" && zip -qr "${task_tmp_dir}/gpm_server.v1.zip" gpm_server)
python3 - "${task_tmp_dir}/gpm_server.zip" "${task_tmp_dir}/gpm_server.no_fasta.zip" <<'PY'
from pathlib import Path
from zipfile import ZipFile
import sys

for archive_name in sys.argv[1:]:
    with ZipFile(archive_name) as archive:
        names = [name for name in archive.namelist() if not name.endswith('/')]
        assert not any('/.prepare_lib/' in name for name in names), archive_name
        assert not any('/logs/' in name or '/.run_all/' in name for name in names), archive_name
        assert not any(name.endswith(('.sh', '.py')) for name in names), archive_name
        assert not any('/grt/cache/' in name or '/grt/checkpoints/' in name or '/grt/donors/' in name for name in names), archive_name
        assert not any('/grt/evidence/' in name for name in names), archive_name
        assert sum(name.lower().endswith(('.fa', '.fasta')) for name in names) == (4 if archive_name.endswith('gpm_server.zip') else 0), archive_name
        assert 'gpm_server/metadata/grt_app_manifest.json' in names, archive_name
        assert 'gpm_server/metadata/grt_final_path.json' in names, archive_name
        assert 'gpm_server/runs/primary_vs_ref/result.paf' in names, archive_name
print('App delivery allowlist passed')
PY

full_zip_workspace="${task_tmp_dir}/zip-full"
no_fasta_zip_workspace="${task_tmp_dir}/zip-no-fasta"
"${backend_exe}" import-zip "${task_tmp_dir}/gpm_server.zip" "${full_zip_workspace}" >/dev/null
"${backend_exe}" import-zip "${task_tmp_dir}/gpm_server.no_fasta.zip" "${no_fasta_zip_workspace}" >/dev/null
if "${backend_exe}" import-zip "${task_tmp_dir}/gpm_server.v1.zip" "${task_tmp_dir}/zip-v1" >/dev/null 2>&1; then
  echo "v1 App package unexpectedly imported" >&2
  exit 1
fi
if [[ -e "${task_tmp_dir}/zip-v1/project.sqlite" ]]; then
  echo "rejected v1 App package left project.sqlite behind" >&2
  exit 1
fi
full_zip_options="$(${backend_exe} list-project-initializer-options "${full_zip_workspace}")"
no_fasta_zip_options="$(${backend_exe} list-project-initializer-options "${no_fasta_zip_workspace}")"
assert_contains "${full_zip_options}" 'fasta_available=true'
assert_contains "${no_fasta_zip_options}" 'fasta_available=false'
"${backend_exe}" initialize-project "${full_zip_workspace}" full-zip-project >/dev/null
"${backend_exe}" initialize-project "${no_fasta_zip_workspace}" no-fasta-project >/dev/null
"${backend_exe}" get-grt-project-view "${no_fasta_zip_workspace}" 1 >/dev/null

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
    value.replace("gpm_grt_precomputed_v2", "gpm_grt_precomputed_v1", 1),
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
