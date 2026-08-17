#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
common_lib="${server_dir}/.prepare_lib/lib/incremental_common.sh"
[[ -f "$common_lib" ]] || {
  echo "ERROR: Missing .prepare_lib/lib/incremental_common.sh" >&2
  exit 1
}
# shellcheck source=../lib/incremental_common.sh
source "$common_lib"

dataset_name=""
dataset_src=""
out_path=""

usage() {
  cat <<'USAGE'
Usage:
  bash add_dataset.sh --ds <dataset_name> <dataset_fasta_path> [-o|--out <add_zip_path>]

Adds one dataset to this prepared gpm_server directory, updates the server state,
and writes an add package zip. The default output is ./add_<dataset_name>.zip.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ds)
      [[ $# -ge 3 ]] || die "--ds requires <dataset_name> <dataset_fasta_path>"
      [[ -z "$dataset_name" ]] || die "--ds may only be provided once"
      dataset_name="$2"
      dataset_src="$3"
      shift 3
      ;;
    -o|--out|--output)
      [[ $# -ge 2 ]] || die "$1 requires <add_zip_path>"
      [[ -n "$2" ]] || die "$1 requires a non-empty output path"
      out_path="$(resolve_path "$2")"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$dataset_name" ]] || die "Missing --ds"
validate_name "$dataset_name"
ensure_readable_file "$dataset_src"

[[ -f "${server_dir}/metadata/prepare_options.tsv" ]] || die "Missing metadata/prepare_options.tsv"
[[ -f "${server_dir}/metadata/datasets.tsv" ]] || die "Missing metadata/datasets.tsv"
[[ -f "${server_dir}/metadata/reference.tsv" ]] || die "Missing metadata/reference.tsv"
[[ -x "${server_dir}/assign_chr_groups.sh" ]] || die "Missing executable assign_chr_groups.sh"

require_cmd samtools
require_cmd zip
require_cmd gzip
require_cmd python3

if awk -F '\t' -v name="$dataset_name" 'NR > 1 && $1 == name { found = 1 } END { exit found ? 0 : 1 }' "${server_dir}/metadata/datasets.tsv"; then
  die "Duplicate dataset name: ${dataset_name}"
fi

alignment_engine="$(read_prepare_option alignment_engine || printf 'minimap2')"
minimap_preset="$(read_prepare_option minimap_preset || printf 'asm10')"
blastn_task="$(read_prepare_option blastn_task || printf 'blastn')"
blastn_evalue="$(read_prepare_option blastn_evalue || printf '1e-10')"
blastn_dust="$(read_prepare_option blastn_dust || printf 'no')"
winnowmap_preset="$(read_prepare_option winnowmap_preset || printf 'asm20')"
winnowmap_kmer="$(read_prepare_option winnowmap_kmer || printf '19')"
winnowmap_repeat_fraction="$(read_prepare_option winnowmap_repeat_fraction || printf '0.9998')"
threads="$(read_prepare_option threads)"
chr_score="$(read_prepare_option chr_assignment_min_coverage_percent)"
skip_self="$(read_prepare_option skip_self)"
tel_enabled="$(read_prepare_option tel_enabled || printf 'false')"
cen_enabled="$(read_prepare_option cen_enabled || printf 'false')"

case "$alignment_engine" in
  minimap2)
    require_cmd minimap2
    ;;
  blastn)
    require_cmd makeblastdb
    require_cmd blastn
    [[ -f "${server_dir}/.prepare_lib/tools/blast6_to_paf.py" ]] || die "Missing .prepare_lib/tools/blast6_to_paf.py"
    ;;
  winnowmap)
    require_cmd meryl
    require_cmd winnowmap
    ;;
  *)
    die "Unsupported alignment_engine in metadata/prepare_options.tsv: ${alignment_engine}"
    ;;
esac

if [[ -z "$out_path" ]]; then
  out_path="${server_dir}/add_${dataset_name}.zip"
fi

stage_dir="$(mktemp -d "$(dirname "$server_dir")/.add_dataset.${dataset_name}.XXXXXX")"
package_dir=""
cleanup() {
  rm -rf "$stage_dir"
  if [[ -n "$package_dir" ]]; then
    rm -rf "$package_dir"
  fi
}
trap cleanup EXIT

cp -a "${server_dir}/." "$stage_dir/"
rm -f "${stage_dir}"/add_*.zip "${stage_dir}/$(basename "$server_dir").zip" "${stage_dir}/$(basename "$server_dir").no_fasta.zip"

stage_ds_fa="${stage_dir}/data/datasets/${dataset_name}.fa"
mkdir -p "$(dirname "$stage_ds_fa")" "${stage_dir}/runs/${dataset_name}_vs_ref"
materialize_fasta_input "$dataset_src" "$stage_ds_fa"
ensure_fai "$stage_ds_fa"

python3 "${stage_dir}/.prepare_lib/tools/add_dataset_stage.py" \
  "$stage_dir" \
  "$server_dir" \
  "$dataset_name" \
  "$chr_score" \
  "$alignment_engine" \
  "$minimap_preset" \
  "$blastn_task" \
  "$blastn_evalue" \
  "$blastn_dust" \
  "$winnowmap_preset" \
  "$winnowmap_kmer" \
  "$winnowmap_repeat_fraction" \
  "$threads" \
  "$skip_self"

bash "${stage_dir}/runs/${dataset_name}_vs_ref/command.sh"
bash "${stage_dir}/assign_chr_groups.sh"

while IFS= read -r command_script; do
  bash "$command_script"
done < <(find "${stage_dir}/runs" -mindepth 3 -maxdepth 3 -path '*/chr_*/*/command.sh' | LC_ALL=C sort)

python3 "${stage_dir}/.prepare_lib/tools/validate_add_dataset_stage.py" "$stage_dir" "$dataset_name"

python3 "${stage_dir}/.prepare_lib/tools/promote_server_stage.py" \
  --stage-dir "$stage_dir" \
  --server-dir "$server_dir"

package_dir="$(mktemp -d "$(dirname "$server_dir")/.add_package.${dataset_name}.XXXXXX")"
mkdir -p "${package_dir}/add_package" "${package_dir}/gpm_server"

python3 "${server_dir}/.prepare_lib/tools/add_dataset_package.py" \
  "$server_dir" \
  "$package_dir" \
  "$dataset_name" \
  "$chr_score" \
  "$alignment_engine" \
  "$minimap_preset" \
  "$blastn_task" \
  "$blastn_evalue" \
  "$blastn_dust" \
  "$winnowmap_preset" \
  "$winnowmap_kmer" \
  "$winnowmap_repeat_fraction" \
  "$skip_self" \
  "$tel_enabled" \
  "$cen_enabled"

mkdir -p "$(dirname "$out_path")"
(cd "$package_dir" && zip -r "$out_path" add_package gpm_server >/dev/null)

echo "Added dataset '${dataset_name}' to: ${server_dir}"
echo "Add package: ${out_path}"
