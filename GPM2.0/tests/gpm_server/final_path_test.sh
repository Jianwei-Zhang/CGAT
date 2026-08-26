#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/server/export_final_path_fasta.sh"
EXPORT_BASH="$(command -v "${GPM_TEST_BASH:-bash}")" || {
  echo "final-path export test Bash not found: ${GPM_TEST_BASH:-bash}" >&2
  exit 1
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_BIN="${TMP_DIR}/bin"
mkdir -p "$FAKE_BIN"
ln -s "$EXPORT_BASH" "${FAKE_BIN}/bash"

cat > "${FAKE_BIN}/samtools" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "faidx" ]] || exit 1
fasta="$2"
region="${3:-}"
python3 - "$fasta" "$region" <<'PY'
import sys

fasta_path = sys.argv[1]
region = sys.argv[2]
seqs = {}
name = None
parts = []
with open(fasta_path, "r", encoding="utf-8") as handle:
    for raw in handle:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                seqs[name] = "".join(parts)
            name = line[1:].split()[0]
            parts = []
        else:
            parts.append(line)
    if name is not None:
        seqs[name] = "".join(parts)

seq_name, coords = region.split(":", 1)
start_text, end_text = coords.split("-", 1)
start = int(start_text)
end = int(end_text)
sequence = seqs[seq_name][start - 1:end]
print(f">{seq_name}:{start}-{end}")
print(sequence)
PY
EOF
chmod +x "${FAKE_BIN}/samtools"

assert_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    echo "expected file: $path" >&2
    exit 1
  }
}

assert_export_error() {
  local server_root="$1"
  local tsv_path="$2"
  local expected_error="$3"
  local error_path="$4"
  shift 4

  if PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "$SCRIPT" \
    --tsv "$tsv_path" \
    --gpm_server "$server_root" \
    -o "${error_path}.fa" \
    "$@" \
    >/dev/null 2>"$error_path"; then
    echo "expected final-path export to fail: ${expected_error}" >&2
    exit 1
  fi
  grep -F "$expected_error" "$error_path" >/dev/null || {
    echo "expected final-path error: ${expected_error}" >&2
    cat "$error_path" >&2
    exit 1
  }
  if grep -F "unbound variable" "$error_path" >/dev/null; then
    echo "final-path validation leaked a nounset error" >&2
    cat "$error_path" >&2
    exit 1
  fi
}

write_server_bundle() {
  local root="$1"
  mkdir -p "${root}/metadata" "${root}/data/reference" "${root}/data/datasets"
  cat > "${root}/metadata/reference.tsv" <<'EOF'
reference_name	species_name	assembly_label	fasta_relpath	fai_relpath
ref	unknown	ref	data/reference/ref.fa	data/reference/ref.fa.fai
EOF
  cat > "${root}/metadata/datasets.tsv" <<'EOF'
dataset_name	assembler	assembler_version	fasta_relpath	fai_relpath	self_alignment_available
ds	ds		data/datasets/ds.fa	data/datasets/ds.fa.fai	true
EOF
  cat > "${root}/data/reference/ref.fa" <<'EOF'
>Chr01
AAAACCCCGGGGTTTT
EOF
  cat > "${root}/data/datasets/ds.fa" <<'EOF'
>tigA
ACGTACGT
EOF
  : > "${root}/data/reference/ref.fa.fai"
  : > "${root}/data/datasets/ds.fa.fai"
}

