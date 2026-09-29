#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"
kind="light"
archive_helper="${server_dir}/.prepare_lib/tools/delivery_archive.py"
archive_path="$(python3 "$archive_helper" path --server-dir "$server_dir" --kind "$kind")"
staging_path="$(python3 "$archive_helper" staging-path --server-dir "$server_dir" --kind "$kind")"
app_packager="${server_dir}/.prepare_lib/tools/grt_app_package.py"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"
[[ -f "$app_packager" ]] || { echo "Missing App package builder: $app_packager" >&2; exit 1; }

temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.package-${kind}.XXXXXX")"
archive_temporary_dir=""
published_staging=false
retain_staging=false
cleanup() {
  rm -rf -- "$temporary_dir"
  if [[ -n "$archive_temporary_dir" ]]; then
    rm -rf -- "$archive_temporary_dir"
  fi
  if [[ "$published_staging" == "true" && "$retain_staging" != "true" ]]; then
    rm -rf -- "$(dirname "$staging_path")"
    rmdir --ignore-fail-on-non-empty "$(dirname "$(dirname "$staging_path")")" 2>/dev/null || true
  fi
}
trap cleanup EXIT

python3 "$app_packager" \
  --source "$server_dir" \
  --staging "${temporary_dir}/${bundle_name}" \
  --no-fasta
python3 "$archive_helper" publish-staging \
  --server-dir "$server_dir" --kind "$kind" \
  --staging "${temporary_dir}/${bundle_name}" >/dev/null
published_staging=true

if [[ -n "${GPM_REPORT_RUN_ID:-}" ]]; then
  retain_staging=true
  echo "Light delivery staging: $staging_path"
  exit 0
fi

if [[ -f "${server_dir}/report/report.html" ]]; then
  python3 "${server_dir}/.prepare_lib/tools/server_report.py" \
    finalize-delivery --server-dir "$server_dir" --kind "$kind"
else
  archive_temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.archive-${kind}.XXXXXX")"
  temporary_archive="${archive_temporary_dir}/$(basename "$archive_path")"
  python3 "$archive_helper" create --server-dir "$server_dir" --kind "$kind" \
    --staging "$staging_path" --output "$temporary_archive"
  mv -f -- "$temporary_archive" "$archive_path"
  rm -rf -- "$archive_temporary_dir" "$(dirname "$staging_path")"
  rmdir --ignore-fail-on-non-empty "$(dirname "$(dirname "$staging_path")")" 2>/dev/null || true
  published_staging=false
fi
echo "Light delivery bundle: $archive_path"
