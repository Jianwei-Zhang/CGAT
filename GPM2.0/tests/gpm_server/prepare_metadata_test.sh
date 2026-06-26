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
exit 0
EOF

cat > "${FAKE_BIN}/makeblastdb" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "${FAKE_BIN}/blastn" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "${FAKE_BIN}/meryl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "${FAKE_BIN}/winnowmap" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "${FAKE_BIN}/zip" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/makeblastdb" "${FAKE_BIN}/blastn" "${FAKE_BIN}/meryl" "${FAKE_BIN}/winnowmap" "${FAKE_BIN}/zip"

write_multi_fasta() {
  local path="$1"
  shift
  : > "$path"
  while [[ $# -ge 2 ]]; do
    printf '>%s\n%s\n' "$1" "$2" >> "$path"
    shift 2
  done
}

assert_prepare_option() {
  local path="$1"
  local expected_key="$2"
  local expected_value="$3"
  awk -F '\t' -v expected_key="$expected_key" -v expected_value="$expected_value" '
    NR == 1 {
      if ($1 != "key" || $2 != "value" || NF != 2) {
        print "prepare_options.tsv must use key/value header" > "/dev/stderr"
        exit 1
      }
      next
    }
    $1 == expected_key {
      found = 1
      if ($2 != expected_value) {
        printf "expected %s=%s, got %s\n", expected_key, expected_value, $2 > "/dev/stderr"
        exit 1
      }
    }
    END {
      if (!found) {
        printf "missing prepare option: %s\n", expected_key > "/dev/stderr"
        exit 1
      }
    }
  ' "$path"
}

ref="${TMP_DIR}/ref.fa"
ds="${TMP_DIR}/ds.fa"
cen="${TMP_DIR}/cen.fa"
output_root="${TMP_DIR}/gpm_server"
write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAA"
write_multi_fasta "$ds" "tig_add" "AAAAAAAAAAAAAAAAAAAA"
write_multi_fasta "$cen" "Chr01_centromere" "AAAAAAAAAA"

mkdir -p "${output_root}/data/reference" "${output_root}/data/datasets"
printf 'stale_ref\t1\t0\t1\t2\n' > "${output_root}/data/reference/ref_add_options.fa.fai"
printf 'stale_ds\t1\t0\t1\t2\n' > "${output_root}/data/datasets/ds_add.fa.fai"

PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
  --ref ref_add_options "$ref" \
  --ds ds_add "$ds" \
  --skip-self \
  --score 71 \
  --minimap-preset asm5 \
  --tel TTAGGG 2 \
  --cen "$cen" \
  -o "$output_root" >/dev/null

metadata_path="${output_root}/metadata/prepare_options.tsv"
[[ -f "$metadata_path" ]] || {
  echo "expected file: $metadata_path" >&2
  exit 1
}

assert_prepare_option "$metadata_path" chr_assignment_min_coverage_percent 71
assert_prepare_option "$metadata_path" alignment_engine minimap2
assert_prepare_option "$metadata_path" minimap_preset asm5
assert_prepare_option "$metadata_path" blastn_task blastn
assert_prepare_option "$metadata_path" blastn_evalue 1e-10
assert_prepare_option "$metadata_path" blastn_dust no
assert_prepare_option "$metadata_path" winnowmap_preset asm20
assert_prepare_option "$metadata_path" winnowmap_kmer 19
assert_prepare_option "$metadata_path" winnowmap_repeat_fraction 0.9998
assert_prepare_option "$metadata_path" threads 10
assert_prepare_option "$metadata_path" skip_self true
assert_prepare_option "$metadata_path" self_alignment_scope none
assert_prepare_option "$metadata_path" tel_enabled true
assert_prepare_option "$metadata_path" cen_enabled true
assert_prepare_option "$metadata_path" cen_min_len 10000
assert_prepare_option "$metadata_path" cen_min_identity 80

grep -q $'^Chr01\t20\t' "${output_root}/data/reference/ref_add_options.fa.fai" || {
  echo "reference .fai was not regenerated from the current FASTA" >&2
  exit 1
}
grep -q $'^tig_add\t20\t' "${output_root}/data/datasets/ds_add.fa.fai" || {
  echo "dataset .fai was not regenerated from the current FASTA" >&2
  exit 1
}

echo "gpm_server_prepare_metadata_test.sh: ok"