write_partitioned_server_bundle() {
  local root="$1"
  mkdir -p \
    "${root}/metadata" \
    "${root}/data/reference/chrs" \
    "${root}/data/partitions/chr/Chr01"
  cat > "${root}/metadata/package.tsv" <<'EOF'
package_mode	fast
sequence_layout	partitioned
EOF
  cat > "${root}/metadata/reference.tsv" <<'EOF'
reference_name	species_name	assembly_label	fasta_relpath	fai_relpath
ref	unknown	ref	data/reference/ref.fa	data/reference/ref.fa.fai
EOF
  cat > "${root}/metadata/datasets.tsv" <<'EOF'
dataset_name	assembler	assembler_version	fasta_relpath	fai_relpath	self_alignment_available
ds	ds		data/datasets/ds.fa	data/datasets/ds.fa.fai	true
EOF
  cat > "${root}/metadata/reference_chr_locator.tsv" <<'EOF'
reference_chr_name	fasta_relpath
Chr01	data/reference/chrs/Chr01.fa
EOF
  cat > "${root}/metadata/source_seq_locator.tsv" <<'EOF'
dataset_name	seq_name	fasta_relpath
ds	tigA	data/partitions/chr/Chr01/ds.fa
EOF
  cat > "${root}/data/reference/chrs/Chr01.fa" <<'EOF'
>Chr01
AAAACCCCGGGGTTTT
EOF
  cat > "${root}/data/partitions/chr/Chr01/ds.fa" <<'EOF'
>tigA
TTGGAACC
EOF
}

write_multi_dataset_server_bundle() {
  local root="$1"
  write_server_bundle "$root"
  cat >> "${root}/metadata/datasets.tsv" <<'EOF'
support	support		data/datasets/support.fa	data/datasets/support.fa.fai	true
EOF
  cat > "${root}/data/datasets/support.fa" <<'EOF'
>tigB
TTTTCCCC
EOF
  : > "${root}/data/datasets/support.fa.fai"
}

write_final_path_tsv() {
  local path="$1"
  cat > "$path" <<'EOF'
#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
1	ref_Chr01:5-8	Chr01	4	-	4	1	1	4
2	Gap	NA	3	NA	1	3	5	7
3	ds_tigA	tigA	8	+	2	5	8	11
EOF
}

write_partitioned_final_path_tsv() {
  local path="$1"
  cat > "$path" <<'EOF'
#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
1	ds_tigA	tigA	8	+	2	6	1	5
2	Gap	NA	2	NA	1	2	6	7
3	ref_Chr01:1-4	Chr01	4	-	4	1	8	11
EOF
}

write_multi_dataset_final_path_tsv() {
  local path="$1"
  cat > "$path" <<'EOF'
#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
1	ds_tigA	tigA	8	+	1	4	1	4
2	support_tigB	tigB	8	+	1	4	5	8
EOF
}

write_project_final_path_tsv() {
  local path="$1"
  cat > "$path" <<'EOF'
Chr	#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
Chr01	1	ds_tigA	tigA		+	1	4	1	4
Chr02	1	ds_tigA	tigA	8	-	5	2	1	4
EOF
}

test_exports_ref_segments_and_dataset_segments_from_same_tsv() {
  local server_root="${TMP_DIR}/gpm_server"
  local tsv_path="${TMP_DIR}/final_path.tsv"
  local output_path="${TMP_DIR}/final_path.fa"
  write_server_bundle "$server_root"
  write_final_path_tsv "$tsv_path"

  PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "$SCRIPT" \
    --tsv "$tsv_path" \
    --gpm_server "$server_root" \
    -o "$output_path" >/dev/null

  assert_file "$output_path"
  local sequence
  sequence="$(awk 'NR > 1 { gsub(/[[:space:]]/, ""); printf "%s", $0 }' "$output_path")"
  [[ "$sequence" == "GGGGNNNCGTA" ]] || {
    echo "unexpected exported sequence: $sequence" >&2
    exit 1
  }
}

test_exports_partitioned_fast_bundle_via_locator_manifests() {
  local server_root="${TMP_DIR}/gpm_server_partitioned"
  local tsv_path="${TMP_DIR}/final_path_partitioned.tsv"
  local output_path="${TMP_DIR}/final_path_partitioned.fa"
  write_partitioned_server_bundle "$server_root"
  write_partitioned_final_path_tsv "$tsv_path"

  PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "$SCRIPT" \
    --tsv "$tsv_path" \
    --gpm_server "$server_root" \
    --ds ds \
    -o "$output_path" >/dev/null

  assert_file "$output_path"
  local sequence
  sequence="$(awk 'NR > 1 { gsub(/[[:space:]]/, ""); printf "%s", $0 }' "$output_path")"
  [[ "$sequence" == "TGGAANNTTTT" ]] || {
    echo "unexpected partitioned exported sequence: $sequence" >&2
    exit 1
  }
}

