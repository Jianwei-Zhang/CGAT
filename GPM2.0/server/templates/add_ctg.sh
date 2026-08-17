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

ctg_name=""
chr_name=""
target_track=""
input_src=""
source_text=""
out_path=""
derived_dataset="derived_ctg"

usage() {
  cat <<'USAGE'
Usage:
  bash add_ctg.sh --ctg <new_ctg_name> --chr <chr_name> --track <dataset_name> -i <single_sequence_fasta> [-o|--out <add_zip_path>] [--source <free_text>]

Adds one derived ctg to this prepared gpm_server directory, updates the server state,
and writes an add_ctg package zip. The default output is ./add_<new_ctg_name>.zip.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ctg)
      [[ $# -ge 2 ]] || die "--ctg requires <new_ctg_name>"
      [[ -z "$ctg_name" ]] || die "--ctg may only be provided once"
      ctg_name="$2"
      shift 2
      ;;
    --chr)
      [[ $# -ge 2 ]] || die "--chr requires <chr_name>"
      [[ -z "$chr_name" ]] || die "--chr may only be provided once"
      chr_name="$2"
      shift 2
      ;;
    --track)
      [[ $# -ge 2 ]] || die "--track requires <dataset_name>"
      [[ -z "$target_track" ]] || die "--track may only be provided once"
      target_track="$2"
      shift 2
      ;;
    -i|--input)
      [[ $# -ge 2 ]] || die "$1 requires <single_sequence_fasta>"
      [[ -z "$input_src" ]] || die "$1 may only be provided once"
      input_src="$(resolve_path "$2")"
      shift 2
      ;;
    --source)
      [[ $# -ge 2 ]] || die "--source requires <free_text>"
      source_text="$2"
      shift 2
      ;;
    -o|--out|--output)
      [[ $# -ge 2 ]] || die "$1 requires <add_ctg_zip_path>"
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

[[ -n "$ctg_name" ]] || die "Missing --ctg"
[[ -n "$chr_name" ]] || die "Missing --chr"
[[ -n "$target_track" ]] || die "Missing --track"
[[ -n "$input_src" ]] || die "Missing -i/--input"
validate_name "$ctg_name"
validate_name "$chr_name"
validate_name "$target_track"
ensure_readable_file "$input_src"

case "${input_src,,}" in
  *.gz)
    die ".fa.gz inputs are not supported by add_ctg.sh; provide a plain single-sequence FASTA."
    ;;
esac

[[ -f "${server_dir}/metadata/prepare_options.tsv" ]] || die "Missing metadata/prepare_options.tsv"
[[ -f "${server_dir}/metadata/datasets.tsv" ]] || die "Missing metadata/datasets.tsv"
[[ -f "${server_dir}/metadata/reference.tsv" ]] || die "Missing metadata/reference.tsv"
[[ -f "${server_dir}/metadata/reference_chr_locator.tsv" ]] || die "Missing metadata/reference_chr_locator.tsv; run run_all.sh before add_ctg.sh"
[[ -f "${server_dir}/metadata/chr_assignments.tsv" ]] || die "Missing metadata/chr_assignments.tsv; run run_all.sh before add_ctg.sh"
[[ -f "${server_dir}/metadata/source_seq_locator.tsv" ]] || die "Missing metadata/source_seq_locator.tsv; run run_all.sh before add_ctg.sh"

require_cmd samtools
require_cmd zip
require_cmd python3

alignment_engine="$(read_prepare_option alignment_engine || printf 'minimap2')"
skip_self="$(read_prepare_option skip_self)"
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
  out_path="${server_dir}/add_${ctg_name}.zip"
fi

stage_dir="$(mktemp -d "$(dirname "$server_dir")/.add_ctg.${ctg_name}.XXXXXX")"
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

python3 "${stage_dir}/.prepare_lib/tools/add_ctg_stage.py" prepare \
  --server-dir "$stage_dir" \
  --ctg "$ctg_name" \
  --chr "$chr_name" \
  --track "$target_track" \
  --input "$input_src" \
  --source "$source_text"

ensure_fai "${stage_dir}/data/derived_ctgs/${ctg_name}.fa"
ensure_fai "${stage_dir}/data/datasets/${derived_dataset}.fa"
ensure_fai "${stage_dir}/runs/chr_${chr_name}/datasets/${derived_dataset}.fa"

bash "${stage_dir}/runs/add_ctg/${ctg_name}_vs_ref/command.sh"
if [[ "$skip_self" != "true" ]]; then
  for command_path in "${stage_dir}/runs/chr_${chr_name}/add_ctg/"*_vs_"${ctg_name}"/command.sh; do
    [[ -e "$command_path" ]] || continue
    bash "$command_path"
  done
fi

python3 "${stage_dir}/.prepare_lib/tools/add_ctg_stage.py" finalize \
  --server-dir "$stage_dir" \
  --ctg "$ctg_name" \
  --chr "$chr_name" \
  --track "$target_track" \
  --input "$input_src" \
  --source "$source_text"

python3 "${stage_dir}/.prepare_lib/tools/track_member_order.py" \
  --server-dir "$stage_dir"

python3 "${stage_dir}/.prepare_lib/tools/promote_server_stage.py" \
  --stage-dir "$stage_dir" \
  --server-dir "$server_dir" \
  --entry add_ctg.sh

package_dir="$(mktemp -d "$(dirname "$server_dir")/.add_ctg_package.${ctg_name}.XXXXXX")"
mkdir -p "${package_dir}/add_ctg" "${package_dir}/gpm_server"

python3 "${server_dir}/.prepare_lib/tools/add_ctg_package.py" \
  "$server_dir" \
  "$package_dir" \
  "$ctg_name"

mkdir -p "$(dirname "$out_path")"
(cd "$package_dir" && zip -r "$out_path" add_ctg gpm_server >/dev/null)

echo "Added ctg '${ctg_name}' to track '${target_track}' on ${chr_name}: ${server_dir}"
echo "Add ctg package: ${out_path}"
