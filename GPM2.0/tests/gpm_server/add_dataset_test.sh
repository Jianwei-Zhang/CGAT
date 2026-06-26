#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/server/prepare.sh"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_BIN="${TMP_DIR}/bin"
mkdir -p "$FAKE_BIN"

cat > "${FAKE_BIN}/samtools" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "faidx" ]] || exit 1
fasta="$2"
seq_name="$(awk '/^>/ { sub(/^>/, "", $1); print $1; exit }' "$fasta")"
seq_len="$(awk 'BEGIN { n=0 } !/^>/ { gsub(/[[:space:]]/, ""); n += length($0) } END { print n }' "$fasta")"
printf '%s\t%s\t0\t%s\t%s\n' "$seq_name" "$seq_len" "$seq_len" "$((seq_len + 1))" > "${fasta}.fai"
EOF

cat > "${FAKE_BIN}/minimap2" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

preset=""
output=""
declare -a positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -x)
      preset="$2"
      shift 2
      ;;
    -o)
      output="$2"
      shift 2
      ;;
    -*)
      if [[ "${2:-}" != "" && "$2" != -* && "$1" =~ ^-(t)$ ]]; then
        shift 2
      else
        shift
      fi
      ;;
    *)
      positional+=("$1")
      shift
      ;;
  esac
done

[[ -n "$output" ]] || exit 1
target="${positional[0]}"
query="${positional[1]}"
target_name="$(awk '/^>/ { sub(/^>/, "", $1); print $1; exit }' "$target")"
target_len="$(awk 'BEGIN { n=0 } !/^>/ { gsub(/[[:space:]]/, ""); n += length($0) } END { print n }' "$target")"
query_name="$(awk '/^>/ { sub(/^>/, "", $1); print $1; exit }' "$query")"
query_len="$(awk 'BEGIN { n=0 } !/^>/ { gsub(/[[:space:]]/, ""); n += length($0) } END { print n }' "$query")"
align_len="$query_len"
if [[ "$align_len" -gt "$target_len" ]]; then
  align_len="$target_len"
fi

mkdir -p "$(dirname "$output")"
printf '%s\t%s\t0\t%s\t+\t%s\t%s\t0\t%s\t%s\t%s\t60\n' \
  "$query_name" "$query_len" "$align_len" "$target_name" "$target_len" "$align_len" "$align_len" "$align_len" > "$output"
printf 'preset=%s target=%s query=%s output=%s\n' "$preset" "$target" "$query" "$output" >> "${GPM_TEST_MINIMAP_LOG:?}"
EOF

cat > "${FAKE_BIN}/zip" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

declare -a roots=()
declare -a excludes=()
out=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r)
      shift
      ;;
    -x)
      excludes+=("$2")
      shift 2
      ;;
    -*)
      shift
      ;;
    *)
      if [[ -z "$out" ]]; then
        out="$1"
      else
        roots+=("$1")
      fi
      shift
      ;;
  esac
done

[[ -n "$out" ]] || exit 1
mkdir -p "$(dirname "$out")"
: > "$out"
for root in "${roots[@]}"; do
  [[ -e "$root" ]] || continue
  while IFS= read -r path; do
    skip=false
    for pattern in "${excludes[@]}"; do
      if [[ "$path" == $pattern ]]; then
        skip=true
        break
      fi
    done
    "$skip" && continue
    printf '%s\n' "--- $path" >> "$out"
    cat "$path" >> "$out"
    printf '\n' >> "$out"
  done < <(find "$root" -type f | LC_ALL=C sort)
done
EOF

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/zip"

repeat_base() {
  local base="$1"
  local count="$2"
  awk -v base="$base" -v count="$count" 'BEGIN { for (i = 0; i < count; i += 1) printf "%s", base; printf "\n" }'
}

write_fasta() {
  local path="$1"
  local name="$2"
  local sequence="$3"
  printf '>%s\n%s\n' "$name" "$sequence" > "$path"
}

assert_file_contains() {
  local path="$1"
  local pattern="$2"
  grep -q -- "$pattern" "$path" || {
    echo "expected '$path' to contain pattern: $pattern" >&2
    exit 1
  }
}