test_exports_with_multiple_dataset_filters() {
  local server_root="${TMP_DIR}/gpm_server_multi"
  local tsv_path="${TMP_DIR}/final_path_multi.tsv"
  local output_path="${TMP_DIR}/final_path_multi.fa"
  write_multi_dataset_server_bundle "$server_root"
  write_multi_dataset_final_path_tsv "$tsv_path"

  PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "$SCRIPT" \
    --tsv "$tsv_path" \
    --gpm_server "$server_root" \
    --ds ds \
    --ds support \
    -o "$output_path" >/dev/null

  assert_file "$output_path"
  local sequence
  sequence="$(awk 'NR > 1 { gsub(/[[:space:]]/, ""); printf "%s", $0 }' "$output_path")"
  [[ "$sequence" == "ACGTTTTT" ]] || {
    echo "unexpected multi-dataset exported sequence: $sequence" >&2
    exit 1
  }
}

test_exports_project_tsv_as_one_fasta_record_per_chromosome() {
  local server_root="${TMP_DIR}/gpm_server_project"
  local tsv_path="${TMP_DIR}/project_final_path.tsv"
  local output_path="${TMP_DIR}/project_final_path.fa"
  write_server_bundle "$server_root"
  write_project_final_path_tsv "$tsv_path"

  PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "$SCRIPT" \
    --tsv "$tsv_path" \
    --gpm_server "$server_root" \
    -o "$output_path" >/dev/null

  assert_file "$output_path"
  local expected_path="${TMP_DIR}/project_final_path.expected.fa"
  cat > "$expected_path" <<'EOF'
>Chr01
ACGT
>Chr02
TACG
EOF
  if ! cmp -s "$expected_path" "$output_path"; then
    echo "unexpected project final-path FASTA" >&2
    diff -u "$expected_path" "$output_path" >&2 || exit 1
    exit 1
  fi
}

test_rejects_unknown_final_path_tsv_header() {
  local server_root="${TMP_DIR}/gpm_server_unknown_header"
  local tsv_path="${TMP_DIR}/unknown_header.tsv"
  write_server_bundle "$server_root"
  cat > "$tsv_path" <<'EOF'
Chromosome	#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
Chr01	1	ds_tigA	tigA	8	+	1	4	1	4
EOF

  assert_export_error \
    "$server_root" \
    "$tsv_path" \
    "Unsupported final path TSV header" \
    "${TMP_DIR}/unknown_header.err"
}

test_rejects_project_tsv_rows_with_wrong_column_count() {
  local server_root="${TMP_DIR}/gpm_server_wrong_width"
  local tsv_path="${TMP_DIR}/wrong_width.tsv"
  write_server_bundle "$server_root"
  cat > "$tsv_path" <<'EOF'
Chr	#	Ctg	Origin ID	overall_len	orient	Ctg_start	Ctg_end	Chr_start	Chr_end
Chr01	1	ds_tigA	tigA	8	+	1	4	1
EOF

  assert_export_error \
    "$server_root" \
    "$tsv_path" \
    "Line 2: expected 10 TSV columns, found 9" \
    "${TMP_DIR}/wrong_width.err"
}

