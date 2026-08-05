#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"
archive_path="${parent_dir}/${bundle_name}.no_fasta.zip"

python3 "${server_dir}/.prepare_lib/tools/grt_contract.py" --bundle "$server_dir"

temporary_dir="$(mktemp -d "${parent_dir}/.${bundle_name}.package-light.XXXXXX")"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT
temporary_archive="${temporary_dir}/${bundle_name}.no_fasta.zip"

cd "$parent_dir"
zip_args=(-r "$temporary_archive" "$bundle_name")
while IFS= read -r fasta_path; do
  [[ -n "$fasta_path" ]] || continue
  zip_args+=(-x "$fasta_path")
done < <(find "$bundle_name" -type f \( -name '*.fa' -o -name '*.fasta' \) | LC_ALL=C sort)
zip "${zip_args[@]}"
mv -f -- "$temporary_archive" "$archive_path"
echo "Light delivery bundle: $archive_path"