assert_file_not_contains() {
  local path="$1"
  local pattern="$2"
  if grep -q -- "$pattern" "$path"; then
    echo "expected '$path' to not contain pattern: $pattern" >&2
    exit 1
  fi
}

ref="${TMP_DIR}/ref.fa"
ds1="${TMP_DIR}/ds1.fa"
ds4="${TMP_DIR}/ds4.fa"
output_root="${TMP_DIR}/gpm_server"
export GPM_TEST_MINIMAP_LOG="${TMP_DIR}/minimap2.log"

write_fasta "$ref" "Chr01" "$(repeat_base A 1500)"
write_fasta "$ds1" "ds1_ctg" "$(repeat_base A 1200)"
write_fasta "$ds4" "ds4_ctg" "$(repeat_base A 400)NNNN$(repeat_base A 796)"

PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
  --ref ref_add_script "$ref" \
  --ds ds1 "$ds1" \
  --skip-self \
  --score 71 \
  --minimap-preset asm5 \
  -o "$output_root" >/dev/null

test -x "${output_root}/add_dataset.sh"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/run_all.sh"

awk -F '\t' 'BEGIN { OFS = "\t" } $1 == "chr_assignment_min_coverage_percent" { $2 = "72" } { print }' \
  "${output_root}/metadata/prepare_options.tsv" > "${output_root}/metadata/prepare_options.tsv.tmp"
mv "${output_root}/metadata/prepare_options.tsv.tmp" "${output_root}/metadata/prepare_options.tsv"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/add_dataset.sh" --ds ds4 "$ds4" >/dev/null

test -f "${output_root}/add_ds4.zip"
grep -q $'^ds4\t' "${output_root}/metadata/datasets.tsv"
grep -q $'^ds4\tds4_ctg\t' "${output_root}/metadata/chr_assignments.tsv"
grep -q $'^ds4\tds4_ctg\t401\t404\t4$' "${output_root}/metadata/source_seq_n_regions.tsv"
grep -q 'preset=asm5' "$GPM_TEST_MINIMAP_LOG"
assert_file_contains "${output_root}/add_ds4.zip" $'package_type\tadd_dataset'
assert_file_contains "${output_root}/add_ds4.zip" $'dataset_name\tds4'
assert_file_contains "${output_root}/add_ds4.zip" $'chr_assignment_min_coverage_percent\t72'
assert_file_contains "${output_root}/add_ds4.zip" $'skip_self\ttrue'
assert_file_contains "${output_root}/add_ds4.zip" $'self_alignment_available\tfalse'
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/metadata/datasets.tsv"
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/metadata/source_seq_n_regions.tsv"
assert_file_contains "${output_root}/add_ds4.zip" $'ds4\tds4\t'
assert_file_contains "${output_root}/add_ds4.zip" $'ds4\tds4_ctg\t401\t404\t4'
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/data/datasets/ds4.fa"
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/data/datasets/ds4.fa.fai"
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/runs/ds4_vs_ref/result.paf"
assert_file_contains "${output_root}/add_ds4.zip" "--- gpm_server/runs/chr_Chr01/ds1_vs_ds4/result.paf"
assert_file_not_contains "${output_root}/add_ds4.zip" "--- gpm_server/metadata/reference.tsv"
assert_file_not_contains "${output_root}/add_ds4.zip" $'ds1\tds1\t'
assert_file_not_contains "${output_root}/add_ds4.zip" $'ds1\tds1_ctg\t'
assert_file_not_contains "${output_root}/add_ds4.zip" "--- gpm_server/data/datasets/ds1.fa"
assert_file_not_contains "${output_root}/add_ds4.zip" "--- gpm_server/runs/ds1_vs_ref/result.paf"

if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/add_dataset.sh" --ds ds4 "$ds4" >"${TMP_DIR}/duplicate.out" 2>&1; then
  echo "duplicate dataset add should fail" >&2
  exit 1
fi
assert_file_contains "${TMP_DIR}/duplicate.out" "Duplicate dataset name: ds4"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/package_full_zip.sh" >/dev/null
test -f "${TMP_DIR}/gpm_server.zip"
assert_file_contains "${TMP_DIR}/gpm_server.zip" "metadata/datasets.tsv"
assert_file_contains "${TMP_DIR}/gpm_server.zip" $'ds4\tds4\t'

echo "gpm_server_add_dataset_test.sh: ok"
