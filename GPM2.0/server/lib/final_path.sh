#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash server/export_final_path_fasta.sh \
    --tsv <final_path_export.tsv> \
    --gpm_server <prepared_gpm_server_dir> \
    -o <output.fa> \
    [--ds <dataset_name> ...]

  bash gpm_server/export_final_path_fasta.sh \
    --tsv <final_path_export.tsv> \
    -o <output.fa> \
    [--ds <dataset_name> ...]

Behavior:
  - Reads the final path TSV exported by GPM Next.
  - Reads metadata/datasets.tsv and metadata/reference.tsv under --gpm_server.
  - If locator manifests exist, resolves source/reference FASTA paths from
    metadata/source_seq_locator.tsv and metadata/reference_chr_locator.tsv.
  - Otherwise falls back to the monolithic dataset/reference FASTA paths.
  - Uses the TSV Origin ID column as the FASTA sequence id.
  - Infers dataset names from the TSV Ctg column prefix when multiple datasets exist.
  - Writes one FASTA record, with Gap rows emitted as N bases.
  - When this script is inside a prepared gpm_server directory, --gpm_server
    is optional and defaults to that directory.

Notes:
  - Run this script on the server where the original FASTA files are still present.
  - Requires samtools.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

normalize_gpm_server_dir() {
  local input="$1"
  if [[ -f "${input}/metadata/datasets.tsv" ]]; then
    printf '%s\n' "$input"
    return
  fi
  if [[ -f "${input}/gpm_server/metadata/datasets.tsv" ]]; then
    printf '%s\n' "${input}/gpm_server"
    return
  fi
  die "--gpm_server must point to a prepared gpm_server directory"
}

