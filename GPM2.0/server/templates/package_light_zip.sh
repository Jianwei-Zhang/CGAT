#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"
archive_helper="${server_dir}/.prepare_lib/tools/delivery_archive.py"
archive_path="$(python3 "$archive_helper" path --server-dir "$server_dir" --kind light)"
app_packager="${server_dir}/.prepare_lib/tools/grt_app_package.py"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"
[[ -f "$app_packager" ]] || { echo "Missing App package builder: $app_packager" >&2; exit 1; }

temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.package-light.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT
temporary_archive="${temporary_dir}/$(basename "$archive_path")"

python3 "$app_packager" \
  --source "$server_dir" \
  --staging "${temporary_dir}/${bundle_name}" \
  --no-fasta
python3 "$archive_helper" create --server-dir "$server_dir" --kind light \
  --staging "${temporary_dir}/${bundle_name}" --output "$temporary_archive"
mv -f -- "$temporary_archive" "$archive_path"
if [[ -z "${GPM_REPORT_RUN_ID:-}" && -f "${server_dir}/report/report.html" ]]; then
  python3 "${server_dir}/.prepare_lib/tools/server_report.py" \
    embed-delivery-report \
    --server-dir "$server_dir" \
    --archive "$archive_path"
fi
echo "Light delivery bundle: $archive_path"
