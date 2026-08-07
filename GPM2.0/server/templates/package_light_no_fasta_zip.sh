#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"
archive_path="${parent_dir}/${bundle_name}.no_fasta.zip"
app_packager="${server_dir}/.prepare_lib/tools/grt_app_package.py"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"
[[ -f "$app_packager" ]] || { echo "Missing App package builder: $app_packager" >&2; exit 1; }

temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.package-light.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT
temporary_archive="${temporary_dir}/${bundle_name}.no_fasta.zip"

python3 "$app_packager" \
  --source "$server_dir" \
  --staging "${temporary_dir}/${bundle_name}" \
  --no-fasta
(
  cd "$temporary_dir"
  zip -rq "$temporary_archive" "$bundle_name"
)
mv -f -- "$temporary_archive" "$archive_path"
echo "Light delivery bundle: $archive_path"