resolve_path_under_server() {
  local server_dir="$1"
  local path_value="$2"
  if [[ "$path_value" = /* ]]; then
    printf '%s\n' "$path_value"
  else
    printf '%s\n' "${server_dir}/${path_value}"
  fi
}

validate_positive_int() {
  local label="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "${label} must be a positive integer: ${value}"
  [[ "$value" -gt 0 ]] || die "${label} must be > 0"
}

column_index() {
  local expected="$1"
  shift
  local index=0
  for column in "$@"; do
    if [[ "$column" == "$expected" ]]; then
      printf '%s\n' "$index"
      return
    fi
    index=$((index + 1))
  done
  die "metadata/datasets.tsv missing required column: ${expected}"
}

TSV_PATH=""
GPM_SERVER_INPUT=""
OUTPUT_PATH=""
DEFAULT_GPM_SERVER_INPUT=""
declare -a REQUESTED_DS=()

if [[ -n "${GPM_FINAL_PATH_DEFAULT_SERVER_DIR:-}" ]]; then
  DEFAULT_GPM_SERVER_INPUT="$GPM_FINAL_PATH_DEFAULT_SERVER_DIR"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tsv)
      [[ $# -ge 2 ]] || die "--tsv requires a path"
      TSV_PATH="$2"
      shift 2
      ;;
    --gpm_server)
      [[ $# -ge 2 ]] || die "--gpm_server requires a path"
      GPM_SERVER_INPUT="$2"
      shift 2
      ;;
    -o|--output)
      [[ $# -ge 2 ]] || die "-o requires a path"
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --ds)
      [[ $# -ge 2 ]] || die "--ds requires a dataset name"
      REQUESTED_DS+=("$2")
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

[[ -n "$TSV_PATH" ]] || die "Missing --tsv"
if [[ -z "$GPM_SERVER_INPUT" ]]; then
  GPM_SERVER_INPUT="$DEFAULT_GPM_SERVER_INPUT"
fi
[[ -n "$GPM_SERVER_INPUT" ]] || die "Missing --gpm_server"
[[ -n "$OUTPUT_PATH" ]] || die "Missing -o"
[[ -f "$TSV_PATH" ]] || die "TSV file not found: $TSV_PATH"
[[ -r "$TSV_PATH" ]] || die "TSV file is not readable: $TSV_PATH"

require_cmd samtools

GPM_SERVER_DIR="$(normalize_gpm_server_dir "$GPM_SERVER_INPUT")"
DATASETS_TSV="${GPM_SERVER_DIR}/metadata/datasets.tsv"
REFERENCE_TSV="${GPM_SERVER_DIR}/metadata/reference.tsv"
SOURCE_SEQ_LOCATOR_TSV="${GPM_SERVER_DIR}/metadata/source_seq_locator.tsv"
REFERENCE_CHR_LOCATOR_TSV="${GPM_SERVER_DIR}/metadata/reference_chr_locator.tsv"

declare -A DATASET_FASTA=()
declare -A SOURCE_SEQ_FASTA=()
declare -A REFERENCE_CHR_FASTA=()
declare -A REQUESTED_SET=()
declare -a DATASET_NAMES=()
HAS_SOURCE_SEQ_LOCATORS=false
HAS_REFERENCE_CHR_LOCATORS=false

make_source_seq_key() {
  printf '%s\t%s\n' "$1" "$2"
}

for ds_name in "${REQUESTED_DS[@]}"; do
  REQUESTED_SET["$ds_name"]=1
done

IFS=$'\t' read -r -a dataset_header < "$DATASETS_TSV" || die "metadata/datasets.tsv is empty"
dataset_name_col="$(column_index "dataset_name" "${dataset_header[@]}")"
fasta_relpath_col="$(column_index "fasta_relpath" "${dataset_header[@]}")"

if [[ -f "$SOURCE_SEQ_LOCATOR_TSV" ]]; then
  HAS_SOURCE_SEQ_LOCATORS=true
  IFS=$'\t' read -r -a source_locator_header < "$SOURCE_SEQ_LOCATOR_TSV" || die "metadata/source_seq_locator.tsv is empty"
  source_locator_dataset_name_col="$(column_index "dataset_name" "${source_locator_header[@]}")"
  source_locator_seq_name_col="$(column_index "seq_name" "${source_locator_header[@]}")"
  source_locator_fasta_relpath_col="$(column_index "fasta_relpath" "${source_locator_header[@]}")"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    ds_name="$(printf '%s\n' "$line" | cut -f$((source_locator_dataset_name_col + 1)))"
    seq_name="$(printf '%s\n' "$line" | cut -f$((source_locator_seq_name_col + 1)))"
    fasta_relpath="$(printf '%s\n' "$line" | cut -f$((source_locator_fasta_relpath_col + 1)))"
    [[ -n "$ds_name" && -n "$seq_name" ]] || continue
    if [[ "${#REQUESTED_DS[@]}" -gt 0 && -z "${REQUESTED_SET[$ds_name]:-}" ]]; then
      continue
    fi
    fasta_path="$(resolve_path_under_server "$GPM_SERVER_DIR" "$fasta_relpath")"
    [[ -f "$fasta_path" ]] || die "Locator FASTA for dataset '${ds_name}' seq '${seq_name}' not found: ${fasta_path}"
    SOURCE_SEQ_FASTA["$(make_source_seq_key "$ds_name" "$seq_name")"]="$fasta_path"
  done < <(tail -n +2 "$SOURCE_SEQ_LOCATOR_TSV")
fi

while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  ds_name="$(printf '%s\n' "$line" | cut -f$((dataset_name_col + 1)))"
  fasta_relpath="$(printf '%s\n' "$line" | cut -f$((fasta_relpath_col + 1)))"
  [[ -n "$ds_name" ]] || continue
  if [[ "${#REQUESTED_DS[@]}" -gt 0 && -z "${REQUESTED_SET[$ds_name]:-}" ]]; then
    continue
  fi
  if [[ "$HAS_SOURCE_SEQ_LOCATORS" == "false" ]]; then
    fasta_path="$(resolve_path_under_server "$GPM_SERVER_DIR" "$fasta_relpath")"
    [[ -f "$fasta_path" ]] || die "FASTA for dataset '${ds_name}' not found: ${fasta_path}"
    DATASET_FASTA["$ds_name"]="$fasta_path"
  fi
  DATASET_NAMES+=("$ds_name")
done < <(tail -n +2 "$DATASETS_TSV")

if [[ "${#REQUESTED_DS[@]}" -gt 0 && "${#DATASET_NAMES[@]}" -eq 0 ]]; then
  die "No dataset FASTA files matched the requested --ds filters"
fi

IFS=$'\t' read -r -a reference_header < "$REFERENCE_TSV" || die "metadata/reference.tsv is empty"
reference_fasta_relpath_col="$(column_index "fasta_relpath" "${reference_header[@]}")"
REFERENCE_FASTA=""
if [[ -f "$REFERENCE_CHR_LOCATOR_TSV" ]]; then
  HAS_REFERENCE_CHR_LOCATORS=true
  IFS=$'\t' read -r -a reference_locator_header < "$REFERENCE_CHR_LOCATOR_TSV" || die "metadata/reference_chr_locator.tsv is empty"
  reference_locator_chr_name_col="$(column_index "reference_chr_name" "${reference_locator_header[@]}")"
  reference_locator_fasta_relpath_col="$(column_index "fasta_relpath" "${reference_locator_header[@]}")"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    chr_name="$(printf '%s\n' "$line" | cut -f$((reference_locator_chr_name_col + 1)))"
    fasta_relpath="$(printf '%s\n' "$line" | cut -f$((reference_locator_fasta_relpath_col + 1)))"
    [[ -n "$chr_name" && -n "$fasta_relpath" ]] || continue
    fasta_path="$(resolve_path_under_server "$GPM_SERVER_DIR" "$fasta_relpath")"
    [[ -f "$fasta_path" ]] || die "Locator FASTA for reference chr '${chr_name}' not found: ${fasta_path}"
    REFERENCE_CHR_FASTA["$chr_name"]="$fasta_path"
  done < <(tail -n +2 "$REFERENCE_CHR_LOCATOR_TSV")
else
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    reference_fasta_relpath="$(printf '%s\n' "$line" | cut -f$((reference_fasta_relpath_col + 1)))"
    [[ -n "$reference_fasta_relpath" ]] || continue
    REFERENCE_FASTA="$(resolve_path_under_server "$GPM_SERVER_DIR" "$reference_fasta_relpath")"
    break
  done < <(tail -n +2 "$REFERENCE_TSV")
  [[ -n "$REFERENCE_FASTA" ]] || die "No reference FASTA path found in metadata/reference.tsv"
  [[ -f "$REFERENCE_FASTA" ]] || die "Reference FASTA not found: ${REFERENCE_FASTA}"
fi

infer_dataset_name() {
  local ctg_name="$1"
  local best=""
  for ds_name in "${DATASET_NAMES[@]}"; do
    if [[ "$ctg_name" == "${ds_name}_"* ]]; then
      if [[ "${#ds_name}" -gt "${#best}" ]]; then
        best="$ds_name"
      fi
    fi
  done
  if [[ -n "$best" ]]; then
    printf '%s\n' "$best"
    return
  fi
  if [[ "${#DATASET_NAMES[@]}" -eq 1 ]]; then
    printf '%s\n' "${DATASET_NAMES[0]}"
    return
  fi
  die "Could not infer dataset for TSV Ctg value '${ctg_name}'. Pass --ds or keep dataset_name_ prefix in Ctg."
}

append_gap() {
  local length="$1"
  validate_positive_int "gap length" "$length"
  awk -v n="$length" 'BEGIN { for (i = 0; i < n; i++) printf "N" }' >> "$RAW_SEQUENCE_TMP"
}

append_fasta_region() {
  local fasta_path="$1"
  local seq_id="$2"
  local start="$3"
  local end="$4"
  local orient="$5"
  validate_positive_int "Ctg_start" "$start"
  validate_positive_int "Ctg_end" "$end"

  local region_start="$start"
  local region_end="$end"
  if [[ "$start" -gt "$end" ]]; then
    region_start="$end"
    region_end="$start"
  fi

  local region_tmp
  region_tmp="$(mktemp)"
  if ! samtools faidx "$fasta_path" "${seq_id}:${region_start}-${region_end}" \
    | awk 'NR > 1 { gsub(/[[:space:]]/, ""); printf "%s", $0 }' > "$region_tmp"; then
    rm -f "$region_tmp"
    die "Failed to extract ${seq_id}:${region_start}-${region_end} from ${fasta_path}"
  fi
  if [[ ! -s "$region_tmp" ]]; then
    rm -f "$region_tmp"
    die "Extracted empty sequence for ${seq_id}:${region_start}-${region_end} from ${fasta_path}"
  fi

  if [[ "$orient" == "-" ]]; then
    rev "$region_tmp" | tr 'ACGTURYSWKMBDHVacgturyswkmbdhv' 'TGCAAYRSWMKVHDBtgcaayrswmkvhdb' >> "$RAW_SEQUENCE_TMP"
  else
    cat "$region_tmp" >> "$RAW_SEQUENCE_TMP"
  fi
  rm -f "$region_tmp"
}

append_reference_segment_region() {
  local ctg_name="$1"
  local orient="$2"
  if [[ ! "$ctg_name" =~ ^ref_(.+):([0-9]+)-([0-9]+)$ ]]; then
    return 1
  fi

  local reference_chr_name="${BASH_REMATCH[1]}"
  local absolute_start="${BASH_REMATCH[2]}"
  local absolute_end="${BASH_REMATCH[3]}"
  local reference_fasta_path=""
  if [[ "$HAS_REFERENCE_CHR_LOCATORS" == "true" ]]; then
    reference_fasta_path="${REFERENCE_CHR_FASTA[$reference_chr_name]:-}"
    [[ -n "$reference_fasta_path" ]] || die "No locator FASTA found for reference chr '${reference_chr_name}'"
  else
    reference_fasta_path="$REFERENCE_FASTA"
  fi
  append_fasta_region "$reference_fasta_path" "$reference_chr_name" "$absolute_start" "$absolute_end" "$orient"
}

OUTPUT_DIR="$(dirname "$OUTPUT_PATH")"
mkdir -p "$OUTPUT_DIR"
RAW_SEQUENCE_TMP="$(mktemp)"
OUTPUT_TMP="$(mktemp)"
trap 'rm -f "$RAW_SEQUENCE_TMP" "$OUTPUT_TMP"' EXIT

record_name="$(basename "$OUTPUT_PATH")"
record_name="${record_name%.fasta}"
record_name="${record_name%.fa}"
[[ -n "$record_name" ]] || record_name="final_path"

line_number=0
while IFS=$'\t' read -r row_index ctg origin_id overall_len orient ctg_start ctg_end chr_start chr_end extra; do
  line_number=$((line_number + 1))
  if [[ "$line_number" -eq 1 && "$row_index" == "#" ]]; then
    continue
  fi
  [[ -n "${row_index}${ctg}${origin_id}${orient}${ctg_start}${ctg_end}${chr_start}${chr_end}" ]] || continue
  [[ -n "$ctg" ]] || die "Line ${line_number}: missing Ctg"
  [[ -n "$chr_start" && -n "$chr_end" ]] || die "Line ${line_number}: missing Chr_start/Chr_end"
  validate_positive_int "Chr_start on line ${line_number}" "$chr_start"
  validate_positive_int "Chr_end on line ${line_number}" "$chr_end"

  if [[ "$ctg" == "Gap" || "$origin_id" == "NA" ]]; then
    gap_len=$((chr_end - chr_start + 1))
    [[ "$gap_len" -gt 0 ]] || die "Line ${line_number}: invalid gap coordinates"
    append_gap "$gap_len"
    continue
  fi

  [[ "$orient" == "+" || "$orient" == "-" ]] || die "Line ${line_number}: orient must be + or -"
  if append_reference_segment_region "$ctg" "$orient"; then
    continue
  fi

  [[ -n "$origin_id" ]] || die "Line ${line_number}: missing Origin ID for non-gap row"
  ds_name="$(infer_dataset_name "$ctg")"
  if [[ "$HAS_SOURCE_SEQ_LOCATORS" == "true" ]]; then
    source_seq_key="$(make_source_seq_key "$ds_name" "$origin_id")"
    fasta_path="${SOURCE_SEQ_FASTA[$source_seq_key]:-}"
    [[ -n "$fasta_path" ]] || die "No locator FASTA found for dataset '${ds_name}' seq '${origin_id}'"
  else
    fasta_path="${DATASET_FASTA[$ds_name]:-}"
    [[ -n "$fasta_path" ]] || die "No FASTA found for dataset '${ds_name}'"
  fi
  append_fasta_region "$fasta_path" "$origin_id" "$ctg_start" "$ctg_end" "$orient"
done < "$TSV_PATH"

[[ -s "$RAW_SEQUENCE_TMP" ]] || die "No sequence was generated from TSV: $TSV_PATH"

{
  printf '>%s\n' "$record_name"
  fold -w 80 "$RAW_SEQUENCE_TMP"
} > "$OUTPUT_TMP"

mv "$OUTPUT_TMP" "$OUTPUT_PATH"
echo "Wrote final path FASTA: $OUTPUT_PATH"
