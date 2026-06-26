#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "$server_dir")"
bundle_name="$(basename "$server_dir")"

cd "$parent_dir"
if [[ "__PACKAGE_MODE__" == "fast" && "__SEQUENCE_LAYOUT__" == "partitioned" ]]; then
  zip_args=(-r "${bundle_name}.zip" "$bundle_name")

  while IFS= read -r fasta_relpath; do
    zip_args+=(-x "${bundle_name}/${fasta_relpath}")
  done < <(awk -F '\t' 'NR > 1 && $4 != "" { print $4 }' "${server_dir}/metadata/reference.tsv")

  while IFS= read -r fasta_relpath; do
    zip_args+=(-x "${bundle_name}/${fasta_relpath}")
  done < <(awk -F '\t' 'NR > 1 && $4 != "" { print $4 }' "${server_dir}/metadata/datasets.tsv")

  zip "${zip_args[@]}"
else
  zip -r "${bundle_name}.zip" "$bundle_name"
fi
