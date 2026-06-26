#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_ROOT="$(pwd)/gpm_server"
THREADS="10"
ALIGNER="minimap2"
MINIMAP_PRESET="asm10"
BLASTN_TASK="blastn"
BLASTN_EVALUE="1e-10"
BLASTN_DUST="no"
WINNOWMAP_PRESET="asm20"
WINNOWMAP_KMER="19"
WINNOWMAP_REPEAT_FRACTION="0.9998"
SKIP_SELF=false
CHR_ASSIGNMENT_MIN_COVERAGE_PERCENT="60"
CEN_SRC=""
CEN_MIN_LEN="10000"
CEN_MIN_IDENTITY="80"
MINIMAP_PRESET_SET=false
BLASTN_TASK_SET=false
BLASTN_EVALUE_SET=false
WINNOWMAP_PRESET_SET=false
WINNOWMAP_KMER_SET=false
WINNOWMAP_REPEAT_FRACTION_SET=false

usage() {
  cat <<'EOF'
Usage:
  bash server/prepare.sh \
    --ref <reference_name> <reference_fasta_path> \
    --ds <dataset_name> <dataset_fasta_path> \
    [-o|--out <gpm_server_output_dir>] \
    [--score|-s <chr_assignment_min_coverage_percent>] \
    [--aligner minimap2|blastn|winnowmap] \
    [--minimap-preset asm10|asm5] \
    [--blastn-task blastn|megablast|dc-megablast] \
    [--blastn-evalue <evalue>] \
    [--winnowmap-preset asm20|asm10|asm5] \
    [--winnowmap-kmer <kmer_size>] \
    [--winnowmap-repeat-fraction <fraction>] \
    [--threads|-t <alignment_threads>] \
    [--skip-self] \
    [--tel <motif> <min_repeat>] \
    [--cen <reference_centromere_fasta>] \
    [--cen-min-len <min_alignment_bp>] \
    [--cen-min-identity <min_identity_percent>] \
    [--ds <dataset_name> <dataset_fasta_path> ...]

Example:
  bash server/prepare.sh \
    --ref rice_IRGSP_1_0 /path/to/ref.fa \
    --ds hifi /path/to/hifi.fa \
    --ds flye /path/to/flye.fa \
    --score 60

Behavior:
  - Uses default work root: ./gpm_server under the current working directory
  - Supports -o/--out to choose another work root
  - Supports --score/-s to set the chr assignment coverage threshold, default: 60
  - Supports --aligner minimap2|blastn|winnowmap, default: minimap2
  - Supports --minimap-preset for minimap2 only, default: asm10
  - Supports --blastn-task and --blastn-evalue for blastn only, defaults: blastn and 1e-10
  - Supports --winnowmap-preset, --winnowmap-kmer, and --winnowmap-repeat-fraction for winnowmap only, defaults: asm20, 19, and 0.9998
  - Supports --threads/-t to choose alignment threads, default: 10
  - Supports repeatable --tel <motif> <min_repeat> to mark telomere-like tandem repeats
  - Supports --cen <reference_centromere_fasta> to mark complete reference centromere regions
  - Supports --cen-min-len and --cen-min-identity to filter centromere alignments
  - Generates staged chromosome-partitioned run commands
  - Supports --skip-self to omit dataset vs self alignments
  - Accepts plain FASTA inputs such as .fa/.fasta/.fna
  - Accepts gzip-compressed FASTA inputs such as .fa.gz/.fasta.gz/.fna.gz
  - Normalizes all inputs into package-local .fa files under data/
  - Creates .fai with samtools faidx when missing
  - Generates metadata/reference.tsv and metadata/datasets.tsv
  - Generates metadata/package.tsv
  - Generates runs/*/command.sh and <work_root>/run_all.sh
  - Chains run_all.sh commands with && so execution stops on the first failed command
  - Generates package_full_zip.sh, package_light_no_fasta_zip.sh, and export_final_path_fasta.sh
  - run_all.sh is staged as: vs_ref -> chr assignment helper -> per-chr commands
  - With --skip-self, same-dataset self alignments are omitted and marked unavailable in metadata/datasets.tsv
  - Prints all generated alignment commands to the terminal for manual copy/paste
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || die "Invalid name '$value'. Use only letters, numbers, dot, underscore, and hyphen."
}

validate_score() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "Invalid --score value '$value'. Use a number from 0 to 100."
  awk -v value="$value" 'BEGIN { exit (value >= 0 && value <= 100 ? 0 : 1) }' \
    || die "Invalid --score value '$value'. Use a number from 0 to 100."
}

validate_tel_motif() {
  local value="$1"
  [[ "$value" =~ ^[ACGTacgt]+$ ]] || die "Invalid --tel motif '$value'. Use only A/C/G/T bases."
}

validate_tel_repeat() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "Invalid --tel min_repeat '$value'. Use a positive integer."
}

validate_cen_min_len() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "Invalid --cen-min-len '$value'. Use a positive integer."
}

validate_cen_min_identity() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "Invalid --cen-min-identity '$value'. Use a number from 0 to 100."
  awk -v value="$value" 'BEGIN { exit (value >= 0 && value <= 100 ? 0 : 1) }' \
    || die "Invalid --cen-min-identity '$value'. Use a number from 0 to 100."
}

validate_minimap_preset() {
  local value="$1"
  case "$value" in
    asm10|asm5)
      ;;
    *)
      die "Invalid --minimap-preset '$value'. Use asm10 or asm5."
      ;;
  esac
}

validate_aligner() {
  local value="$1"
  case "$value" in
    minimap2|blastn|winnowmap)
      ;;
    *)
      die "Invalid --aligner '$value'. Use minimap2, blastn, or winnowmap."
      ;;
  esac
}

validate_blastn_task() {
  local value="$1"
  case "$value" in
    blastn|megablast|dc-megablast)
      ;;
    *)
      die "Invalid --blastn-task '$value'. Use blastn, megablast, or dc-megablast."
      ;;
  esac
}

validate_float_option() {
  local option_name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$ ]] || die "Invalid ${option_name} '$value'. Use a positive number."
  awk -v value="$value" 'BEGIN { exit (value > 0 ? 0 : 1) }' \
    || die "Invalid ${option_name} '$value'. Use a positive number."
}

validate_winnowmap_preset() {
  local value="$1"
  case "$value" in
    asm20|asm10|asm5)
      ;;
    *)
      die "Invalid --winnowmap-preset '$value'. Use asm20, asm10, or asm5."
      ;;
  esac
}

validate_winnowmap_kmer() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "Invalid --winnowmap-kmer '$value'. Use a positive integer."
}

validate_winnowmap_repeat_fraction() {
  local value="$1"
  validate_float_option "--winnowmap-repeat-fraction" "$value"
  awk -v value="$value" 'BEGIN { exit (value > 0 && value < 1 ? 0 : 1) }' \
    || die "Invalid --winnowmap-repeat-fraction '$value'. Use a number greater than 0 and less than 1."
}

validate_engine_specific_options() {
  case "$ALIGNER" in
    minimap2)
      [[ "$BLASTN_TASK_SET" == "false" ]] || die "--blastn-task is only valid with --aligner blastn; selected aligner: $ALIGNER"
      [[ "$BLASTN_EVALUE_SET" == "false" ]] || die "--blastn-evalue is only valid with --aligner blastn; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_PRESET_SET" == "false" ]] || die "--winnowmap-preset is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_KMER_SET" == "false" ]] || die "--winnowmap-kmer is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_REPEAT_FRACTION_SET" == "false" ]] || die "--winnowmap-repeat-fraction is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      ;;
    blastn)
      [[ "$MINIMAP_PRESET_SET" == "false" ]] || die "--minimap-preset is only valid with --aligner minimap2; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_PRESET_SET" == "false" ]] || die "--winnowmap-preset is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_KMER_SET" == "false" ]] || die "--winnowmap-kmer is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      [[ "$WINNOWMAP_REPEAT_FRACTION_SET" == "false" ]] || die "--winnowmap-repeat-fraction is only valid with --aligner winnowmap; selected aligner: $ALIGNER"
      ;;
    winnowmap)
      [[ "$MINIMAP_PRESET_SET" == "false" ]] || die "--minimap-preset is only valid with --aligner minimap2; selected aligner: $ALIGNER"
      [[ "$BLASTN_TASK_SET" == "false" ]] || die "--blastn-task is only valid with --aligner blastn; selected aligner: $ALIGNER"
      [[ "$BLASTN_EVALUE_SET" == "false" ]] || die "--blastn-evalue is only valid with --aligner blastn; selected aligner: $ALIGNER"
      ;;
  esac
}

validate_threads() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "Invalid --threads value '$value'. Use a positive integer."
}

ensure_readable_file() {
  local path="$1"
  [[ -f "$path" ]] || die "File not found: $path"
  [[ -r "$path" ]] || die "File is not readable: $path"
}

ensure_fai() {
  local fasta="$1"
  rm -f "${fasta}.fai"
  samtools faidx "$fasta"
}

materialize_fasta_input() {
  local src="$1"
  local dst="$2"
  case "${src,,}" in
    *.gz)
      gzip -dc -- "$src" > "$dst" || die "Failed to decompress gzip FASTA: $src"
      ;;
    *)
      cp -f "$src" "$dst"
      ;;
  esac
}

sanitize_fasta_basename() {
  local src="$1"
  local base
  base="$(basename "$src")"
  base="${base%.gz}"
  base="${base%.*}"
  base="$(printf '%s' "$base" | sed -E 's/[^A-Za-z0-9._-]+/_/g; s/-/_/g')"
  [[ -n "$base" ]] || base="ref_centromeres"
  printf '%s.fa\n' "$base"
}

shell_quote() {
  printf '%q' "$1"
}

alignment_tools_dir() {
  printf '%s/.prepare_lib/tools\n' "$WORK_ROOT"
}

write_alignment_command_script() {
  local output_path="$1"
  local run_dir="$2"
  local target_fa="$3"
  local query_fa="$4"
  local self_mode="$5"
  local result_name="${6:-result.paf}"
  local blast6_name="${result_name%.paf}.blast6"
  local target_db_dir="blastdb_${result_name%.paf}"
  local target_db_prefix="${target_db_dir}/target"
  local repetitive_db_dir="merylDB_${result_name%.paf}"
  local repetitive_txt="repetitive_${WINNOWMAP_KMER}_${result_name%.paf}.txt"
  local tools_dir
  tools_dir="$(alignment_tools_dir)"

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'cd %s\n' "$(shell_quote "$run_dir")"
    case "$ALIGNER" in
      minimap2)
        printf 'minimap2 -x %s ' "$(shell_quote "$MINIMAP_PRESET")"
        if [[ "$self_mode" == "true" ]]; then
          printf -- '-X '
        fi
        printf -- '-t %s -o %s %s %s > stdout.log 2> stderr.log\n' \
          "$(shell_quote "$THREADS")" \
          "$(shell_quote "$result_name")" \
          "$(shell_quote "$target_fa")" \
          "$(shell_quote "$query_fa")"
        ;;
      blastn)
        printf 'rm -rf %s\n' "$(shell_quote "$target_db_dir")"
        printf 'mkdir -p %s\n' "$(shell_quote "$target_db_dir")"
        printf 'makeblastdb -in %s -dbtype nucl -out %s > makeblastdb.stdout.log 2> makeblastdb.stderr.log\n' \
          "$(shell_quote "$target_fa")" \
          "$(shell_quote "$target_db_prefix")"
        printf 'blastn -task %s -query %s -db %s -num_threads %s -dust %s -evalue %s -outfmt %s -out %s > stdout.log 2> stderr.log\n' \
          "$(shell_quote "$BLASTN_TASK")" \
          "$(shell_quote "$query_fa")" \
          "$(shell_quote "$target_db_prefix")" \
          "$(shell_quote "$THREADS")" \
          "$(shell_quote "$BLASTN_DUST")" \
          "$(shell_quote "$BLASTN_EVALUE")" \
          "$(shell_quote "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps")" \
          "$(shell_quote "$blast6_name")"
        printf 'python3 %s --input %s --output %s\n' \
          "$(shell_quote "${tools_dir}/blast6_to_paf.py")" \
          "$(shell_quote "$blast6_name")" \
          "$(shell_quote "$result_name")"
        ;;
      winnowmap)
        printf 'rm -rf %s\n' "$(shell_quote "$repetitive_db_dir")"
        printf 'meryl count k=%s output %s %s > meryl.stdout.log 2> meryl.stderr.log\n' \
          "$(shell_quote "$WINNOWMAP_KMER")" \
          "$(shell_quote "$repetitive_db_dir")" \
          "$(shell_quote "$target_fa")"
        printf 'meryl print greater-than distinct=%s %s > %s\n' \
          "$(shell_quote "$WINNOWMAP_REPEAT_FRACTION")" \
          "$(shell_quote "$repetitive_db_dir")" \
          "$(shell_quote "$repetitive_txt")"
        printf 'winnowmap -W %s -x %s ' \
          "$(shell_quote "$repetitive_txt")" \
          "$(shell_quote "$WINNOWMAP_PRESET")"
        if [[ "$self_mode" == "true" ]]; then
          printf -- '-X '
        fi
        printf -- '-t %s %s %s > %s 2> stderr.log\n' \
          "$(shell_quote "$THREADS")" \
          "$(shell_quote "$target_fa")" \
          "$(shell_quote "$query_fa")" \
          "$(shell_quote "$result_name")"
        printf ': > stdout.log\n'
        ;;
    esac
  } > "$output_path"
  chmod +x "$output_path"
}

resolve_output_root() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$(pwd)/$path"
  fi
}

write_package_scripts() {
  local work_root="$1"
  local package_mode="$2"
  local sequence_layout="$3"
  local full_template="${SCRIPT_DIR}/templates/package_full_zip.sh"
  local light_template="${SCRIPT_DIR}/templates/package_light_no_fasta_zip.sh"

  [[ -f "$full_template" ]] || die "Missing template: $full_template"
  [[ -f "$light_template" ]] || die "Missing template: $light_template"

  cp -f "$full_template" "${work_root}/package_full_zip.sh"
  sed -i \
    -e "s/__PACKAGE_MODE__/${package_mode}/g" \
    -e "s/__SEQUENCE_LAYOUT__/${sequence_layout}/g" \
    "${work_root}/package_full_zip.sh"
  chmod +x "${work_root}/package_full_zip.sh"

  cp -f "$light_template" "${work_root}/package_light_no_fasta_zip.sh"
  chmod +x "${work_root}/package_light_no_fasta_zip.sh"
}

write_export_final_path_fasta_script() {
  local work_root="$1"
  local template_path="${SCRIPT_DIR}/templates/export_final_path_fasta.sh"

  [[ -f "$template_path" ]] || die "Missing template: $template_path"
  cp -f "$template_path" "${work_root}/export_final_path_fasta.sh"
  chmod +x "${work_root}/export_final_path_fasta.sh"
}

write_prepare_lib() {
  local work_root="$1"
  local lib_src="${SCRIPT_DIR}/lib"
  local lib_dst="${work_root}/.prepare_lib/lib"
  local tools_src="${SCRIPT_DIR}/tools"
  local tools_dst="${work_root}/.prepare_lib/tools"

  [[ -d "$lib_src" ]] || die "Missing server library directory: $lib_src"
  [[ -d "$tools_src" ]] || die "Missing server tools directory: $tools_src"
  rm -rf "$lib_dst"
  rm -rf "$tools_dst"
  mkdir -p "$(dirname "$lib_dst")"
  mkdir -p "$tools_dst"
  cp -R "$lib_src" "$lib_dst"
  cp -f "$tools_src"/*.py "$tools_dst"/
}

write_add_dataset_script() {
  local work_root="$1"

  cat > "${work_root}/add_dataset.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || die "Invalid name '$value'. Use only letters, numbers, dot, underscore, and hyphen."
}

ensure_readable_file() {
  local path="$1"
  [[ -f "$path" ]] || die "File not found: $path"
  [[ -r "$path" ]] || die "File is not readable: $path"
}

resolve_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$(pwd)/$path"
  fi
}

read_prepare_option() {
  local key="$1"
  awk -F '\t' -v key="$key" '
    NR == 1 { next }
    $1 == key { print $2; found = 1; exit }
    END { if (!found) exit 1 }
  ' "${server_dir}/metadata/prepare_options.tsv"
}

materialize_fasta_input() {
  local src="$1"
  local dst="$2"
  case "${src,,}" in
    *.gz)
      gzip -dc -- "$src" > "$dst" || die "Failed to decompress gzip FASTA: $src"
      ;;
    *)
      cp -f "$src" "$dst"
      ;;
  esac
}

ensure_fai() {
  local fasta="$1"
  rm -f "${fasta}.fai"
  samtools faidx "$fasta"
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

python3 - \
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
  "$skip_self" <<'PY'
import csv
import shlex
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_key_values(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)
    if not rows or rows[0] != ["key", "value"]:
        fail(f"invalid key/value metadata: {path}")
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


stage_dir = Path(sys.argv[1])
server_dir = Path(sys.argv[2])
dataset_name = sys.argv[3]
chr_score = sys.argv[4]
alignment_engine = sys.argv[5]
minimap_preset = sys.argv[6]
blastn_task = sys.argv[7]
blastn_evalue = sys.argv[8]
blastn_dust = sys.argv[9]
winnowmap_preset = sys.argv[10]
winnowmap_kmer = sys.argv[11]
winnowmap_repeat_fraction = sys.argv[12]
threads = sys.argv[13]
skip_self = sys.argv[14].lower() == "true"
metadata_dir = stage_dir / "metadata"
options = read_key_values(metadata_dir / "prepare_options.tsv")

package_fields = [
    "package_mode",
    "sequence_layout",
    "preassigned_chr",
    "chr_assignment_min_coverage_percent",
    "self_alignment_scope",
    "cross_alignment_scope",
]
package_values = {
    "package_mode": options.get("package_mode", "fast"),
    "sequence_layout": options.get("sequence_layout", "partitioned"),
    "preassigned_chr": options.get("preassigned_chr", "true"),
    "chr_assignment_min_coverage_percent": chr_score,
    "self_alignment_scope": "none" if skip_self else options.get("self_alignment_scope", "chr_partition"),
    "cross_alignment_scope": options.get("cross_alignment_scope", "chr_partition"),
}
with (metadata_dir / "package.tsv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(package_fields)
    writer.writerow([package_values[field] for field in package_fields])

datasets_path = metadata_dir / "datasets.tsv"
with datasets_path.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
if any(row.get("dataset_name") == dataset_name for row in rows):
    fail(f"Duplicate dataset name: {dataset_name}")
fieldnames = [
    "dataset_name",
    "assembler",
    "assembler_version",
    "fasta_relpath",
    "fai_relpath",
    "self_alignment_available",
]
rows.append(
    {
        "dataset_name": dataset_name,
        "assembler": dataset_name,
        "assembler_version": "",
        "fasta_relpath": f"data/datasets/{dataset_name}.fa",
        "fai_relpath": f"data/datasets/{dataset_name}.fa.fai",
        "self_alignment_available": "false" if skip_self else "true",
    }
)
with datasets_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

assign_script = stage_dir / "assign_chr_groups.sh"
text = assign_script.read_text(encoding="utf-8")
replacements = {
    "export GPM_FAST_WORK_ROOT=": shlex.quote(str(stage_dir)),
    "export GPM_FAST_THREADS=": shlex.quote(threads),
    "export GPM_FAST_ALIGNMENT_ENGINE=": shlex.quote(alignment_engine),
    "export GPM_FAST_MINIMAP_PRESET=": shlex.quote(minimap_preset),
    "export GPM_FAST_BLASTN_TASK=": shlex.quote(blastn_task),
    "export GPM_FAST_BLASTN_EVALUE=": shlex.quote(blastn_evalue),
    "export GPM_FAST_BLASTN_DUST=": shlex.quote(blastn_dust),
    "export GPM_FAST_WINNOWMAP_PRESET=": shlex.quote(winnowmap_preset),
    "export GPM_FAST_WINNOWMAP_KMER=": shlex.quote(winnowmap_kmer),
    "export GPM_FAST_WINNOWMAP_REPEAT_FRACTION=": shlex.quote(winnowmap_repeat_fraction),
    "export GPM_FAST_BLAST6_TO_PAF=": shlex.quote(str(stage_dir / ".prepare_lib" / "tools" / "blast6_to_paf.py")),
}
updated_lines = []
for line in text.splitlines():
    for prefix, value in replacements.items():
        if line.startswith(prefix):
            line = prefix + value
            break
    updated_lines.append(line)
assign_script.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
assign_script.chmod(0o755)

ref_path = metadata_dir / "reference.tsv"
with ref_path.open(newline="", encoding="utf-8") as handle:
    reference_rows = list(csv.DictReader(handle, delimiter="\t"))
if len(reference_rows) != 1:
    fail(f"expected exactly one reference row in {ref_path}")
reference_fa = stage_dir / reference_rows[0]["fasta_relpath"]
run_dir = stage_dir / "runs" / f"{dataset_name}_vs_ref"
command_path = run_dir / "command.sh"
dataset_fa = stage_dir / f"data/datasets/{dataset_name}.fa"
lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}"]
if alignment_engine == "minimap2":
    args = ["minimap2", "-x", minimap_preset, "-t", threads, "-o", "result.paf", str(reference_fa), str(dataset_fa)]
    lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
elif alignment_engine == "blastn":
    outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
    lines.extend(
        [
            "rm -rf blastdb_result",
            "mkdir -p blastdb_result",
            " ".join(shlex.quote(part) for part in ["makeblastdb", "-in", str(reference_fa), "-dbtype", "nucl", "-out", "blastdb_result/target"])
            + " > makeblastdb.stdout.log 2> makeblastdb.stderr.log",
            " ".join(
                shlex.quote(part)
                for part in [
                    "blastn",
                    "-task",
                    blastn_task,
                    "-query",
                    str(dataset_fa),
                    "-db",
                    "blastdb_result/target",
                    "-num_threads",
                    threads,
                    "-dust",
                    blastn_dust,
                    "-evalue",
                    blastn_evalue,
                    "-outfmt",
                    outfmt,
                    "-out",
                    "result.blast6",
                ]
            )
            + " > stdout.log 2> stderr.log",
            " ".join(
                shlex.quote(part)
                for part in [
                    "python3",
                    str(stage_dir / ".prepare_lib" / "tools" / "blast6_to_paf.py"),
                    "--input",
                    "result.blast6",
                    "--output",
                    "result.paf",
                ]
            ),
        ]
    )
elif alignment_engine == "winnowmap":
    lines.extend(
        [
            "rm -rf merylDB_result",
            " ".join(shlex.quote(part) for part in ["meryl", "count", f"k={winnowmap_kmer}", "output", "merylDB_result", str(reference_fa)])
            + " > meryl.stdout.log 2> meryl.stderr.log",
            " ".join(shlex.quote(part) for part in ["meryl", "print", "greater-than", f"distinct={winnowmap_repeat_fraction}", "merylDB_result"])
            + f" > {shlex.quote('repetitive_' + winnowmap_kmer + '_result.txt')}",
            " ".join(
                shlex.quote(part)
                for part in [
                    "winnowmap",
                    "-W",
                    f"repetitive_{winnowmap_kmer}_result.txt",
                    "-x",
                    winnowmap_preset,
                    "-t",
                    threads,
                    str(reference_fa),
                    str(dataset_fa),
                ]
            )
            + " > result.paf 2> stderr.log",
            ": > stdout.log",
        ]
    )
else:
    fail(f"unsupported alignment engine: {alignment_engine}")
command_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
command_path.chmod(0o755)
PY

bash "${stage_dir}/runs/${dataset_name}_vs_ref/command.sh"
bash "${stage_dir}/assign_chr_groups.sh"

while IFS= read -r command_script; do
  bash "$command_script"
done < <(find "${stage_dir}/runs" -mindepth 3 -maxdepth 3 -path '*/chr_*/*/command.sh' | LC_ALL=C sort)

python3 - "$stage_dir" "$dataset_name" <<'PY'
import csv
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


stage_dir = Path(sys.argv[1])
dataset_name = sys.argv[2]
required_files = [
    stage_dir / "metadata" / "datasets.tsv",
    stage_dir / "metadata" / "chr_assignments.tsv",
    stage_dir / "metadata" / "source_seq_locator.tsv",
    stage_dir / "data" / "datasets" / f"{dataset_name}.fa",
    stage_dir / "data" / "datasets" / f"{dataset_name}.fa.fai",
    stage_dir / "runs" / f"{dataset_name}_vs_ref" / "result.paf",
]
for path in required_files:
    if not path.exists():
        fail(f"staged add output is missing: {path}")

with (stage_dir / "metadata" / "datasets.tsv").open(newline="", encoding="utf-8") as handle:
    datasets = list(csv.DictReader(handle, delimiter="\t"))
if not any(row.get("dataset_name") == dataset_name for row in datasets):
    fail(f"staged datasets.tsv is missing dataset: {dataset_name}")

with (stage_dir / "metadata" / "source_seq_locator.tsv").open(newline="", encoding="utf-8") as handle:
    locators = list(csv.DictReader(handle, delimiter="\t"))
if not any(row.get("dataset_name") == dataset_name for row in locators):
    fail(f"staged source_seq_locator.tsv is missing dataset: {dataset_name}")
PY

python3 - "$stage_dir" "$server_dir" <<'PY'
import shutil
import sys
from pathlib import Path

stage_dir = Path(sys.argv[1])
server_dir = Path(sys.argv[2])

for path in stage_dir.rglob("*.sh"):
    text = path.read_text(encoding="utf-8")
    text = text.replace(str(stage_dir), str(server_dir))
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)

for name in [
    "metadata",
    "data",
    "runs",
    "tel",
    "cen",
    ".prepare_lib",
    "assign_chr_groups.sh",
    "run_all.sh",
    "package_full_zip.sh",
    "package_light_no_fasta_zip.sh",
    "export_final_path_fasta.sh",
    "add_dataset.sh",
]:
    src = stage_dir / name
    dst = server_dir / name
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if not src.exists():
        continue
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
        if name.endswith(".sh"):
            dst.chmod(0o755)
PY

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
EOF
  chmod +x "${work_root}/add_dataset.sh"
}

write_add_ctg_script() {
  local work_root="$1"

  cat > "${work_root}/add_ctg.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || die "Invalid name '$value'. Use only letters, numbers, dot, underscore, and hyphen."
}

ensure_readable_file() {
  local path="$1"
  [[ -f "$path" ]] || die "File not found: $path"
  [[ -r "$path" ]] || die "File is not readable: $path"
}

resolve_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$(pwd)/$path"
  fi
}

read_prepare_option() {
  local key="$1"
  awk -F '\t' -v key="$key" '
    NR == 1 { next }
    $1 == key { print $2; found = 1; exit }
    END { if (!found) exit 1 }
  ' "${server_dir}/metadata/prepare_options.tsv"
}

ensure_fai() {
  local fasta="$1"
  rm -f "${fasta}.fai"
  samtools faidx "$fasta"
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

python3 - "$stage_dir" "$server_dir" <<'PY'
import shutil
import sys
from pathlib import Path

stage_dir = Path(sys.argv[1])
server_dir = Path(sys.argv[2])

for path in stage_dir.rglob("*.sh"):
    text = path.read_text(encoding="utf-8")
    text = text.replace(str(stage_dir), str(server_dir))
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)

for name in [
    "metadata",
    "data",
    "runs",
    "tel",
    "cen",
    ".prepare_lib",
    "assign_chr_groups.sh",
    "run_all.sh",
    "package_full_zip.sh",
    "package_light_no_fasta_zip.sh",
    "export_final_path_fasta.sh",
    "add_dataset.sh",
    "add_ctg.sh",
]:
    src = stage_dir / name
    dst = server_dir / name
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if not src.exists():
        continue
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
        if name.endswith(".sh"):
            dst.chmod(0o755)
PY

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
EOF
  chmod +x "${work_root}/add_ctg.sh"
}

write_reference_segments_metadata() {
  local ref_fa="$1"
  local output_path="$2"

  awk -v min_gap_run_bp=100 -v output_path="$output_path" '
    function emit_segment(end_bp) {
      if (current_chr != "" && end_bp >= segment_start_bp) {
        segment_order += 1
        printf "%s\t%d\t%d\t%d\n", current_chr, segment_order, segment_start_bp, end_bp >> output_path
      }
    }

    function close_gap_if_needed(next_bp) {
      if (gap_run_length >= min_gap_run_bp) {
        emit_segment(gap_start_bp - 1)
        segment_start_bp = next_bp
      }
      gap_run_length = 0
      gap_start_bp = 0
    }

    function finish_record() {
      if (current_chr == "") {
        return
      }
      if (gap_run_length > 0) {
        close_gap_if_needed(sequence_bp + 1)
      }
      emit_segment(sequence_bp)
    }

    BEGIN {
      print "reference_chr_name\tsegment_order\tsegment_start_bp\tsegment_end_bp" > output_path
      current_chr = ""
      segment_order = 0
      segment_start_bp = 1
      sequence_bp = 0
      gap_run_length = 0
      gap_start_bp = 0
    }

    /^>/ {
      finish_record()
      current_chr = substr($0, 2)
      sub(/[[:space:]].*$/, "", current_chr)
      segment_order = 0
      segment_start_bp = 1
      sequence_bp = 0
      gap_run_length = 0
      gap_start_bp = 0
      next
    }

    {
      gsub(/[[:space:]]/, "", $0)
      for (i = 1; i <= length($0); i++) {
        base = substr($0, i, 1)
        sequence_bp += 1
        if (base == "N" || base == "n") {
          if (gap_run_length == 0) {
            gap_start_bp = sequence_bp
          }
          gap_run_length += 1
        } else if (gap_run_length > 0) {
          close_gap_if_needed(sequence_bp)
        }
      }
    }

    END {
      finish_record()
    }
  ' "$ref_fa"
}

collect_reference_chr_names() {
  local ref_fa="$1"
  awk '
    /^>/ {
      name = substr($0, 2)
      sub(/[[:space:]].*$/, "", name)
      print name
    }
  ' "$ref_fa"
}

write_package_metadata() {
  local output_path="$1"
  local package_mode="$2"
  local sequence_layout="$3"
  local preassigned_chr="$4"
  local self_alignment_scope="$5"
  local cross_alignment_scope="$6"

  {
    printf 'package_mode\tsequence_layout\tpreassigned_chr\tchr_assignment_min_coverage_percent\tself_alignment_scope\tcross_alignment_scope\n'
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$package_mode" \
      "$sequence_layout" \
      "$preassigned_chr" \
      "$CHR_ASSIGNMENT_MIN_COVERAGE_PERCENT" \
      "$self_alignment_scope" \
      "$cross_alignment_scope"
  } > "$output_path"
}

write_prepare_options_metadata() {
  local output_path="$1"
  local package_mode="$2"
  local sequence_layout="$3"
  local preassigned_chr="$4"
  local self_alignment_scope="$5"
  local cross_alignment_scope="$6"
  local tel_enabled="false"
  local cen_enabled="false"

  if [[ "${#TEL_RULE_ARGS[@]}" -gt 0 ]]; then
    tel_enabled="true"
  fi
  if [[ -n "$CEN_SRC" ]]; then
    cen_enabled="true"
  fi

  {
    printf 'key\tvalue\n'
    printf 'package_mode\t%s\n' "$package_mode"
    printf 'sequence_layout\t%s\n' "$sequence_layout"
    printf 'preassigned_chr\t%s\n' "$preassigned_chr"
    printf 'chr_assignment_min_coverage_percent\t%s\n' "$CHR_ASSIGNMENT_MIN_COVERAGE_PERCENT"
    printf 'alignment_engine\t%s\n' "$ALIGNER"
    printf 'minimap_preset\t%s\n' "$MINIMAP_PRESET"
    printf 'blastn_task\t%s\n' "$BLASTN_TASK"
    printf 'blastn_evalue\t%s\n' "$BLASTN_EVALUE"
    printf 'blastn_dust\t%s\n' "$BLASTN_DUST"
    printf 'winnowmap_preset\t%s\n' "$WINNOWMAP_PRESET"
    printf 'winnowmap_kmer\t%s\n' "$WINNOWMAP_KMER"
    printf 'winnowmap_repeat_fraction\t%s\n' "$WINNOWMAP_REPEAT_FRACTION"
    printf 'threads\t%s\n' "$THREADS"
    printf 'skip_self\t%s\n' "$SKIP_SELF"
    printf 'self_alignment_scope\t%s\n' "$self_alignment_scope"
    printf 'cross_alignment_scope\t%s\n' "$cross_alignment_scope"
    printf 'tel_enabled\t%s\n' "$tel_enabled"
    printf 'cen_enabled\t%s\n' "$cen_enabled"
    printf 'cen_min_len\t%s\n' "$CEN_MIN_LEN"
    printf 'cen_min_identity\t%s\n' "$CEN_MIN_IDENTITY"
  } > "$output_path"
}

write_tel_rules_metadata() {
  local output_path="$1"
  shift

  {
    printf 'rule_id\tmotif\tmin_repeat\treverse_complement\n'
    local rule_index=1
    while [[ $# -ge 2 ]]; do
      printf 'tel%s\t%s\t%s\ttrue\n' "$rule_index" "${1^^}" "$2"
      rule_index=$((rule_index + 1))
      shift 2
    done
  } > "$output_path"
}

write_cen_reference_metadata() {
  local output_path="$1"
  local cen_fasta="$2"
  local ref_fai="$3"
  local fasta_relpath="$4"

  python3 - "$output_path" "$cen_fasta" "$ref_fai" "$fasta_relpath" "$CEN_MIN_LEN" "$CEN_MIN_IDENTITY" <<'PY'
import csv
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


output_path = Path(sys.argv[1])
cen_fasta = Path(sys.argv[2])
ref_fai = Path(sys.argv[3])
fasta_relpath = sys.argv[4]
min_len = sys.argv[5]
min_identity = sys.argv[6]

ref_chrs = set()
with ref_fai.open(encoding="utf-8") as handle:
    for line in handle:
        fields = line.rstrip("\n").split("\t")
        if fields and fields[0]:
            ref_chrs.add(fields[0])

seen_chrs = set()
rows = []
with cen_fasta.open(encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.strip()
        if not line.startswith(">"):
            continue
        sequence_name = line[1:].split()[0]
        suffix = "_centromere"
        if not sequence_name.endswith(suffix):
            fail(f"--cen FASTA header must end with _centromere: {sequence_name}")
        chr_name = sequence_name[: -len(suffix)]
        if not chr_name:
            fail(f"--cen FASTA header has empty chromosome name: {sequence_name}")
        if chr_name in seen_chrs:
            fail(f"Duplicate --cen chromosome entry: {chr_name}")
        if chr_name not in ref_chrs:
            fail(f"Unknown --cen chromosome entry: {chr_name}")
        seen_chrs.add(chr_name)
        rows.append(["cen", chr_name, sequence_name, fasta_relpath, min_len, min_identity])

if not rows:
    fail("--cen FASTA contains no centromere records")

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["cen_id", "chr_name", "sequence_name", "fasta_relpath", "min_len", "min_identity"])
    writer.writerows(rows)
PY
}

write_ref_command_script() {
  local run_dir="$1"
  local ref_fa="$2"
  local ds_fa="$3"

  write_alignment_command_script "${run_dir}/command.sh" "$run_dir" "$ref_fa" "$ds_fa" false
}

write_assignment_script() {
  local output_path="$1"
  local work_root="$2"
  shift 2
  cat > "$output_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail

export GPM_FAST_WORK_ROOT=$(shell_quote "$work_root")
export GPM_FAST_THREADS=$(shell_quote "$THREADS")
export GPM_FAST_ALIGNMENT_ENGINE=$(shell_quote "$ALIGNER")
export GPM_FAST_MINIMAP_PRESET=$(shell_quote "$MINIMAP_PRESET")
export GPM_FAST_BLASTN_TASK=$(shell_quote "$BLASTN_TASK")
export GPM_FAST_BLASTN_EVALUE=$(shell_quote "$BLASTN_EVALUE")
export GPM_FAST_BLASTN_DUST=$(shell_quote "$BLASTN_DUST")
export GPM_FAST_WINNOWMAP_PRESET=$(shell_quote "$WINNOWMAP_PRESET")
export GPM_FAST_WINNOWMAP_KMER=$(shell_quote "$WINNOWMAP_KMER")
export GPM_FAST_WINNOWMAP_REPEAT_FRACTION=$(shell_quote "$WINNOWMAP_REPEAT_FRACTION")
export GPM_FAST_BLAST6_TO_PAF=$(shell_quote "${work_root}/.prepare_lib/tools/blast6_to_paf.py")

python3 - <<'PY'
import csv
import os
import shlex
import shutil
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_tsv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_single_tsv_row(path):
    rows = read_tsv_rows(path)
    if len(rows) != 1:
        fail(f"expected exactly one data row in {path}")
    return rows[0]


def read_fasta_records(path):
    records = []
    current_name = None
    current_sequence_parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_name is not None:
                    records.append((current_name, "".join(current_sequence_parts)))
                current_name = line[1:].split()[0]
                current_sequence_parts = []
                continue
            current_sequence_parts.append(line)
    if current_name is not None:
        records.append((current_name, "".join(current_sequence_parts)))
    return records


def merged_interval_coverage(intervals):
    if not intervals:
        return 0
    sorted_intervals = sorted(intervals)
    total = 0
    current_start, current_end = sorted_intervals[0]
    for start, end in sorted_intervals[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start + 1
        current_start, current_end = start, end
    return total + (current_end - current_start + 1)


def weighted_median_of_positions(values):
    sorted_values = sorted(values, key=lambda item: item[0])
    total_weight = sum(max(0, weight) for _, weight in sorted_values)
    if total_weight <= 0:
        return sorted_values[len(sorted_values) // 2][0]

    threshold = (total_weight // 2) + 1
    cumulative = 0
    for position, weight in sorted_values:
        cumulative += max(0, weight)
        if cumulative >= threshold:
            return position
    return sorted_values[-1][0]


def write_selected_fasta(path, ordered_records, selected_names):
    with path.open("w", encoding="utf-8") as handle:
        for name, sequence in ordered_records:
            if name not in selected_names:
                continue
            handle.write(f">{name}\n{sequence}\n")


def write_single_record_fasta(path, name, sequence):
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f">{name}\n{sequence}\n")


def iter_n_regions(sequence):
    index = 0
    while index < len(sequence):
        if sequence[index] not in {"N", "n"}:
            index += 1
            continue
        start = index
        while index < len(sequence) and sequence[index] in {"N", "n"}:
            index += 1
        yield start + 1, index, index - start


def write_run_command_script(path, run_dir, left_fa, right_fa, self_mode, threads, minimap_preset):
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}"]
    if alignment_engine == "minimap2":
        args = ["minimap2", "-x", minimap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, "-o", "result.paf", str(left_fa), str(right_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
    elif alignment_engine == "blastn":
        outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
        lines.extend(
            [
                "rm -rf blastdb_result",
                "mkdir -p blastdb_result",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "makeblastdb",
                        "-in",
                        str(left_fa),
                        "-dbtype",
                        "nucl",
                        "-out",
                        "blastdb_result/target",
                    ]
                )
                + " > makeblastdb.stdout.log 2> makeblastdb.stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "blastn",
                        "-task",
                        blastn_task,
                        "-query",
                        str(right_fa),
                        "-db",
                        "blastdb_result/target",
                        "-num_threads",
                        threads,
                        "-dust",
                        blastn_dust,
                        "-evalue",
                        blastn_evalue,
                        "-outfmt",
                        outfmt,
                        "-out",
                        "result.blast6",
                    ]
                )
                + " > stdout.log 2> stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "python3",
                        blast6_to_paf,
                        "--input",
                        "result.blast6",
                        "--output",
                        "result.paf",
                    ]
                ),
            ]
        )
    elif alignment_engine == "winnowmap":
        lines.extend(
            [
                "rm -rf merylDB_result",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "meryl",
                        "count",
                        f"k={winnowmap_kmer}",
                        "output",
                        "merylDB_result",
                        str(left_fa),
                    ]
                )
                + " > meryl.stdout.log 2> meryl.stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "meryl",
                        "print",
                        "greater-than",
                        f"distinct={winnowmap_repeat_fraction}",
                        "merylDB_result",
                    ]
                )
                + f" > {shlex.quote('repetitive_' + winnowmap_kmer + '_result.txt')}",
            ]
        )
        args = ["winnowmap", "-W", f"repetitive_{winnowmap_kmer}_result.txt", "-x", winnowmap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, str(left_fa), str(right_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > result.paf 2> stderr.log")
        lines.append(": > stdout.log")
    else:
        fail(f"unsupported alignment engine: {alignment_engine}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def write_tel_scan_command_script(path, run_dir, work_root, chr_name, selected_dataset_fastas):
    args = [str(work_root), chr_name]
    args.extend(f"{dataset_name}={fasta_path}" for dataset_name, fasta_path in selected_dataset_fastas)
    python_invocation = "python3 - " + " ".join(shlex.quote(part) for part in args) + " <<'PY'"
    scanner = r'''import csv
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_rules(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rules = []
    for row in rows:
        rule_id = str(row.get("rule_id", "")).strip()
        motif = str(row.get("motif", "")).strip().upper()
        try:
            min_repeat = int(row.get("min_repeat", ""))
        except ValueError:
            fail(f"invalid tel min_repeat in {path}: {row!r}")
        if not rule_id or not motif or min_repeat < 1:
            fail(f"invalid tel rule in {path}: {row!r}")
        rules.append(
            {
                "rule_id": rule_id,
                "motif": motif,
                "min_repeat": min_repeat,
            }
        )
    return rules


def read_fasta_records(path):
    records = []
    current_name = None
    current_parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_name is not None:
                    records.append((current_name, "".join(current_parts)))
                current_name = line[1:].split()[0]
                current_parts = []
                continue
            current_parts.append(line)
    if current_name is not None:
        records.append((current_name, "".join(current_parts)))
    return records


def reverse_complement(motif):
    table = str.maketrans("ACGTacgt", "TGCAtgca")
    return motif.translate(table)[::-1].upper()


def scan_pattern(sequence, pattern, min_repeat):
    seq = sequence.upper()
    motif = pattern.upper()
    motif_len = len(motif)
    if motif_len < 1:
        return
    index = 0
    limit = len(seq) - motif_len
    while index <= limit:
        count = 0
        while seq[index + count * motif_len : index + (count + 1) * motif_len] == motif:
            count += 1
        if count >= min_repeat:
            start_bp = index + 1
            end_bp = index + count * motif_len
            yield start_bp, end_bp, count
            index += count * motif_len
            continue
        index += 1


def iter_rule_hits(sequence, rule):
    motif = rule["motif"]
    min_repeat = rule["min_repeat"]
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, motif, min_repeat):
        yield start_bp, end_bp, repeat_count, "+"
    rc = reverse_complement(motif)
    if rc == motif:
        return
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, rc, min_repeat):
        yield start_bp, end_bp, repeat_count, "-"


def parse_dataset_specs(values):
    specs = []
    for value in values:
        if "=" not in value:
            fail(f"invalid dataset spec: {value}")
        dataset_name, fasta_path = value.split("=", 1)
        dataset_name = dataset_name.strip()
        fasta = Path(fasta_path)
        if not dataset_name or not fasta.exists():
            fail(f"invalid dataset spec: {value}")
        specs.append((dataset_name, fasta))
    return specs


work_root = Path(sys.argv[1])
chr_name = sys.argv[2]
dataset_specs = parse_dataset_specs(sys.argv[3:])
rules = read_rules(work_root / "tel" / "rules.tsv")
output_dir = work_root / "tel" / f"chr_{chr_name}"
output_dir.mkdir(parents=True, exist_ok=True)

header = [
    "rule_id",
    "dataset_name",
    "seq_name",
    "assigned_chr_name",
    "motif",
    "min_repeat",
    "repeat_count",
    "start_bp",
    "end_bp",
    "strand",
]

for dataset_name, fasta_path in dataset_specs:
    output_path = output_dir / f"{dataset_name}.tsv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        for seq_name, sequence in read_fasta_records(fasta_path):
            for rule in rules:
                for start_bp, end_bp, repeat_count, strand in iter_rule_hits(sequence, rule):
                    writer.writerow(
                        [
                            rule["rule_id"],
                            dataset_name,
                            seq_name,
                            chr_name,
                            rule["motif"],
                            rule["min_repeat"],
                            repeat_count,
                            start_bp,
                            end_bp,
                            strand,
                        ]
                    )
'''
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(run_dir))}\n"
        f"{python_invocation}\n"
        f"{scanner}\n"
        "PY\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_cen_scan_command_script(path, run_dir, work_root, chr_name, selected_dataset_fastas, threads, minimap_preset):
    cen_reference_path = work_root / "cen" / "reference.tsv"
    rows = read_tsv_rows(cen_reference_path)
    cen_row = next((row for row in rows if row.get("chr_name") == chr_name), None)
    if cen_row is None:
        return False

    cen_fasta = work_root / cen_row["fasta_relpath"]
    cen_query_name = cen_row["sequence_name"]
    cen_chr_fasta = run_dir / f"{chr_name}_centromere.fa"
    for name, sequence in read_fasta_records(cen_fasta):
        if name == cen_query_name:
            write_single_record_fasta(cen_chr_fasta, name, sequence)
            break
    else:
        fail(f"missing centromere sequence {cen_query_name} in {cen_fasta}")

    output_dir = work_root / "cen" / f"chr_{chr_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_specs = []
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}", ""]
    for index, (dataset_name, fasta_path) in enumerate(selected_dataset_fastas):
        result_name = "result.paf" if len(selected_dataset_fastas) == 1 else f"result_{dataset_name}.paf"
        result_path = run_dir / result_name
        dataset_specs.append(f"{dataset_name}={result_path}")
        if alignment_engine == "minimap2":
            args = [
                "minimap2",
                "-x",
                minimap_preset,
                "-t",
                threads,
                "-c",
                "--cs",
                "-o",
                result_name,
                str(fasta_path),
                str(cen_chr_fasta),
            ]
            command = " ".join(shlex.quote(part) for part in args)
            lines.append(f"{command} > stdout_{dataset_name}.log 2> stderr_{dataset_name}.log")
        elif alignment_engine == "blastn":
            blast6_name = result_name.replace(".paf", ".blast6")
            db_dir = f"blastdb_{dataset_name}"
            outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
            lines.extend(
                [
                    f"rm -rf {shlex.quote(db_dir)}",
                    f"mkdir -p {shlex.quote(db_dir)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "makeblastdb",
                            "-in",
                            str(fasta_path),
                            "-dbtype",
                            "nucl",
                            "-out",
                            f"{db_dir}/target",
                        ]
                    )
                    + f" > makeblastdb_{dataset_name}.stdout.log 2> makeblastdb_{dataset_name}.stderr.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "blastn",
                            "-task",
                            blastn_task,
                            "-query",
                            str(cen_chr_fasta),
                            "-db",
                            f"{db_dir}/target",
                            "-num_threads",
                            threads,
                            "-dust",
                            blastn_dust,
                            "-evalue",
                            blastn_evalue,
                            "-outfmt",
                            outfmt,
                            "-out",
                            blast6_name,
                        ]
                    )
                    + f" > stdout_{dataset_name}.log 2> stderr_{dataset_name}.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "python3",
                            blast6_to_paf,
                            "--input",
                            blast6_name,
                            "--output",
                            result_name,
                        ]
                    ),
                ]
            )
        elif alignment_engine == "winnowmap":
            meryl_dir = f"merylDB_{dataset_name}"
            repetitive_txt = f"repetitive_{winnowmap_kmer}_{dataset_name}.txt"
            lines.extend(
                [
                    f"rm -rf {shlex.quote(meryl_dir)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "meryl",
                            "count",
                            f"k={winnowmap_kmer}",
                            "output",
                            meryl_dir,
                            str(fasta_path),
                        ]
                    )
                    + f" > meryl_{dataset_name}.stdout.log 2> meryl_{dataset_name}.stderr.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "meryl",
                            "print",
                            "greater-than",
                            f"distinct={winnowmap_repeat_fraction}",
                            meryl_dir,
                        ]
                    )
                    + f" > {shlex.quote(repetitive_txt)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "winnowmap",
                            "-W",
                            repetitive_txt,
                            "-x",
                            winnowmap_preset,
                            "-t",
                            threads,
                            str(fasta_path),
                            str(cen_chr_fasta),
                        ]
                    )
                    + f" > {shlex.quote(result_name)} 2> stderr_{dataset_name}.log",
                    f": > stdout_{dataset_name}.log",
                ]
            )
        else:
            fail(f"unsupported alignment engine: {alignment_engine}")
    args = [
        str(work_root),
        chr_name,
        cen_row["sequence_name"],
        cen_row["min_len"],
        cen_row["min_identity"],
    ]
    args.extend(dataset_specs)
    python_invocation = "python3 - " + " ".join(shlex.quote(part) for part in args) + " <<'PY'"
    parser = r'''import csv
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def parse_dataset_specs(values):
    specs = []
    for value in values:
        if "=" not in value:
            fail(f"invalid dataset spec: {value}")
        dataset_name, paf_path = value.split("=", 1)
        dataset_name = dataset_name.strip()
        paf = Path(paf_path)
        if not dataset_name or not paf.exists():
            fail(f"invalid dataset spec: {value}")
        specs.append((dataset_name, paf))
    return specs


def parse_identity(fields):
    block_length = int(fields[10])
    if block_length <= 0:
        return 0.0
    for tag in fields[12:]:
        parts = tag.split(":", 2)
        if len(parts) != 3:
            continue
        key, tag_type, value = parts
        if key in {"dv", "de"} and tag_type == "f":
            try:
                divergence = float(value)
            except ValueError:
                continue
            return max(0.0, min(100.0, (1.0 - divergence) * 100.0))
    matches = int(fields[9])
    return max(0.0, min(100.0, (matches * 100.0) / block_length))


work_root = Path(sys.argv[1])
chr_name = sys.argv[2]
query_name = sys.argv[3]
min_len = int(sys.argv[4])
min_identity = float(sys.argv[5])
dataset_specs = parse_dataset_specs(sys.argv[6:])
output_dir = work_root / "cen" / f"chr_{chr_name}"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "marks.tsv"

header = [
    "cen_id",
    "chr_name",
    "query_name",
    "dataset_name",
    "ctg_name",
    "ctg_start",
    "ctg_end",
    "strand",
    "align_length",
    "identity",
    "mapq",
]

with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    for dataset_name, paf_path in dataset_specs:
        with paf_path.open(encoding="utf-8") as paf_handle:
            for raw_line in paf_handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    continue
                if fields[0] != query_name:
                    continue
                strand = fields[4]
                if strand not in {"+", "-"}:
                    continue
                align_length = int(fields[10])
                identity = parse_identity(fields)
                if align_length < min_len or identity < min_identity:
                    continue
                writer.writerow(
                    [
                        "cen",
                        chr_name,
                        query_name,
                        dataset_name,
                        fields[5],
                        int(fields[7]) + 1,
                        int(fields[8]),
                        strand,
                        align_length,
                        f"{identity:.3f}",
                        fields[11],
                    ]
                )
'''
    lines.extend(["", python_invocation, parser, "PY"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return True


def write_generated_command_script(path, command_paths, chr_name):
    if not command_paths:
        body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"echo {shlex.quote(f'No chr-local alignments to run for {chr_name}.')} >&2\n"
        )
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return

    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for index, command_path in enumerate(command_paths):
        quoted = shlex.quote(str(command_path))
        if index < len(command_paths) - 1:
            lines.append(f"bash {quoted} && \\\\")
        else:
            lines.append(f"bash {quoted}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


work_root = Path(os.environ["GPM_FAST_WORK_ROOT"])
threads = os.environ["GPM_FAST_THREADS"]
alignment_engine = os.environ.get("GPM_FAST_ALIGNMENT_ENGINE", "minimap2")
minimap_preset = os.environ["GPM_FAST_MINIMAP_PRESET"]
blastn_task = os.environ.get("GPM_FAST_BLASTN_TASK", "blastn")
blastn_evalue = os.environ.get("GPM_FAST_BLASTN_EVALUE", "1e-10")
blastn_dust = os.environ.get("GPM_FAST_BLASTN_DUST", "no")
winnowmap_preset = os.environ.get("GPM_FAST_WINNOWMAP_PRESET", "asm20")
winnowmap_kmer = os.environ.get("GPM_FAST_WINNOWMAP_KMER", "19")
winnowmap_repeat_fraction = os.environ.get("GPM_FAST_WINNOWMAP_REPEAT_FRACTION", "0.9998")
blast6_to_paf = os.environ.get(
    "GPM_FAST_BLAST6_TO_PAF",
    str(work_root / ".prepare_lib" / "tools" / "blast6_to_paf.py"),
)
metadata_dir = work_root / "metadata"
runs_dir = work_root / "runs"
package = read_single_tsv_row(metadata_dir / "package.tsv")
datasets = read_tsv_rows(metadata_dir / "datasets.tsv")
reference = read_single_tsv_row(metadata_dir / "reference.tsv")

try:
    threshold = float(package["chr_assignment_min_coverage_percent"])
except (KeyError, ValueError) as exc:
    fail(f"invalid chr_assignment_min_coverage_percent in package.tsv: {exc}")

skip_self = package.get("self_alignment_scope", "") == "none"
reference_fasta = work_root / reference["fasta_relpath"]
reference_records = read_fasta_records(reference_fasta)
reference_chr_names = [name for name, _sequence in reference_records]
reference_by_name = {name: sequence for name, sequence in reference_records}
if not reference_chr_names:
    fail(f"reference fasta has no chromosome records: {reference_fasta}")

dataset_infos = {}
dataset_order = []
for row in datasets:
    dataset_name = row["dataset_name"]
    fasta_path = work_root / row["fasta_relpath"]
    ordered_records = read_fasta_records(fasta_path)
    records_by_name = {name: sequence for name, sequence in ordered_records}
    dataset_order.append(dataset_name)
    dataset_infos[dataset_name] = {
        "fasta_path": fasta_path,
        "ordered_records": ordered_records,
        "records_by_name": records_by_name,
    }

candidate_map = {}
for dataset_name in dataset_order:
    paf_path = runs_dir / f"{dataset_name}_vs_ref" / "result.paf"
    if not paf_path.exists():
        fail(f"missing ref alignment result: {paf_path}")
    dataset_info = dataset_infos[dataset_name]
    records_by_name = dataset_info["records_by_name"]
    assert isinstance(records_by_name, dict)

    with paf_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                continue
            query_name = fields[0]
            sequence = records_by_name.get(query_name)
            if sequence is None:
                continue
            seq_length = max(len(sequence), 1)
            query_start = int(fields[2]) + 1
            query_end = int(fields[3])
            strand = fields[4]
            target_name = fields[5]
            ref_start = int(fields[7]) + 1
            block_length = int(fields[10])
            if strand not in ("+", "-"):
                continue
            if target_name not in reference_chr_names:
                continue
            if query_start < 1 or query_end < query_start or ref_start < 1:
                continue
            qualified = block_length >= 1000 or ((block_length * 100.0) / seq_length) >= 25.0
            if not qualified:
                continue
            candidate_anchor = (
                ref_start - query_start + 1
                if strand == "+"
                else ref_start - seq_length + query_end
            )
            key = (dataset_name, query_name, seq_length, target_name)
            bucket = candidate_map.setdefault(
                key,
                {"intervals": [], "anchor_weights": []},
            )
            bucket["intervals"].append((query_start, query_end))
            bucket["anchor_weights"].append((candidate_anchor, block_length))

assignment_rows = []
selected_by_chr_dataset = {
    chr_name: {} for chr_name in reference_chr_names
}
for dataset_name in dataset_order:
    dataset_info = dataset_infos[dataset_name]
    ordered_records = dataset_info["ordered_records"]
    assert isinstance(ordered_records, list)
    for seq_name, sequence in ordered_records:
        seq_length = max(len(sequence), 1)
        for chr_name in reference_chr_names:
            key = (dataset_name, seq_name, seq_length, chr_name)
            bucket = candidate_map.get(key)
            if bucket is None:
                continue
            intervals = bucket["intervals"]
            anchor_weights = bucket["anchor_weights"]
            assert isinstance(intervals, list)
            assert isinstance(anchor_weights, list)
            support_bp = merged_interval_coverage(intervals)
            support_percent = (support_bp * 100.0) / seq_length
            if support_percent < threshold:
                continue
            assignment_rows.append(
                {
                    "dataset_name": dataset_name,
                    "seq_name": seq_name,
                    "seq_length_bp": seq_length,
                    "assigned_chr_name": chr_name,
                    "support_bp": support_bp,
                    "support_percent": f"{support_percent:.3f}",
                    "anchor_start": weighted_median_of_positions(anchor_weights),
                }
            )
            selected_by_chr_dataset.setdefault(chr_name, {}).setdefault(dataset_name, set()).add(seq_name)

chr_assignments_path = metadata_dir / "chr_assignments.tsv"
with chr_assignments_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "support_bp",
            "support_percent",
            "anchor_start",
        ]
    )
    for row in assignment_rows:
        writer.writerow(
            [
                row["dataset_name"],
                row["seq_name"],
                row["seq_length_bp"],
                row["assigned_chr_name"],
                row["support_bp"],
                row["support_percent"],
                row["anchor_start"],
            ]
        )

reference_chr_dir = work_root / "data" / "reference" / "chrs"
if reference_chr_dir.exists():
    shutil.rmtree(reference_chr_dir)
reference_chr_dir.mkdir(parents=True, exist_ok=True)
for chr_name in reference_chr_names:
    chr_sequence = reference_by_name.get(chr_name)
    if chr_sequence is None:
        fail(f"missing reference sequence for {chr_name}")
    write_single_record_fasta(reference_chr_dir / f"{chr_name}.fa", chr_name, chr_sequence)

reference_locator_path = metadata_dir / "reference_chr_locator.tsv"
with reference_locator_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["reference_chr_name", "fasta_relpath"])
    for chr_name in reference_chr_names:
        writer.writerow([chr_name, f"data/reference/chrs/{chr_name}.fa"])

partition_root = work_root / "data" / "partitions"
partition_chr_root = partition_root / "chr"
partition_unplaced_root = partition_root / "unplaced"
if partition_root.exists():
    shutil.rmtree(partition_root)
partition_chr_root.mkdir(parents=True, exist_ok=True)
partition_unplaced_root.mkdir(parents=True, exist_ok=True)

source_locator_map = {}
for chr_name in reference_chr_names:
    chr_partition_dir = partition_chr_root / chr_name
    chr_partition_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name in dataset_order:
        selected_names = selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set())
        if not selected_names:
            continue
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        partition_fasta = chr_partition_dir / f"{dataset_name}.fa"
        write_selected_fasta(partition_fasta, ordered_records, selected_names)
        relpath = partition_fasta.relative_to(work_root).as_posix()
        for seq_name, _sequence in ordered_records:
            if seq_name in selected_names and (dataset_name, seq_name) not in source_locator_map:
                source_locator_map[(dataset_name, seq_name)] = relpath

for dataset_name in dataset_order:
    dataset_info = dataset_infos[dataset_name]
    ordered_records = dataset_info["ordered_records"]
    assert isinstance(ordered_records, list)
    assigned_names = set()
    for chr_name in reference_chr_names:
        assigned_names.update(selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set()))
    unassigned_names = {seq_name for seq_name, _sequence in ordered_records if seq_name not in assigned_names}
    if unassigned_names:
        unplaced_fasta = partition_unplaced_root / f"{dataset_name}.fa"
        write_selected_fasta(unplaced_fasta, ordered_records, unassigned_names)
        relpath = unplaced_fasta.relative_to(work_root).as_posix()
        for seq_name in unassigned_names:
            source_locator_map[(dataset_name, seq_name)] = relpath

source_locator_path = metadata_dir / "source_seq_locator.tsv"
with source_locator_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["dataset_name", "seq_name", "fasta_relpath"])
    for dataset_name in dataset_order:
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        for seq_name, _sequence in ordered_records:
            relpath = source_locator_map.get((dataset_name, seq_name))
            if relpath is None:
                fail(f"missing source locator for {dataset_name}:{seq_name}")
            writer.writerow([dataset_name, seq_name, relpath])

n_region_path = metadata_dir / "source_seq_n_regions.tsv"
assigned_by_dataset = {}
for chr_datasets in selected_by_chr_dataset.values():
    for dataset_name, selected_names in chr_datasets.items():
        assigned_by_dataset.setdefault(dataset_name, set()).update(selected_names)
with n_region_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"])
    for dataset_name in dataset_order:
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assigned_names = assigned_by_dataset.get(dataset_name, set())
        assert isinstance(ordered_records, list)
        for seq_name, sequence in ordered_records:
            if seq_name not in assigned_names:
                continue
            for start_bp, end_bp, length_bp in iter_n_regions(sequence):
                writer.writerow([dataset_name, seq_name, start_bp, end_bp, length_bp])

for chr_name in reference_chr_names:
    chr_run_dir = runs_dir / f"chr_{chr_name}"
    datasets_dir = chr_run_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    for stale_fasta in datasets_dir.glob("*.fa"):
        stale_fasta.unlink()
    for child in chr_run_dir.iterdir():
        if child.name in {"datasets", "command.sh", "generated_command.sh"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    selected_dataset_fastas = []
    for dataset_name in dataset_order:
        selected_names = selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set())
        if not selected_names:
            continue
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        output_fasta = datasets_dir / f"{dataset_name}.fa"
        write_selected_fasta(output_fasta, ordered_records, selected_names)
        selected_dataset_fastas.append((dataset_name, output_fasta))

    command_paths = []
    if not skip_self:
        for dataset_name, output_fasta in selected_dataset_fastas:
            run_dir = chr_run_dir / f"{dataset_name}_vs_self"
            run_dir.mkdir(parents=True, exist_ok=True)
            command_path = run_dir / "command.sh"
            write_run_command_script(
                command_path,
                run_dir,
                output_fasta,
                output_fasta,
                self_mode=True,
                threads=threads,
                minimap_preset=minimap_preset,
            )
            command_paths.append(command_path)

    for left_index, (left_name, left_fasta) in enumerate(selected_dataset_fastas):
        for right_name, right_fasta in selected_dataset_fastas[left_index + 1 :]:
            run_dir = chr_run_dir / f"{left_name}_vs_{right_name}"
            run_dir.mkdir(parents=True, exist_ok=True)
            command_path = run_dir / "command.sh"
            write_run_command_script(
                command_path,
                run_dir,
                left_fasta,
                right_fasta,
                self_mode=False,
                threads=threads,
                minimap_preset=minimap_preset,
            )
            command_paths.append(command_path)

    tel_rules_path = work_root / "tel" / "rules.tsv"
    if tel_rules_path.exists() and selected_dataset_fastas:
        run_dir = chr_run_dir / "tel_scan"
        run_dir.mkdir(parents=True, exist_ok=True)
        command_path = run_dir / "command.sh"
        write_tel_scan_command_script(
            command_path,
            run_dir,
            work_root,
            chr_name,
            selected_dataset_fastas,
        )
        command_paths.append(command_path)

    cen_reference_path = work_root / "cen" / "reference.tsv"
    if cen_reference_path.exists() and selected_dataset_fastas:
        run_dir = chr_run_dir / "cen_scan"
        run_dir.mkdir(parents=True, exist_ok=True)
        command_path = run_dir / "command.sh"
        if write_cen_scan_command_script(
            command_path,
            run_dir,
            work_root,
            chr_name,
            selected_dataset_fastas,
            threads,
            minimap_preset,
        ):
            command_paths.append(command_path)

    write_generated_command_script(chr_run_dir / "generated_command.sh", command_paths, chr_name)
PY
EOF
  chmod +x "$output_path"
}

write_chr_placeholder_script() {
  local run_dir="$1"
  local chr_name="$2"

  cat > "${run_dir}/command.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(shell_quote "$run_dir")
generated_command="./generated_command.sh"
[[ -f "\${generated_command}" ]] || {
  echo "missing chr-local generated command for ${chr_name}; run assign_chr_groups.sh first" >&2
  exit 1
}
bash "\${generated_command}"
EOF
  chmod +x "${run_dir}/command.sh"
}

write_self_command_script() {
  local run_dir="$1"
  local ds_fa="$2"

  write_alignment_command_script "${run_dir}/command.sh" "$run_dir" "$ds_fa" "$ds_fa" true
}

write_ds_pair_command_script() {
  local run_dir="$1"
  local left_ds_fa="$2"
  local right_ds_fa="$3"

  write_alignment_command_script "${run_dir}/command.sh" "$run_dir" "$left_ds_fa" "$right_ds_fa" false
}

print_ref_command() {
  local index="$1"
  local total="$2"
  local run_label="$3"
  local run_dir="$4"
  local ref_fa="$5"
  local ds_fa="$6"

  printf '[%s/%s] %s\n' "$index" "$total" "$run_label"
  printf 'cd %s\n' "$run_dir"
  sed '1,3d' "${run_dir}/command.sh"
  printf '\n'
}

print_self_command() {
  local index="$1"
  local total="$2"
  local run_label="$3"
  local run_dir="$4"
  local ds_fa="$5"

  printf '[%s/%s] %s\n' "$index" "$total" "$run_label"
  printf 'cd %s\n' "$run_dir"
  sed '1,3d' "${run_dir}/command.sh"
  printf '\n'
}

print_ds_pair_command() {
  local index="$1"
  local total="$2"
  local run_label="$3"
  local run_dir="$4"
  local left_ds_fa="$5"
  local right_ds_fa="$6"

  printf '[%s/%s] %s\n' "$index" "$total" "$run_label"
  printf 'cd %s\n' "$run_dir"
  sed '1,3d' "${run_dir}/command.sh"
  printf '\n'
}

append_run_all_command() {
  local command_script="$1"
  local index="$2"
  local total="$3"

  if [[ "$index" -lt "$total" ]]; then
    printf 'bash %s && \\\n' "$(shell_quote "$command_script")" >> "$RUN_ALL"
  else
    printf 'bash %s\n' "$(shell_quote "$command_script")" >> "$RUN_ALL"
  fi
}

REF_NAME=""
REF_SRC=""
declare -a DATASET_NAMES=()
declare -a DATASET_SRCS=()
declare -a TEL_RULE_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 3 ]] || die "--ref requires <reference_name> <reference_fasta_path>"
      [[ -z "$REF_NAME" ]] || die "--ref may only be provided once"
      REF_NAME="$2"
      REF_SRC="$3"
      shift 3
      ;;
    --ds)
      [[ $# -ge 3 ]] || die "--ds requires <dataset_name> <dataset_fasta_path>"
      DATASET_NAMES+=("$2")
      DATASET_SRCS+=("$3")
      shift 3
      ;;
    -o|--out|--output)
      [[ $# -ge 2 ]] || die "$1 requires <gpm_server_output_dir>"
      [[ -n "$2" ]] || die "$1 requires a non-empty output path"
      WORK_ROOT="$(resolve_output_root "$2")"
      shift 2
      ;;
    --score|-s)
      [[ $# -ge 2 ]] || die "$1 requires <chr_assignment_min_coverage_percent>"
      validate_score "$2"
      CHR_ASSIGNMENT_MIN_COVERAGE_PERCENT="$2"
      shift 2
      ;;
    --aligner)
      [[ $# -ge 2 ]] || die "--aligner requires minimap2, blastn, or winnowmap"
      validate_aligner "$2"
      ALIGNER="$2"
      shift 2
      ;;
    --skip-self)
      SKIP_SELF=true
      shift
      ;;
    --minimap-preset)
      [[ $# -ge 2 ]] || die "--minimap-preset requires asm10 or asm5"
      validate_minimap_preset "$2"
      MINIMAP_PRESET="$2"
      MINIMAP_PRESET_SET=true
      shift 2
      ;;
    --blastn-task)
      [[ $# -ge 2 ]] || die "--blastn-task requires blastn, megablast, or dc-megablast"
      validate_blastn_task "$2"
      BLASTN_TASK="$2"
      BLASTN_TASK_SET=true
      shift 2
      ;;
    --blastn-evalue)
      [[ $# -ge 2 ]] || die "--blastn-evalue requires <evalue>"
      validate_float_option "--blastn-evalue" "$2"
      BLASTN_EVALUE="$2"
      BLASTN_EVALUE_SET=true
      shift 2
      ;;
    --winnowmap-preset)
      [[ $# -ge 2 ]] || die "--winnowmap-preset requires asm20, asm10, or asm5"
      validate_winnowmap_preset "$2"
      WINNOWMAP_PRESET="$2"
      WINNOWMAP_PRESET_SET=true
      shift 2
      ;;
    --winnowmap-kmer)
      [[ $# -ge 2 ]] || die "--winnowmap-kmer requires <kmer_size>"
      validate_winnowmap_kmer "$2"
      WINNOWMAP_KMER="$2"
      WINNOWMAP_KMER_SET=true
      shift 2
      ;;
    --winnowmap-repeat-fraction)
      [[ $# -ge 2 ]] || die "--winnowmap-repeat-fraction requires <fraction>"
      validate_winnowmap_repeat_fraction "$2"
      WINNOWMAP_REPEAT_FRACTION="$2"
      WINNOWMAP_REPEAT_FRACTION_SET=true
      shift 2
      ;;
    --threads|-t)
      [[ $# -ge 2 ]] || die "$1 requires <alignment_threads>"
      validate_threads "$2"
      THREADS="$2"
      shift 2
      ;;
    --tel)
      [[ $# -ge 3 ]] || die "--tel requires <motif> <min_repeat>"
      validate_tel_motif "$2"
      validate_tel_repeat "$3"
      TEL_RULE_ARGS+=("${2^^}" "$3")
      shift 3
      ;;
    --cen)
      [[ $# -ge 2 ]] || die "--cen requires <reference_centromere_fasta>"
      [[ -z "$CEN_SRC" ]] || die "--cen may only be provided once"
      CEN_SRC="$2"
      shift 2
      ;;
    --cen-min-len)
      [[ $# -ge 2 ]] || die "--cen-min-len requires <min_alignment_bp>"
      validate_cen_min_len "$2"
      CEN_MIN_LEN="$2"
      shift 2
      ;;
    --cen-min-identity)
      [[ $# -ge 2 ]] || die "--cen-min-identity requires <min_identity_percent>"
      validate_cen_min_identity "$2"
      CEN_MIN_IDENTITY="$2"
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

[[ -n "$REF_NAME" ]] || die "Missing --ref"
[[ "${#DATASET_NAMES[@]}" -gt 0 ]] || die "At least one --ds is required"
validate_engine_specific_options

require_cmd samtools
require_cmd zip
require_cmd gzip
require_cmd python3
case "$ALIGNER" in
  minimap2)
    require_cmd minimap2
    ;;
  blastn)
    require_cmd makeblastdb
    require_cmd blastn
    ;;
  winnowmap)
    require_cmd meryl
    require_cmd winnowmap
    ;;
esac

validate_name "$REF_NAME"
ensure_readable_file "$REF_SRC"
if [[ -n "$CEN_SRC" ]]; then
  ensure_readable_file "$CEN_SRC"
fi

declare -A SEEN_DATASET_NAMES=()
for i in "${!DATASET_NAMES[@]}"; do
  validate_name "${DATASET_NAMES[$i]}"
  ensure_readable_file "${DATASET_SRCS[$i]}"

  if [[ -n "${SEEN_DATASET_NAMES[${DATASET_NAMES[$i]}]:-}" ]]; then
    die "Duplicate dataset name: ${DATASET_NAMES[$i]}"
  fi
  SEEN_DATASET_NAMES["${DATASET_NAMES[$i]}"]=1
done

mkdir -p \
  "${WORK_ROOT}/metadata" \
  "${WORK_ROOT}/data/reference" \
  "${WORK_ROOT}/data/datasets" \
  "${WORK_ROOT}/runs"

if [[ "${#TEL_RULE_ARGS[@]}" -gt 0 ]]; then
  mkdir -p "${WORK_ROOT}/tel"
  write_tel_rules_metadata "${WORK_ROOT}/tel/rules.tsv" "${TEL_RULE_ARGS[@]}"
fi

REF_DST="${WORK_ROOT}/data/reference/${REF_NAME}.fa"
materialize_fasta_input "$REF_SRC" "$REF_DST"
ensure_fai "$REF_DST"

if [[ -n "$CEN_SRC" ]]; then
  mkdir -p "${WORK_ROOT}/cen" "${WORK_ROOT}/data/centromere"
  CEN_BASENAME="$(sanitize_fasta_basename "$CEN_SRC")"
  CEN_DST="${WORK_ROOT}/data/centromere/${CEN_BASENAME}"
  CEN_REL="data/centromere/${CEN_BASENAME}"
  materialize_fasta_input "$CEN_SRC" "$CEN_DST"
  write_cen_reference_metadata "${WORK_ROOT}/cen/reference.tsv" "$CEN_DST" "${REF_DST}.fai" "$CEN_REL"
fi

{
  printf 'reference_name\tspecies_name\tassembly_label\tfasta_relpath\tfai_relpath\n'
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$REF_NAME" \
    "unknown" \
    "$REF_NAME" \
    "data/reference/${REF_NAME}.fa" \
    "data/reference/${REF_NAME}.fa.fai"
} > "${WORK_ROOT}/metadata/reference.tsv"

write_reference_segments_metadata "$REF_DST" "${WORK_ROOT}/metadata/reference_segments.tsv"

package_mode="fast"
sequence_layout="partitioned"
preassigned_chr="true"
self_alignment_scope="chr_partition"
cross_alignment_scope="chr_partition"
if [[ "$SKIP_SELF" == "true" ]]; then
  self_alignment_scope="none"
fi
write_package_metadata \
  "${WORK_ROOT}/metadata/package.tsv" \
  "$package_mode" \
  "$sequence_layout" \
  "$preassigned_chr" \
  "$self_alignment_scope" \
  "$cross_alignment_scope"
write_prepare_options_metadata \
  "${WORK_ROOT}/metadata/prepare_options.tsv" \
  "$package_mode" \
  "$sequence_layout" \
  "$preassigned_chr" \
  "$self_alignment_scope" \
  "$cross_alignment_scope"

{
  printf 'dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n'
  for i in "${!DATASET_NAMES[@]}"; do
    ds_name="${DATASET_NAMES[$i]}"
    ds_src="${DATASET_SRCS[$i]}"
    ds_dst="${WORK_ROOT}/data/datasets/${ds_name}.fa"
    self_alignment_available="true"
    if [[ "$SKIP_SELF" == "true" ]]; then
      self_alignment_available="false"
    fi

    materialize_fasta_input "$ds_src" "$ds_dst"
    ensure_fai "$ds_dst"

    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$ds_name" \
      "$ds_name" \
      "" \
      "data/datasets/${ds_name}.fa" \
      "data/datasets/${ds_name}.fa.fai" \
      "$self_alignment_available"
  done
} > "${WORK_ROOT}/metadata/datasets.tsv"

RUN_ALL="${WORK_ROOT}/run_all.sh"
{
  printf '#!/usr/bin/env bash\n'
  printf 'set -euo pipefail\n'
  printf '\n'
} > "$RUN_ALL"

DATASET_COUNT=${#DATASET_NAMES[@]}
mapfile -t REFERENCE_CHR_NAMES < <(collect_reference_chr_names "$REF_DST")

TOTAL_COMMANDS=$(( DATASET_COUNT + 1 + ${#REFERENCE_CHR_NAMES[@]} ))
COMMAND_INDEX=1

for ((i = 0; i < DATASET_COUNT; i++)); do
  ds_name="${DATASET_NAMES[$i]}"
  ds_fa="${WORK_ROOT}/data/datasets/${ds_name}.fa"
  run_ref_dir="${WORK_ROOT}/runs/${ds_name}_vs_ref"
  mkdir -p "$run_ref_dir"
  write_ref_command_script "$run_ref_dir" "$REF_DST" "$ds_fa"
  append_run_all_command "${run_ref_dir}/command.sh" "$COMMAND_INDEX" "$TOTAL_COMMANDS"
  print_ref_command "$COMMAND_INDEX" "$TOTAL_COMMANDS" "${ds_name}_vs_ref" "$run_ref_dir" "$REF_DST" "$ds_fa"
  COMMAND_INDEX=$((COMMAND_INDEX + 1))
done

write_assignment_script "${WORK_ROOT}/assign_chr_groups.sh" "$WORK_ROOT" "${DATASET_NAMES[@]}"
append_run_all_command "${WORK_ROOT}/assign_chr_groups.sh" "$COMMAND_INDEX" "$TOTAL_COMMANDS"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "assign_chr_groups"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/assign_chr_groups.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

for chr_name in "${REFERENCE_CHR_NAMES[@]}"; do
  run_chr_dir="${WORK_ROOT}/runs/chr_${chr_name}"
  mkdir -p "$run_chr_dir"
  write_chr_placeholder_script "$run_chr_dir" "$chr_name"
  append_run_all_command "${run_chr_dir}/command.sh" "$COMMAND_INDEX" "$TOTAL_COMMANDS"
  printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "chr_${chr_name}"
  printf 'cd %s\n' "$run_chr_dir"
  printf 'bash %s\n\n' "${run_chr_dir}/command.sh"
  COMMAND_INDEX=$((COMMAND_INDEX + 1))
done

chmod +x "$RUN_ALL"
write_package_scripts "$WORK_ROOT" "$package_mode" "$sequence_layout"
write_prepare_lib "$WORK_ROOT"
write_export_final_path_fasta_script "$WORK_ROOT"
write_add_dataset_script "$WORK_ROOT"
write_add_ctg_script "$WORK_ROOT"

echo "Prepared GPM Next server workspace at: ${WORK_ROOT}"
echo "Generated:"
echo "  - ${WORK_ROOT}/metadata/package.tsv"
echo "  - ${WORK_ROOT}/metadata/prepare_options.tsv"
echo "  - ${WORK_ROOT}/metadata/reference.tsv"
echo "  - ${WORK_ROOT}/metadata/reference_segments.tsv"
echo "  - ${WORK_ROOT}/metadata/datasets.tsv"
echo "  - ${WORK_ROOT}/run_all.sh"
if [[ "${#TEL_RULE_ARGS[@]}" -gt 0 ]]; then
  echo "  - ${WORK_ROOT}/tel/rules.tsv"
fi
echo "  - ${WORK_ROOT}/add_dataset.sh"
echo "  - ${WORK_ROOT}/add_ctg.sh"
echo "  - ${WORK_ROOT}/export_final_path_fasta.sh"
echo "  - ${WORK_ROOT}/.prepare_lib/lib"
echo "  - ${WORK_ROOT}/.prepare_lib/tools"
echo "  - ${WORK_ROOT}/package_full_zip.sh"
echo "  - ${WORK_ROOT}/package_light_no_fasta_zip.sh"
echo
echo "Next:"
echo "  1. Run: bash ${WORK_ROOT}/run_all.sh"
echo "  2. Or copy the alignment commands printed above and execute them one by one"
echo "  3. Execution order is strict: finish all *_vs_ref jobs first, then assignment, then chr-local jobs"
if [[ "$SKIP_SELF" == "true" ]]; then
  echo "     - chr-local same-dataset self alignments remain skipped"
fi
echo "  4. After all result.paf files are ready, package the delivery bundle:"
echo "     - Full package: bash ${WORK_ROOT}/package_full_zip.sh"
echo "     - Light package without .fa/.fasta: bash ${WORK_ROOT}/package_light_no_fasta_zip.sh"
echo "  5. To add a dataset later, run:"
echo "     - bash ${WORK_ROOT}/add_dataset.sh --ds <dataset_name> /path/to/dataset.fa"
echo "  6. To add a derived ctg later, run:"
echo "     - bash ${WORK_ROOT}/add_ctg.sh --ctg <ctg_name> --chr <chr_name> --track <dataset_name> -i /path/to/final.fa"
echo "  7. To export final path FASTA on the server, run:"
echo "     - bash ${WORK_ROOT}/export_final_path_fasta.sh --tsv /path/to/final_path.tsv -o /path/to/final_path.fa"
echo
echo "Delivery reminder:"
echo "  - gpm_next importer does not require metadata/alignments.tsv"
echo "  - The zip should contain top-level gpm_server/{metadata,data,runs}"
