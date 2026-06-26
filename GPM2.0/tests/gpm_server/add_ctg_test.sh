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
awk '
  /^>/ {
    if (name != "") {
      printf "%s\t%s\t0\t%s\t%s\n", name, length_bp, length_bp, length_bp + 1
    }
    name = $1
    sub(/^>/, "", name)
    length_bp = 0
    next
  }
  {
    gsub(/[[:space:]]/, "")
    length_bp += length($0)
  }
  END {
    if (name != "") {
      printf "%s\t%s\t0\t%s\t%s\n", name, length_bp, length_bp, length_bp + 1
    }
  }
' "$fasta" > "${fasta}.fai"
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
    -t)
      shift 2
      ;;
    -X)
      shift
      ;;
    -*)
      shift
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

cat > "${FAKE_BIN}/makeblastdb" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -in)
      input="$2"
      shift 2
      ;;
    -out)
      output="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

[[ -n "$input" && -n "$output" ]] || exit 1
mkdir -p "$(dirname "$output")"
printf '%s\n' "$input" > "${output}.source"
EOF

cat > "${FAKE_BIN}/blastn" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

task=""
query=""
db=""
output=""
db_count=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -task)
      task="$2"
      shift 2
      ;;
    -query)
      query="$2"
      shift 2
      ;;
    -db)
      db="$2"
      db_count=$((db_count + 1))
      shift 2
      ;;
    -out)
      output="$2"
      shift 2
      ;;
    -*)
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

[[ "$db_count" -eq 1 ]] || {
  echo "expected exactly one -db argument, saw $db_count" >&2
  exit 1
}
[[ -n "$query" && -n "$db" && -n "$output" ]] || exit 1
target="$(cat "${db}.source")"
target_name="$(awk '/^>/ { sub(/^>/, "", $1); print $1; exit }' "$target")"
target_len="$(awk 'BEGIN { n=0 } !/^>/ { gsub(/[[:space:]]/, ""); n += length($0) } END { print n }' "$target")"
query_name="$(awk '/^>/ { sub(/^>/, "", $1); print $1; exit }' "$query")"
query_len="$(awk 'BEGIN { n=0 } !/^>/ { gsub(/[[:space:]]/, ""); n += length($0) } END { print n }' "$query")"
align_len="$query_len"
if [[ "$align_len" -gt "$target_len" ]]; then
  align_len="$target_len"
fi

mkdir -p "$(dirname "$output")"
printf '%s\t%s\t99.0\t%s\t0\t0\t1\t%s\t1\t%s\t1e-20\t500\t%s\t%s\t%s\t0\n' \
  "$query_name" "$target_name" "$align_len" "$align_len" "$align_len" "$query_len" "$target_len" "$align_len" > "$output"
printf 'task=%s db_count=%s target=%s query=%s output=%s\n' "$task" "$db_count" "$target" "$query" "$output" >> "${GPM_TEST_BLASTN_LOG:?}"
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

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/makeblastdb" "${FAKE_BIN}/blastn" "${FAKE_BIN}/zip"

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

ref="${TMP_DIR}/ref.fa"
ds1="${TMP_DIR}/ds1.fa"
ds2="${TMP_DIR}/ds2.fa"
final_fa="${TMP_DIR}/gap.final.fa"
output_root="${TMP_DIR}/gpm_server"
export GPM_TEST_MINIMAP_LOG="${TMP_DIR}/minimap2.log"
export GPM_TEST_BLASTN_LOG="${TMP_DIR}/blastn.log"

write_fasta "$ref" "Chr01" "$(repeat_base A 2000)"
write_fasta "$ds1" "ds1_ctg" "$(repeat_base A 1200)"
write_fasta "$ds2" "ds2_ctg" "$(repeat_base A 1000)"
write_fasta "$final_fa" "old_gap_name" "$(repeat_base A 400)NNNNNNNNNN$(repeat_base A 590)"

PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
  --ref ref_add_ctg "$ref" \
  --ds hifiasm "$ds1" \
  --ds flye "$ds2" \
  --score 60 \
  --minimap-preset asm5 \
  -o "$output_root" >/dev/null

test -x "${output_root}/add_ctg.sh"
PATH="${FAKE_BIN}:$PATH" bash "${output_root}/run_all.sh"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/add_ctg.sh" \
  --ctg Chr01_gap3_filled \
  --chr Chr01 \
  --track hifiasm \
  --source gapfiller \
  -i "$final_fa" >/dev/null

