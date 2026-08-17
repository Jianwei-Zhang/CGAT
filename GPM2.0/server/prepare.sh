#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_LIB="${SCRIPT_DIR}/lib/incremental_common.sh"
[[ -f "$COMMON_LIB" ]] || {
  echo "ERROR: Missing server library: $COMMON_LIB" >&2
  exit 1
}
# shellcheck source=lib/incremental_common.sh
source "$COMMON_LIB"

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
GRT_MERYL="meryl"
GRT_MERQURY="merqury.sh"
GRT_CRAQ="craq"
GRT_MINIMAP2="minimap2"
GRT_NUCMER="nucmer"
GRT_DELTA_FILTER="delta-filter"
GRT_SHOW_COORDS="show-coords"
GRT_QC_MEMORY_GB="80"
GRT_KMER_SIZE="21"
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
    [--reads <reads_fastq_path> ...] \
    [--grt-qc-memory-gb <memory_gb>] \
    [--grt-kmer-size <kmer_size>] \
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
  - The first --ds is the locked GRT primary dataset; later initial --ds inputs are support datasets
  - Discovers minimap2, nucmer, delta-filter, and show-coords from PATH and records their resolved paths
  - Repeatable --reads enables one shared Meryl database plus Merqury/CRAQ for every initial dataset
  - With --reads, also discovers meryl, merqury.sh, and craq from PATH
  - With no --reads, only reads-based QC is skipped; q0 and frozen D0/Dtel are still prepared
  - Generates staged chromosome-partitioned run commands
  - Supports --skip-self to omit dataset vs self alignments
  - Accepts plain FASTA inputs such as .fa/.fasta/.fna
  - Accepts gzip-compressed FASTA inputs such as .fa.gz/.fasta.gz/.fna.gz
  - Normalizes all inputs into package-local .fa files under data/
  - Creates .fai with samtools faidx when missing
  - Generates metadata/reference.tsv and metadata/datasets.tsv
  - Generates metadata/package.tsv
  - Generates authoritative metadata/track_member_orders.tsv during chr assignment
  - Generates runs/*/command.sh, <work_root>/.run_all/plan.tsv, and <work_root>/run_all.sh
  - run_all.sh executes the generated plan serially and stops on the first failed command
  - run_all.sh writes live progress to <work_root>/logs/run_all.log and current state to logs/status.tsv
  - run_all.sh holds an exclusive workspace lock while active
  - Generates package_full_zip.sh, package_light_no_fasta_zip.sh, and export_final_path_fasta.sh
  - run_all.sh is staged as: vs_ref -> chr assignment helper -> GRT q0/D0/Dtel -> GRT Step1 -> GRT Step2/3 -> GRT telomere/q4 finalization -> per-chr commands -> GRT evidence/package validation -> full zip -> light zip
  - A successful run_all.sh creates both delivery archives in the parent directory of the work root
  - With --skip-self, same-dataset self alignments are omitted and marked unavailable in metadata/datasets.tsv
  - Prints all generated staged commands to the terminal for manual copy/paste
EOF
}

make_executable_if_supported() {
  local path="$1"
  [[ -f "$path" ]] || die "Generated script is missing: $path"
  chmod +x "$path" 2>/dev/null || true
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

validate_positive_integer() {
  local option_name="$1"
  local value="$2"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "Invalid ${option_name} '$value'. Use a positive integer."
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
        printf '(minimap2 --version > tool_version.txt 2>&1 || printf %s > tool_version.txt)\n' "$(shell_quote $'unknown\n')"
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
        printf '(blastn -version > tool_version.txt 2>&1 || printf %s > tool_version.txt)\n' "$(shell_quote $'unknown\n')"
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
        printf '(winnowmap --version > tool_version.txt 2>&1 || printf %s > tool_version.txt)\n' "$(shell_quote $'unknown\n')"
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
  make_executable_if_supported "$output_path"
}

resolve_required_command() {
  local command_name="$1"
  local resolved
  resolved="$(command -v "$command_name")" \
    || die "Required command not found in PATH: $command_name"
  if [[ "$resolved" != /* ]]; then
    resolved="$(cd "$(dirname "$resolved")" && pwd)/$(basename "$resolved")"
  fi
  printf '%s\n' "$resolved"
}

require_mummer_help_option() {
  local executable="$1"
  local help_flag="$2"
  local option_pattern="$3"
  local option_label="$4"
  local install_guidance="$5"
  local help_output
  local help_line
  local found="false"

  help_output="$("$executable" "$help_flag" 2>&1 || true)"
  while IFS= read -r help_line; do
    if [[ "$help_line" =~ $option_pattern ]]; then
      found="true"
      break
    fi
  done <<<"$help_output"
  if [[ "$found" != "true" ]]; then
    die "Incompatible MUMmer tool '$executable': missing required option $option_label. $install_guidance"
  fi
}

validate_mummer4_capabilities() {
  local nucmer_path="$1"
  local delta_filter_path="$2"
  local show_coords_path="$3"
  local nucmer_guidance="Install a current MUMmer4 build with nucmer --batch and -t/--threads support."
  local utility_guidance="Install a complete MUMmer4 build whose delta-filter and show-coords utilities support the GRT recipe."

  require_mummer_help_option \
    "$nucmer_path" --help '^[[:space:]]*--batch([=[:space:]]|$)' --batch \
    "$nucmer_guidance"
  require_mummer_help_option \
    "$nucmer_path" --help '^[[:space:]]*-t([|,[:space:]]|$)' -t/--threads \
    "$nucmer_guidance"
  require_mummer_help_option \
    "$delta_filter_path" -h '^[[:space:]]*-r([|,[:space:]]|$)' -r \
    "$utility_guidance"
  require_mummer_help_option \
    "$delta_filter_path" -h '^[[:space:]]*-l([|,[:space:]]|$)' -l \
    "$utility_guidance"
  require_mummer_help_option \
    "$show_coords_path" -h '^[[:space:]]*-r([|,[:space:]]|$)' -r \
    "$utility_guidance"
  require_mummer_help_option \
    "$show_coords_path" -h '^[[:space:]]*-l([|,[:space:]]|$)' -l \
    "$utility_guidance"
}

copy_script_template() {
  local template_name="$1"
  local output_path="$2"
  local template_path="${SCRIPT_DIR}/templates/${template_name}"

  [[ -f "$template_path" ]] || die "Missing template: $template_path"
  cp -f "$template_path" "$output_path"
  make_executable_if_supported "$output_path"
}

write_package_scripts() {
  local work_root="$1"

  copy_script_template "package_full_zip.sh" "${work_root}/package_full_zip.sh"
  copy_script_template "package_light_no_fasta_zip.sh" "${work_root}/package_light_no_fasta_zip.sh"
}

write_export_final_path_fasta_script() {
  local work_root="$1"
  copy_script_template "export_final_path_fasta.sh" "${work_root}/export_final_path_fasta.sh"
}

write_prepare_lib() {
  local work_root="$1"
  local lib_src="${SCRIPT_DIR}/lib"
  local lib_dst="${work_root}/.prepare_lib/lib"
  local tools_src="${SCRIPT_DIR}/tools"
  local tools_dst="${work_root}/.prepare_lib/tools"
  local contracts_src="${SCRIPT_DIR}/contracts"
  local contracts_dst="${work_root}/.prepare_lib/contracts"

  [[ -d "$lib_src" ]] || die "Missing server library directory: $lib_src"
  [[ -d "$tools_src" ]] || die "Missing server tools directory: $tools_src"
  [[ -d "$tools_src/grt_core" ]] || die "Missing GRT core package: $tools_src/grt_core"
  [[ -f "$tools_src/grt_app_package.py" ]] || die "Missing App delivery package builder: $tools_src/grt_app_package.py"
  [[ -d "$contracts_src" ]] || die "Missing server contracts directory: $contracts_src"
  rm -rf "$lib_dst"
  rm -rf "$tools_dst"
  rm -rf "$contracts_dst"
  mkdir -p "$(dirname "$lib_dst")"
  mkdir -p "$tools_dst"
  mkdir -p "$contracts_dst"
  cp -R "$lib_src" "$lib_dst"
  cp -f "$tools_src"/*.py "$tools_dst"/
  cp -R "$tools_src/grt_core" "$tools_dst/grt_core"
  find "$tools_dst/grt_core" -type d -name '__pycache__' -prune -exec rm -rf {} +
  cp -f "$contracts_src"/*.json "$contracts_dst"/
}

write_add_dataset_script() {
  local work_root="$1"
  copy_script_template "add_dataset.sh" "${work_root}/add_dataset.sh"
}

write_add_ctg_script() {
  local work_root="$1"
  copy_script_template "add_ctg.sh" "${work_root}/add_ctg.sh"
}

write_reference_segments_metadata() {
  local ref_fa="$1"
  local output_path="$2"
  local scanner="${SCRIPT_DIR}/tools/reference_segments.py"

  [[ -f "$scanner" ]] || die "Missing reference segment scanner: $scanner"
  python3 "$scanner" "$ref_fa" "$output_path"
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
  local reads_qc_enabled="false"
  if [[ "${#READS_SRCS[@]}" -gt 0 ]]; then
    reads_qc_enabled="true"
  fi

  {
    printf 'workflow\tschema_version\tpackage_mode\tsequence_layout\tpreassigned_chr\tself_alignment_scope\tcross_alignment_scope\tchr_assignment_min_coverage_percent\tgrt_precompute_enabled\trecipe_locked\tfinal_path_schema_version\treads_qc_enabled\n'
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "gpm_grt_precomputed_v2" \
      "2" \
      "$package_mode" \
      "$sequence_layout" \
      "$preassigned_chr" \
      "$self_alignment_scope" \
      "$cross_alignment_scope" \
      "$CHR_ASSIGNMENT_MIN_COVERAGE_PERCENT" \
      "true" \
      "true" \
      "1" \
      "$reads_qc_enabled"
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
  local reads_qc_enabled="false"

  if [[ "${#TEL_RULE_ARGS[@]}" -gt 0 ]]; then
    tel_enabled="true"
  fi
  if [[ -n "$CEN_SRC" ]]; then
    cen_enabled="true"
  fi
  if [[ "${#READS_SRCS[@]}" -gt 0 ]]; then
    reads_qc_enabled="true"
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
    printf 'grt_workflow\t%s\n' "gpm_grt_precomputed_v2"
    printf 'grt_primary_dataset\t%s\n' "${DATASET_NAMES[0]}"
    printf 'grt_reads_qc_enabled\t%s\n' "$reads_qc_enabled"
    printf 'grt_meryl\t%s\n' "$GRT_MERYL"
    printf 'grt_merqury\t%s\n' "$GRT_MERQURY"
    printf 'grt_craq\t%s\n' "$GRT_CRAQ"
    printf 'grt_qc_memory_gb\t%s\n' "$GRT_QC_MEMORY_GB"
    printf 'grt_kmer_size\t%s\n' "$GRT_KMER_SIZE"
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

  python3 "${SCRIPT_DIR}/tools/cen_reference_metadata.py" \
    "$output_path" "$cen_fasta" "$ref_fai" "$fasta_relpath" \
    "$CEN_MIN_LEN" "$CEN_MIN_IDENTITY"
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
  local template_path="${SCRIPT_DIR}/templates/assign_chr_groups.sh"
  local renderer="${SCRIPT_DIR}/tools/render_template.py"

  [[ -f "$template_path" ]] || die "Missing template: $template_path"
  [[ -f "$renderer" ]] || die "Missing template renderer: $renderer"
  python3 "$renderer" \
    --template "$template_path" \
    --output "$output_path" \
    --allow GPM_FAST_WORK_ROOT \
    --allow GPM_FAST_THREADS \
    --allow GPM_FAST_ALIGNMENT_ENGINE \
    --allow GPM_FAST_MINIMAP_PRESET \
    --allow GPM_FAST_BLASTN_TASK \
    --allow GPM_FAST_BLASTN_EVALUE \
    --allow GPM_FAST_BLASTN_DUST \
    --allow GPM_FAST_WINNOWMAP_PRESET \
    --allow GPM_FAST_WINNOWMAP_KMER \
    --allow GPM_FAST_WINNOWMAP_REPEAT_FRACTION \
    --allow GPM_FAST_BLAST6_TO_PAF \
    --shell-var GPM_FAST_WORK_ROOT "$work_root" \
    --shell-var GPM_FAST_THREADS "$THREADS" \
    --shell-var GPM_FAST_ALIGNMENT_ENGINE "$ALIGNER" \
    --shell-var GPM_FAST_MINIMAP_PRESET "$MINIMAP_PRESET" \
    --shell-var GPM_FAST_BLASTN_TASK "$BLASTN_TASK" \
    --shell-var GPM_FAST_BLASTN_EVALUE "$BLASTN_EVALUE" \
    --shell-var GPM_FAST_BLASTN_DUST "$BLASTN_DUST" \
    --shell-var GPM_FAST_WINNOWMAP_PRESET "$WINNOWMAP_PRESET" \
    --shell-var GPM_FAST_WINNOWMAP_KMER "$WINNOWMAP_KMER" \
    --shell-var GPM_FAST_WINNOWMAP_REPEAT_FRACTION "$WINNOWMAP_REPEAT_FRACTION" \
    --shell-var GPM_FAST_BLAST6_TO_PAF "${work_root}/.prepare_lib/tools/blast6_to_paf.py"
  make_executable_if_supported "$output_path"
}

write_grt_prepare_script() {
  local output_path="$1"
  local work_root="$2"
  shift 2

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'python3 %s --server-dir %s --threads %s --memory-gb %s --kmer-size %s --meryl %s --merqury %s --craq %s' \
      "$(shell_quote "${work_root}/.prepare_lib/tools/grt_prepare_inputs.py")" \
      "$(shell_quote "$work_root")" \
      "$(shell_quote "$THREADS")" \
      "$(shell_quote "$GRT_QC_MEMORY_GB")" \
      "$(shell_quote "$GRT_KMER_SIZE")" \
      "$(shell_quote "$GRT_MERYL")" \
      "$(shell_quote "$GRT_MERQURY")" \
      "$(shell_quote "$GRT_CRAQ")"
    while [[ $# -gt 0 ]]; do
      printf ' --reads %s' "$(shell_quote "$1")"
      shift
    done
    printf '\n'
  } > "$output_path"
  make_executable_if_supported "$output_path"
}

write_grt_step1_script() {
  local output_path="$1"
  local work_root="$2"

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'python3 %s --server-dir %s --threads %s --minimap2 %s\n' \
      "$(shell_quote "${work_root}/.prepare_lib/tools/grt_step1.py")" \
      "$(shell_quote "$work_root")" \
      "$(shell_quote "$THREADS")" \
      "$(shell_quote "$GRT_MINIMAP2")"
  } > "$output_path"
  make_executable_if_supported "$output_path"
}

write_grt_step23_script() {
  local output_path="$1"
  local work_root="$2"

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'python3 %s --server-dir %s --threads %s --minimap2 %s --nucmer %s --delta-filter %s --show-coords %s\n' \
      "$(shell_quote "${work_root}/.prepare_lib/tools/grt_step23.py")" \
      "$(shell_quote "$work_root")" \
      "$(shell_quote "$THREADS")" \
      "$(shell_quote "$GRT_MINIMAP2")" \
      "$(shell_quote "$GRT_NUCMER")" \
      "$(shell_quote "$GRT_DELTA_FILTER")" \
      "$(shell_quote "$GRT_SHOW_COORDS")"
  } > "$output_path"
  make_executable_if_supported "$output_path"
}

write_grt_telomere_finalize_script() {
  local output_path="$1"
  local work_root="$2"

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'python3 %s --server-dir %s --threads %s --minimap2 %s --nucmer %s --delta-filter %s --show-coords %s\n' \
      "$(shell_quote "${work_root}/.prepare_lib/tools/grt_telomere_finalize.py")" \
      "$(shell_quote "$work_root")" \
      "$(shell_quote "$THREADS")" \
      "$(shell_quote "$GRT_MINIMAP2")" \
      "$(shell_quote "$GRT_NUCMER")" \
      "$(shell_quote "$GRT_DELTA_FILTER")" \
      "$(shell_quote "$GRT_SHOW_COORDS")"
  } > "$output_path"
  make_executable_if_supported "$output_path"
}

write_grt_evidence_package_script() {
  local output_path="$1"
  local work_root="$2"

  {
    printf '#!/usr/bin/env bash\n'
    printf 'set -euo pipefail\n'
    printf 'python3 %s --server-dir %s --threads %s --minimap2 %s\n' \
      "$(shell_quote "${work_root}/.prepare_lib/tools/grt_evidence_package.py")" \
      "$(shell_quote "$work_root")" \
      "$(shell_quote "$THREADS")" \
      "$(shell_quote "$GRT_MINIMAP2")"
  } > "$output_path"
  make_executable_if_supported "$output_path"
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
  make_executable_if_supported "${run_dir}/command.sh"
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

append_run_all_unit() {
  local unit_id="$1"
  local command_relpath="$2"
  local detail_log_relpath="$3"

  printf '%s\t%s\t%s\n' \
    "$unit_id" \
    "$command_relpath" \
    "$detail_log_relpath" >> "$RUN_ALL_PLAN"
}

REF_NAME=""
REF_SRC=""
declare -a DATASET_NAMES=()
declare -a DATASET_SRCS=()
declare -a TEL_RULE_ARGS=()
declare -a READS_SRCS=()

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
      WORK_ROOT="$(resolve_path "$2")"
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
    --reads)
      [[ $# -ge 2 ]] || die "--reads requires <reads_fastq_path>"
      READS_SRCS+=("$2")
      shift 2
      ;;
    --grt-qc-memory-gb)
      [[ $# -ge 2 ]] || die "--grt-qc-memory-gb requires <memory_gb>"
      validate_positive_integer "--grt-qc-memory-gb" "$2"
      GRT_QC_MEMORY_GB="$2"
      shift 2
      ;;
    --grt-kmer-size)
      [[ $# -ge 2 ]] || die "--grt-kmer-size requires <kmer_size>"
      validate_positive_integer "--grt-kmer-size" "$2"
      GRT_KMER_SIZE="$2"
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
GRT_MINIMAP2="$(resolve_required_command minimap2)"
GRT_NUCMER="$(resolve_required_command nucmer)"
GRT_DELTA_FILTER="$(resolve_required_command delta-filter)"
GRT_SHOW_COORDS="$(resolve_required_command show-coords)"
validate_mummer4_capabilities \
  "$GRT_NUCMER" "$GRT_DELTA_FILTER" "$GRT_SHOW_COORDS"
if [[ "${#READS_SRCS[@]}" -gt 0 ]]; then
  GRT_MERYL="$(resolve_required_command meryl)"
  GRT_MERQURY="$(resolve_required_command merqury.sh)"
  GRT_CRAQ="$(resolve_required_command craq)"
fi
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

for i in "${!READS_SRCS[@]}"; do
  ensure_readable_file "${READS_SRCS[$i]}"
  if [[ "${READS_SRCS[$i]}" != /* ]]; then
    READS_SRCS[$i]="$(cd "$(dirname "${READS_SRCS[$i]}")" && pwd)/$(basename "${READS_SRCS[$i]}")"
  fi
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
RUN_ALL_STATE_DIR="${WORK_ROOT}/.run_all"
RUN_ALL_PLAN="${RUN_ALL_STATE_DIR}/plan.tsv"
rm -rf "$RUN_ALL_STATE_DIR" "${WORK_ROOT}/logs"
mkdir -p "$RUN_ALL_STATE_DIR"
{
  printf '#!/usr/bin/env bash\n'
  printf 'set -euo pipefail\n'
  printf '\n'
  printf 'server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
  printf 'exec python3 "${server_dir}/.prepare_lib/tools/run_all_runner.py" --server-dir "$server_dir" "$@"\n'
} > "$RUN_ALL"
printf 'unit_id\tcommand_relpath\tdetail_log_relpath\n' > "$RUN_ALL_PLAN"

DATASET_COUNT=${#DATASET_NAMES[@]}
mapfile -t REFERENCE_CHR_NAMES < <(collect_reference_chr_names "$REF_DST")

TOTAL_COMMANDS=$(( DATASET_COUNT + 8 + ${#REFERENCE_CHR_NAMES[@]} ))
COMMAND_INDEX=1

for ((i = 0; i < DATASET_COUNT; i++)); do
  ds_name="${DATASET_NAMES[$i]}"
  ds_fa="${WORK_ROOT}/data/datasets/${ds_name}.fa"
  run_ref_dir="${WORK_ROOT}/runs/${ds_name}_vs_ref"
  mkdir -p "$run_ref_dir"
  write_ref_command_script "$run_ref_dir" "$REF_DST" "$ds_fa"
  append_run_all_unit \
    "ref:${ds_name}" \
    "runs/${ds_name}_vs_ref/command.sh" \
    "runs/${ds_name}_vs_ref/stderr.log"
  print_ref_command "$COMMAND_INDEX" "$TOTAL_COMMANDS" "${ds_name}_vs_ref" "$run_ref_dir" "$REF_DST" "$ds_fa"
  COMMAND_INDEX=$((COMMAND_INDEX + 1))
done

write_assignment_script "${WORK_ROOT}/assign_chr_groups.sh" "$WORK_ROOT" "${DATASET_NAMES[@]}"
append_run_all_unit "assign" "assign_chr_groups.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "assign_chr_groups"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/assign_chr_groups.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

write_grt_prepare_script "${WORK_ROOT}/prepare_grt_inputs.sh" "$WORK_ROOT" "${READS_SRCS[@]}"
append_run_all_unit "grt_prepare" "prepare_grt_inputs.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "prepare_grt_inputs"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/prepare_grt_inputs.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

write_grt_step1_script "${WORK_ROOT}/run_grt_step1.sh" "$WORK_ROOT"
append_run_all_unit "grt_step1" "run_grt_step1.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "run_grt_step1"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/run_grt_step1.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

write_grt_step23_script "${WORK_ROOT}/run_grt_step23.sh" "$WORK_ROOT"
append_run_all_unit "grt_step23" "run_grt_step23.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "run_grt_step23"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/run_grt_step23.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

write_grt_telomere_finalize_script "${WORK_ROOT}/run_grt_telomere_finalize.sh" "$WORK_ROOT"
append_run_all_unit \
  "grt_telomere_finalize" \
  "run_grt_telomere_finalize.sh" \
  "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "run_grt_telomere_finalize"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/run_grt_telomere_finalize.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

for chr_name in "${REFERENCE_CHR_NAMES[@]}"; do
  run_chr_dir="${WORK_ROOT}/runs/chr_${chr_name}"
  mkdir -p "$run_chr_dir"
  write_chr_placeholder_script "$run_chr_dir" "$chr_name"
  append_run_all_unit \
    "chr:${chr_name}" \
    "runs/chr_${chr_name}/command.sh" \
    "logs/run_all.log"
  printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "chr_${chr_name}"
  printf 'cd %s\n' "$run_chr_dir"
  printf 'bash %s\n\n' "${run_chr_dir}/command.sh"
  COMMAND_INDEX=$((COMMAND_INDEX + 1))
done

write_grt_evidence_package_script "${WORK_ROOT}/finalize_grt_evidence.sh" "$WORK_ROOT"
append_run_all_unit "finalize_evidence" "finalize_grt_evidence.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "finalize_grt_evidence"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/finalize_grt_evidence.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

append_run_all_unit "package_full" "package_full_zip.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "package_full_zip"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/package_full_zip.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

append_run_all_unit "package_light" "package_light_no_fasta_zip.sh" "logs/run_all.log"
printf '[%s/%s] %s\n' "$COMMAND_INDEX" "$TOTAL_COMMANDS" "package_light_no_fasta_zip"
printf 'cd %s\n' "$WORK_ROOT"
printf 'bash %s\n\n' "${WORK_ROOT}/package_light_no_fasta_zip.sh"
COMMAND_INDEX=$((COMMAND_INDEX + 1))

make_executable_if_supported "$RUN_ALL"
write_package_scripts "$WORK_ROOT"
write_prepare_lib "$WORK_ROOT"
write_export_final_path_fasta_script "$WORK_ROOT"
write_add_dataset_script "$WORK_ROOT"
write_add_ctg_script "$WORK_ROOT"

echo "Prepared GPM2.0 server workspace at: ${WORK_ROOT}"
echo "Generated:"
echo "  - ${WORK_ROOT}/metadata/package.tsv"
echo "  - ${WORK_ROOT}/metadata/prepare_options.tsv"
echo "  - ${WORK_ROOT}/metadata/reference.tsv"
echo "  - ${WORK_ROOT}/metadata/reference_segments.tsv"
echo "  - ${WORK_ROOT}/metadata/datasets.tsv"
echo "  - ${WORK_ROOT}/run_all.sh"
echo "  - ${WORK_ROOT}/.run_all/plan.tsv"
if [[ "${#TEL_RULE_ARGS[@]}" -gt 0 ]]; then
  echo "  - ${WORK_ROOT}/tel/rules.tsv"
fi
echo "  - ${WORK_ROOT}/add_dataset.sh"
echo "  - ${WORK_ROOT}/add_ctg.sh"
echo "  - ${WORK_ROOT}/prepare_grt_inputs.sh"
echo "  - ${WORK_ROOT}/run_grt_step1.sh"
echo "  - ${WORK_ROOT}/run_grt_step23.sh"
echo "  - ${WORK_ROOT}/run_grt_telomere_finalize.sh"
echo "  - ${WORK_ROOT}/finalize_grt_evidence.sh"
echo "  - ${WORK_ROOT}/export_final_path_fasta.sh"
echo "  - ${WORK_ROOT}/.prepare_lib/lib"
echo "  - ${WORK_ROOT}/.prepare_lib/tools"
echo "  - ${WORK_ROOT}/package_full_zip.sh"
echo "  - ${WORK_ROOT}/package_light_no_fasta_zip.sh"
echo
echo "Next:"
echo "  1. Run: bash ${WORK_ROOT}/run_all.sh"
echo "     - This automatically creates both the full and light delivery archives"
echo "  2. Or execute the staged commands printed above one by one, including the final two package commands"
echo "  3. Execution order is strict: finish all *_vs_ref jobs first, then assignment, GRT q0/D0/Dtel, GRT Step1, GRT Step2/3, GRT telomere/q4 finalization, chr-local jobs, evidence finalization, full packaging, and light packaging"
if [[ "$SKIP_SELF" == "true" ]]; then
  echo "     - chr-local same-dataset self alignments remain skipped"
fi
echo "  4. Output archives:"
echo "     - Full package: $(dirname "$WORK_ROOT")/$(basename "$WORK_ROOT").zip"
echo "     - Light package: $(dirname "$WORK_ROOT")/$(basename "$WORK_ROOT").no_fasta.zip"
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