test_generated_server_script_defaults_to_own_gpm_server_dir() {
  local server_root="${TMP_DIR}/gpm_server_generated"
  local tsv_path="${TMP_DIR}/final_path_generated.tsv"
  local output_path="${TMP_DIR}/final_path_generated.fa"
  write_server_bundle "$server_root"
  write_final_path_tsv "$tsv_path"
  mkdir -p "${server_root}/.prepare_lib"
  cp "${REPO_ROOT}/server/templates/export_final_path_fasta.sh" "${server_root}/export_final_path_fasta.sh"
  cp -R "${REPO_ROOT}/server/lib" "${server_root}/.prepare_lib/lib"

  PATH="${FAKE_BIN}:$PATH" "$EXPORT_BASH" "${server_root}/export_final_path_fasta.sh" \
    --tsv "$tsv_path" \
    -o "$output_path" >/dev/null

  assert_file "$output_path"
  local sequence
  sequence="$(awk 'NR > 1 { gsub(/[[:space:]]/, ""); printf "%s", $0 }' "$output_path")"
  [[ "$sequence" == "GGGGNNNCGTA" ]] || {
    echo "unexpected generated-script exported sequence: $sequence" >&2
    exit 1
  }
}

test_rejects_blank_metadata_headers_without_nounset_errors() {
  local tsv_path="${TMP_DIR}/final_path_invalid_metadata.tsv"
  write_final_path_tsv "$tsv_path"

  local datasets_root="${TMP_DIR}/blank_datasets_header"
  write_server_bundle "$datasets_root"
  printf '\n' > "${datasets_root}/metadata/datasets.tsv"
  assert_export_error \
    "$datasets_root" \
    "$tsv_path" \
    "metadata/datasets.tsv header is empty" \
    "${TMP_DIR}/blank_datasets_header.err"

  local source_locator_root="${TMP_DIR}/blank_source_locator_header"
  write_partitioned_server_bundle "$source_locator_root"
  printf '\n' > "${source_locator_root}/metadata/source_seq_locator.tsv"
  assert_export_error \
    "$source_locator_root" \
    "$tsv_path" \
    "metadata/source_seq_locator.tsv header is empty" \
    "${TMP_DIR}/blank_source_locator_header.err"

  local reference_root="${TMP_DIR}/blank_reference_header"
  write_server_bundle "$reference_root"
  printf '\n' > "${reference_root}/metadata/reference.tsv"
  assert_export_error \
    "$reference_root" \
    "$tsv_path" \
    "metadata/reference.tsv header is empty" \
    "${TMP_DIR}/blank_reference_header.err"

  local reference_locator_root="${TMP_DIR}/blank_reference_locator_header"
  write_partitioned_server_bundle "$reference_locator_root"
  printf '\n' > "${reference_locator_root}/metadata/reference_chr_locator.tsv"
  assert_export_error \
    "$reference_locator_root" \
    "$tsv_path" \
    "metadata/reference_chr_locator.tsv header is empty" \
    "${TMP_DIR}/blank_reference_locator_header.err"
}

test_rejects_empty_dataset_catalog_without_nounset_errors() {
  local server_root="${TMP_DIR}/empty_dataset_catalog"
  local tsv_path="${TMP_DIR}/final_path_empty_dataset_catalog.tsv"
  write_server_bundle "$server_root"
  write_final_path_tsv "$tsv_path"
  sed -n '1p' "${server_root}/metadata/datasets.tsv" \
    > "${server_root}/metadata/datasets.tsv.tmp"
  mv "${server_root}/metadata/datasets.tsv.tmp" \
    "${server_root}/metadata/datasets.tsv"

  assert_export_error \
    "$server_root" \
    "$tsv_path" \
    "metadata/datasets.tsv contains no usable dataset rows" \
    "${TMP_DIR}/empty_dataset_catalog.err"
}

test_exports_ref_segments_and_dataset_segments_from_same_tsv

test_exports_partitioned_fast_bundle_via_locator_manifests

test_exports_with_multiple_dataset_filters

test_exports_project_tsv_as_one_fasta_record_per_chromosome

test_rejects_unknown_final_path_tsv_header

test_rejects_project_tsv_rows_with_wrong_column_count

test_generated_server_script_defaults_to_own_gpm_server_dir

test_rejects_blank_metadata_headers_without_nounset_errors

test_rejects_empty_dataset_catalog_without_nounset_errors

echo "final_path_test.sh: ok"
