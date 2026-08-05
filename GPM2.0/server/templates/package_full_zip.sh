#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"
archive_path="${parent_dir}/${bundle_name}.zip"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"

temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.package-full.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT
temporary_archive="${temporary_dir}/${bundle_name}.zip"

cd "$parent_dir"
zip -r "$temporary_archive" "$bundle_name"
mv -f -- "$temporary_archive" "$archive_path"
echo "Full delivery bundle: $archive_path"