test -f "${output_root}/add_Chr01_gap3_filled.zip"
grep -q $'^derived_ctg\t' "${output_root}/metadata/datasets.tsv"
grep -q $'^derived_ctg\tChr01_gap3_filled\t' "${output_root}/metadata/chr_assignments.tsv"
grep -q $'^derived_ctg\tChr01_gap3_filled\tdata/derived_ctgs/Chr01_gap3_filled.fa$' "${output_root}/metadata/source_seq_locator.tsv"
grep -q $'^derived_ctg\tChr01_gap3_filled\t401\t410\t10$' "${output_root}/metadata/source_seq_n_regions.tsv"
grep -q $'^derived_ctg\tChr01_gap3_filled\tgapfiller\tgap.final.fa\t' "${output_root}/metadata/derived_ctgs.tsv"
grep -q $'^derived_ctg\tChr01_gap3_filled\tChr01\thifiasm\tderived\t' "${output_root}/metadata/track_members.tsv"
grep -q '^>Chr01_gap3_filled$' "${output_root}/data/derived_ctgs/Chr01_gap3_filled.fa"
test -f "${output_root}/data/derived_ctgs/Chr01_gap3_filled.fa.fai"
test -f "${output_root}/data/datasets/derived_ctg.fa.fai"
test -f "${output_root}/runs/add_ctg/Chr01_gap3_filled_vs_ref/result.paf"
test -f "${output_root}/runs/chr_Chr01/add_ctg/hifiasm_vs_Chr01_gap3_filled/result.paf"
test -f "${output_root}/runs/chr_Chr01/add_ctg/flye_vs_Chr01_gap3_filled/result.paf"
grep -q 'preset=asm5' "$GPM_TEST_MINIMAP_LOG"

add_zip="${output_root}/add_Chr01_gap3_filled.zip"
assert_file_contains "$add_zip" $'package_type\tadd_ctg'
assert_file_contains "$add_zip" $'ctg_name\tChr01_gap3_filled'
assert_file_contains "$add_zip" $'target_chr\tChr01'
assert_file_contains "$add_zip" $'target_track\thifiasm'
assert_file_contains "$add_zip" $'source\tgapfiller'
assert_file_contains "$add_zip" $'skip_self\tfalse'
assert_file_contains "$add_zip" "--- gpm_server/metadata/derived_ctgs.tsv"
assert_file_contains "$add_zip" "--- gpm_server/metadata/track_members.tsv"
assert_file_contains "$add_zip" "--- gpm_server/data/derived_ctgs/Chr01_gap3_filled.fa"
assert_file_contains "$add_zip" "--- gpm_server/data/derived_ctgs/Chr01_gap3_filled.fa.fai"
assert_file_contains "$add_zip" "--- gpm_server/data/datasets/derived_ctg.fa.fai"
assert_file_contains "$add_zip" "--- gpm_server/runs/add_ctg/Chr01_gap3_filled_vs_ref/result.paf"
assert_file_contains "$add_zip" "--- gpm_server/runs/chr_Chr01/add_ctg/hifiasm_vs_Chr01_gap3_filled/result.paf"
assert_file_contains "$add_zip" "--- gpm_server/runs/chr_Chr01/add_ctg/flye_vs_Chr01_gap3_filled/result.paf"
assert_file_contains "$add_zip" $'derived_ctg\tChr01_gap3_filled\t401\t410\t10'

if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/add_ctg.sh" \
  --ctg Chr01_gap3_filled \
  --chr Chr01 \
  --track hifiasm \
  -i "$final_fa" >"${TMP_DIR}/duplicate.out" 2>&1; then
  echo "duplicate add_ctg should fail" >&2
  exit 1
fi
assert_file_contains "${TMP_DIR}/duplicate.out" "ctg name already exists: Chr01_gap3_filled"
assert_file_contains "${TMP_DIR}/duplicate.out" "Please choose a different --ctg name"

blast_output_root="${TMP_DIR}/gpm_server_blast"
PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
  --ref ref_add_ctg_blast "$ref" \
  --ds hifiasm "$ds1" \
  --score 60 \
  --aligner blastn \
  --blastn-task megablast \
  -o "$blast_output_root" >/dev/null

PATH="${FAKE_BIN}:$PATH" bash "${blast_output_root}/run_all.sh"
PATH="${FAKE_BIN}:$PATH" bash "${blast_output_root}/add_ctg.sh" \
  --ctg Chr01_gap4_filled \
  --chr Chr01 \
  --track hifiasm \
  -i "$final_fa" >/dev/null

test -f "${blast_output_root}/runs/add_ctg/Chr01_gap4_filled_vs_ref/result.paf"
test -f "${blast_output_root}/runs/chr_Chr01/add_ctg/hifiasm_vs_Chr01_gap4_filled/result.paf"
grep -q 'task=megablast db_count=1' "$GPM_TEST_BLASTN_LOG"
assert_file_contains "${blast_output_root}/add_Chr01_gap4_filled.zip" $'alignment_engine\tblastn'
assert_file_contains "${blast_output_root}/add_Chr01_gap4_filled.zip" $'blastn_task\tmegablast'

echo "gpm_server_add_ctg_test.sh: ok"
