#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"

cd "$parent_dir"
zip_args=(-r "${bundle_name}.no_fasta.zip" "$bundle_name")
while IFS= read -r fasta_path; do
  [[ -n "$fasta_path" ]] || continue
  zip_args+=(-x "$fasta_path")
done < <(find "$bundle_name" -type f \( -name '*.fa' -o -name '*.fasta' \) | LC_ALL=C sort)
zip "${zip_args[@]}"
