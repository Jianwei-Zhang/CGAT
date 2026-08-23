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

for grt_tool in nucmer delta-filter show-coords merqury.sh craq; do
  cat > "${FAKE_BIN}/${grt_tool}" <<EOF
#!/usr/bin/env bash
case "${grt_tool}:\${1:-}" in
  nucmer:--help)
    printf '%s\n' '     --batch=BASES' ' -t, --threads=NUM'
    ;;
  delta-filter:-h|show-coords:-h)
    printf '%s\n' '-r    reference-order option' '-l    sequence-length option'
    ;;
esac
exit 0
EOF
done

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
if [[ -n "${FAKE_ZIP_LOG:-}" ]]; then
  printf '%q ' "$@" >> "$FAKE_ZIP_LOG"
  printf '\n' >> "$FAKE_ZIP_LOG"
fi
exit 0
EOF

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/makeblastdb" "${FAKE_BIN}/blastn" "${FAKE_BIN}/meryl" "${FAKE_BIN}/winnowmap" "${FAKE_BIN}/zip" \
  "${FAKE_BIN}/nucmer" "${FAKE_BIN}/delta-filter" "${FAKE_BIN}/show-coords" "${FAKE_BIN}/merqury.sh" "${FAKE_BIN}/craq"

write_fasta() {
  local path="$1"
  local name="$2"
  printf '>%s\nACGT\n' "$name" > "$path"
}

write_multi_fasta() {
  local path="$1"
  shift
  : > "$path"
  while [[ $# -ge 2 ]]; do
    printf '>%s\n%s\n' "$1" "$2" >> "$path"
    shift 2
  done
}

write_gap_ref_partitioneda() {
  local path="$1"
  python3 - <<'PY' > "$path"
print(">Chr01")
print("A" * 5 + "N" * 99 + "C" * 4 + "N" * 100 + "G" * 3)
print(">Chr02")
print("T" * 6)
PY
}

gzip_copy() {
  local src="$1"
  local dst="$2"
  gzip -c "$src" > "$dst"
}

assert_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    echo "expected file: $path" >&2
    exit 1
  }
}

assert_dir() {
  local path="$1"
  [[ -d "$path" ]] || {
    echo "expected directory: $path" >&2
    exit 1
  }
}

assert_prepare_option() {
  local path="$1"
  local expected_key="$2"
  local expected_value="$3"
  awk -F '\t' -v expected_key="$expected_key" -v expected_value="$expected_value" '
    NR == 1 { next }
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

assert_package_metadata() {
  local path="$1"
  local expected_mode="$2"
  local expected_preassigned_chr="$3"
  local expected_self_scope="$4"
  local expected_cross_scope="$5"
  local expected_sequence_layout="${6:-partitioned}"
  local expected_score="${7:-60}"

  awk -F '\t' \
    -v expected_mode="$expected_mode" \
    -v expected_preassigned_chr="$expected_preassigned_chr" \
    -v expected_self_scope="$expected_self_scope" \
    -v expected_cross_scope="$expected_cross_scope" \
    -v expected_sequence_layout="$expected_sequence_layout" \
    -v expected_score="$expected_score" '
    NR == 1 {
      for (i = 1; i <= NF; i++) {
        columns[$i] = i
      }
      next
    }
    NR == 2 {
      if (!columns["workflow"] || !columns["schema_version"] || !columns["package_mode"] ||
          !columns["sequence_layout"] || !columns["preassigned_chr"] ||
          !columns["chr_assignment_min_coverage_percent"] || !columns["self_alignment_scope"] ||
          !columns["cross_alignment_scope"] || !columns["grt_precompute_enabled"] ||
          !columns["recipe_locked"] || !columns["final_path_schema_version"] ||
          !columns["reads_qc_enabled"]) {
        print "package.tsv missing expected columns" > "/dev/stderr"
        exit 1
      }
      if ($(columns["workflow"]) != "gpm_grt_precomputed_v2" ||
          $(columns["schema_version"]) != "2" ||
          $(columns["grt_precompute_enabled"]) != "true" ||
          $(columns["recipe_locked"]) != "true" ||
          $(columns["final_path_schema_version"]) != "1") {
        print "package.tsv missing locked GRT v1 identity" > "/dev/stderr"
        exit 1
      }
      if ($(columns["package_mode"]) != expected_mode) {
        printf "expected package_mode=%s, got %s\n", expected_mode, $(columns["package_mode"]) > "/dev/stderr"
        exit 1
      }
      if ($(columns["sequence_layout"]) != expected_sequence_layout) {
        printf "expected sequence_layout=%s, got %s\n", expected_sequence_layout, $(columns["sequence_layout"]) > "/dev/stderr"
        exit 1
      }
      if ($(columns["preassigned_chr"]) != expected_preassigned_chr) {
        printf "expected preassigned_chr=%s, got %s\n", expected_preassigned_chr, $(columns["preassigned_chr"]) > "/dev/stderr"
        exit 1
      }
      if ($(columns["chr_assignment_min_coverage_percent"]) != expected_score) {
        printf "expected chr_assignment_min_coverage_percent=%s, got %s\n", expected_score, $(columns["chr_assignment_min_coverage_percent"]) > "/dev/stderr"
        exit 1
      }
      if ($(columns["self_alignment_scope"]) != expected_self_scope) {
        printf "expected self_alignment_scope=%s, got %s\n", expected_self_scope, $(columns["self_alignment_scope"]) > "/dev/stderr"
        exit 1
      }
      if ($(columns["cross_alignment_scope"]) != expected_cross_scope) {
        printf "expected cross_alignment_scope=%s, got %s\n", expected_cross_scope, $(columns["cross_alignment_scope"]) > "/dev/stderr"
        exit 1
      }
      next
    }
    END {
      if (NR != 2) {
        print "expected package.tsv header + one data row" > "/dev/stderr"
        exit 1
      }
    }
  ' "$path"
}

test_score_option_sets_chr_assignment_threshold() {
  local ref="${TMP_DIR}/ref-score.fa"
  local ds="${TMP_DIR}/ds-score.fa"
  local output_root="${TMP_DIR}/score_gpm_server"
  write_fasta "$ref" ref_score
  write_fasta "$ds" ds_score

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_score "$ref" \
    --ds ds_score "$ds" \
    --score 72 \
    -o "$output_root" >/dev/null

  assert_package_metadata "${output_root}/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned" "72"

  local short_output_root="${TMP_DIR}/score_short_gpm_server"
  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_score "$ref" \
    --ds ds_score "$ds" \
    -s 65 \
    -o "$short_output_root" >/dev/null

  assert_package_metadata "${short_output_root}/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned" "65"
}

test_minimap_options_set_preset_and_threads() {
  local ref="${TMP_DIR}/ref-minimap.fa"
  local ds_a="${TMP_DIR}/ds-minimap-a.fa"
  local ds_b="${TMP_DIR}/ds-minimap-b.fa"
  local output_root="${TMP_DIR}/minimap_options_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAA"
  write_multi_fasta "$ds_a" "tig_a" "AAAAAAAAAA"
  write_multi_fasta "$ds_b" "tig_b" "CCCCCCCCCC"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_minimap "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --minimap-preset asm5 \
    --threads 12 \
    -o "$output_root" >/dev/null

  grep -F "minimap2 -x asm5 -t 12 -o result.paf" "${output_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected ds-vs-ref command to use asm5 and 12 threads" >&2
    cat "${output_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }

  cat > "${output_root}/runs/ds_a_vs_ref/result.paf" <<'EOF'
tig_a	10	0	6	+	Chr01	6	0	6	6	6	60
EOF
  cat > "${output_root}/runs/ds_b_vs_ref/result.paf" <<'EOF'
tig_b	10	0	6	+	Chr01	6	0	6	6	6	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/assign_chr_groups.sh" >/dev/null

  grep -F "minimap2 -x asm5 -X -t 12 -o result.paf" "${output_root}/runs/chr_Chr01/ds_a_vs_self/command.sh" >/dev/null || {
    echo "expected chr-local self command to use asm5, -X, and 12 threads" >&2
    cat "${output_root}/runs/chr_Chr01/ds_a_vs_self/command.sh" >&2
    exit 1
  }
  grep -F "minimap2 -x asm5 -t 12 -o result.paf" "${output_root}/runs/chr_Chr01/ds_a_vs_ds_b/command.sh" >/dev/null || {
    echo "expected chr-local pair command to use asm5 and 12 threads" >&2
    cat "${output_root}/runs/chr_Chr01/ds_a_vs_ds_b/command.sh" >&2
    exit 1
  }
}

test_alignment_engine_defaults_and_validation() {
  local ref="${TMP_DIR}/ref-aligner.fa"
  local ds="${TMP_DIR}/ds-aligner.fa"
  local default_root="${TMP_DIR}/aligner_default_gpm_server"
  local blastn_root="${TMP_DIR}/aligner_blastn_gpm_server"
  local winnowmap_root="${TMP_DIR}/aligner_winnowmap_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAA"
  write_multi_fasta "$ds" "tig_a" "AAAAAAAAAA"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    -o "$default_root" >/dev/null
  grep -F "minimap2 -x asm10 -t 10 -o result.paf" "${default_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected default minimap2 command to use 10 threads" >&2
    cat "${default_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  assert_prepare_option "${default_root}/metadata/prepare_options.tsv" alignment_engine minimap2
  assert_prepare_option "${default_root}/metadata/prepare_options.tsv" threads 10

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    --aligner blastn \
    -o "$blastn_root" >/dev/null
  grep -F "makeblastdb -in" "${blastn_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected blastn command to build a BLAST database" >&2
    cat "${blastn_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  grep -F "blastn -task blastn" "${blastn_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected blastn command to use default blastn task" >&2
    cat "${blastn_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  grep -F "blast6_to_paf.py" "${blastn_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected blastn command to convert blast6 to PAF" >&2
    cat "${blastn_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  assert_prepare_option "${blastn_root}/metadata/prepare_options.tsv" alignment_engine blastn

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    --aligner winnowmap \
    -o "$winnowmap_root" >/dev/null
  grep -F "meryl count k=19" "${winnowmap_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected winnowmap command to compute repetitive kmers" >&2
    cat "${winnowmap_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  grep -F "winnowmap -W repetitive_19_result.txt -x asm20 -t 10" "${winnowmap_root}/runs/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected winnowmap command to use default preset and threads" >&2
    cat "${winnowmap_root}/runs/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  assert_prepare_option "${winnowmap_root}/metadata/prepare_options.tsv" alignment_engine winnowmap

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    --aligner blastn \
    --minimap-preset asm5 \
    -o "${TMP_DIR}/invalid_blastn_gpm_server" >/dev/null 2>"${TMP_DIR}/invalid_blastn.err"; then
    echo "expected minimap option with blastn to fail" >&2
    exit 1
  fi
  grep -F -- "--minimap-preset is only valid with --aligner minimap2; selected aligner: blastn" "${TMP_DIR}/invalid_blastn.err" >/dev/null || {
    echo "expected invalid blastn option error" >&2
    cat "${TMP_DIR}/invalid_blastn.err" >&2
    exit 1
  }

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    --aligner minimap2 \
    --blastn-evalue 1e-20 \
    -o "${TMP_DIR}/invalid_minimap_gpm_server" >/dev/null 2>"${TMP_DIR}/invalid_minimap.err"; then
    echo "expected blastn option with minimap2 to fail" >&2
    exit 1
  fi
  grep -F -- "--blastn-evalue is only valid with --aligner blastn; selected aligner: minimap2" "${TMP_DIR}/invalid_minimap.err" >/dev/null || {
    echo "expected invalid minimap option error" >&2
    cat "${TMP_DIR}/invalid_minimap.err" >&2
    exit 1
  }

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    --aligner blastn \
    --winnowmap-kmer 21 \
    -o "${TMP_DIR}/invalid_winnowmap_gpm_server" >/dev/null 2>"${TMP_DIR}/invalid_winnowmap.err"; then
    echo "expected winnowmap option with blastn to fail" >&2
    exit 1
  fi
  grep -F -- "--winnowmap-kmer is only valid with --aligner winnowmap; selected aligner: blastn" "${TMP_DIR}/invalid_winnowmap.err" >/dev/null || {
    echo "expected invalid winnowmap option error" >&2
    cat "${TMP_DIR}/invalid_winnowmap.err" >&2
    exit 1
  }
}

test_out_alias_sets_output_root() {
  local ref="${TMP_DIR}/ref-out.fa"
  local ds="${TMP_DIR}/ds-out.fa"
  local output_root="${TMP_DIR}/out_alias_gpm_server"
  write_fasta "$ref" ref_out
  write_fasta "$ds" ds_out

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_out "$ref" \
    --ds ds_out "$ds" \
    --out "$output_root" >/dev/null

  assert_file "${output_root}/metadata/package.tsv"
  assert_file "${output_root}/run_all.sh"
}

assert_chr_partition_run_all_staging() {
  local run_all="$1"
  local output_root="$2"
  local chr_name="$3"
  local plan="${output_root}/.run_all/plan.tsv"

  bash -n "$run_all"
  grep -F '.prepare_lib/tools/run_all_runner.py' "$run_all" >/dev/null || {
    echo "run_all.sh does not invoke the generated runner" >&2
    exit 1
  }
  [[ -f "$plan" ]] || {
    echo "missing run_all execution plan: $plan" >&2
    exit 1
  }
  mapfile -t command_lines < <(tail -n +2 "$plan")
  [[ "${#command_lines[@]}" -eq 11 ]] || {
    echo "expected 11 staged plan units, got ${#command_lines[@]}" >&2
    if [[ "${#command_lines[@]}" -gt 0 ]]; then
      printf '%s\n' "${command_lines[@]}" >&2
    fi
    exit 1
  }

  [[ "${command_lines[0]}" == $'ref:ds_a\truns/ds_a_vs_ref/command.sh\truns/ds_a_vs_ref/stderr.log' ]] || {
    echo "unexpected first run_all plan unit" >&2
    printf '%s\n' "${command_lines[0]}" >&2
    exit 1
  }
  [[ "${command_lines[1]}" == $'ref:ds_b\truns/ds_b_vs_ref/command.sh\truns/ds_b_vs_ref/stderr.log' ]] || {
    echo "unexpected second run_all plan unit" >&2
    printf '%s\n' "${command_lines[1]}" >&2
    exit 1
  }
  local expected_tail
  expected_tail="$(cat <<EOF
assign	assign_chr_groups.sh	logs/run_all.log
grt_prepare	prepare_grt_inputs.sh	logs/run_all.log
grt_step1	run_grt_step1.sh	logs/run_all.log
grt_step23	run_grt_step23.sh	logs/run_all.log
grt_telomere_finalize	run_grt_telomere_finalize.sh	logs/run_all.log
chr:${chr_name}	runs/chr_${chr_name}/command.sh	logs/run_all.log
finalize_evidence	finalize_grt_evidence.sh	logs/run_all.log
package_full	package_full_zip.sh	logs/run_all.log
package_light	package_light_no_fasta_zip.sh	logs/run_all.log
EOF
)"
  [[ "$(printf '%s\n' "${command_lines[@]:2}")" == "$expected_tail" ]] || {
    echo "unexpected run_all plan tail" >&2
    printf '%s\n' "${command_lines[@]:2}" >&2
    exit 1
  }
  [[ -f "${output_root}/.prepare_lib/tools/run_all_runner.py" ]] || {
    echo "generated workspace is missing run_all_runner.py" >&2
    exit 1
  }
}

assert_tsv_has_self_alignment_flag() {
  local datasets_tsv="$1"
  local expected="$2"
  awk -F '\t' -v expected="$expected" '
    NR == 1 {
      for (i = 1; i <= NF; i++) {
        if ($i == "self_alignment_available") {
          flag_col = i
        }
      }
      if (!flag_col) {
        print "missing self_alignment_available column" > "/dev/stderr"
        exit 1
      }
      next
    }
    NF && $flag_col != expected {
      printf "expected self_alignment_available=%s, got %s on line %d\n", expected, $flag_col, NR > "/dev/stderr"
      exit 1
    }
  ' "$datasets_tsv"
}

assert_reference_segments_tsv() {
  local path="$1"
  assert_file "$path"
  local expected="${TMP_DIR}/expected_reference_segments.tsv"
  cat > "$expected" <<'EOF'
reference_chr_name	segment_order	segment_start_bp	segment_end_bp
Chr01	1	1	108
Chr01	2	209	211
Chr02	1	1	6
EOF
  diff -u "$expected" "$path"
}

assert_text_fasta_contents() {
  local path="$1"
  local expected="$2"
  assert_file "$path"
  local expected_path="${TMP_DIR}/expected.$(basename "$path")"
  printf '%s' "$expected" > "$expected_path"
  diff -u "$expected_path" "$path"
}

assert_chr_assignments_tsv() {
  local path="$1"
  local expected="${TMP_DIR}/expected_chr_assignments.tsv"
  cat > "$expected" <<'EOF'
dataset_name	seq_name	seq_length_bp	assigned_chr_name	source_orientation	orientation_source	support_bp	support_percent	anchor_start
ds_a	tig_multi	10	Chr01	+	ref_alignment	6	60.000	6
ds_a	tig_multi	10	Chr02	+	ref_alignment	6	60.000	15
ds_b	tig_chr1	10	Chr01	-	ref_alignment	7	70.000	6
EOF
  diff -u "$expected" "$path"
}

assert_reference_chr_locator_tsv() {
  local path="$1"
  local expected="${TMP_DIR}/expected_reference_chr_locator.tsv"
  cat > "$expected" <<'EOF'
reference_chr_name	fasta_relpath
Chr01	data/reference/chrs/Chr01.fa
Chr02	data/reference/chrs/Chr02.fa
EOF
  diff -u "$expected" "$path"
}

assert_source_seq_locator_tsv() {
  local path="$1"
  local expected="${TMP_DIR}/expected_source_seq_locator.tsv"
  cat > "$expected" <<'EOF'
dataset_name	seq_name	fasta_relpath
ds_a	tig_multi	data/partitions/chr/Chr01/ds_a.fa
ds_b	tig_chr1	data/partitions/chr/Chr01/ds_b.fa
ds_b	tig_unplaced	data/partitions/unplaced/ds_b.fa
EOF
  diff -u "$expected" "$path"
}

assert_zip_log_contains() {
  local log_path="$1"
  local expected="$2"
  local expected_escaped
  expected_escaped="$(printf '%q' "$expected")"
  grep -F -- "$expected" "$log_path" >/dev/null || grep -F -- "$expected_escaped" "$log_path" >/dev/null || {
    echo "expected zip command to contain: $expected" >&2
    echo "actual zip command:" >&2
    cat "$log_path" >&2
    exit 1
  }
}

assert_zip_log_not_contains() {
  local log_path="$1"
  local unexpected="$2"
  local unexpected_escaped
  unexpected_escaped="$(printf '%q' "$unexpected")"
  ! grep -F -- "$unexpected" "$log_path" >/dev/null && ! grep -F -- "$unexpected_escaped" "$log_path" >/dev/null || {
    echo "expected zip command not to contain: $unexpected" >&2
    echo "actual zip command:" >&2
    cat "$log_path" >&2
    exit 1
  }
}

test_custom_output_root() {
  local ref="${TMP_DIR}/ref.fa"
  local ds_a="${TMP_DIR}/ds-a.fa"
  local ds_b="${TMP_DIR}/ds-b.fa"
  local output_root="${TMP_DIR}/custom_gpm_server"
  write_fasta "$ref" ref
  write_fasta "$ds_a" ds_a
  write_fasta "$ds_b" ds_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    -o "$output_root" >/dev/null

  assert_dir "${output_root}/metadata"
  assert_file "${output_root}/metadata/reference.tsv"
  assert_file "${output_root}/metadata/package.tsv"
  assert_file "${output_root}/metadata/datasets.tsv"
  assert_file "${output_root}/run_all.sh"
  assert_file "${output_root}/export_final_path_fasta.sh"
  assert_file "${output_root}/.prepare_lib/lib/final_path.sh"
  assert_file "${output_root}/.prepare_lib/tools/add_dataset_package.py"
  assert_file "${output_root}/.prepare_lib/tools/grt_prepare_inputs.py"
  assert_file "${output_root}/.prepare_lib/tools/grt_step1.py"
  assert_file "${output_root}/.prepare_lib/tools/grt_step23.py"
  assert_file "${output_root}/.prepare_lib/tools/grt_telomere_finalize.py"
  assert_file "${output_root}/.prepare_lib/tools/grt_evidence_package.py"
  assert_file "${output_root}/.prepare_lib/contracts/grt_precomputed_v2.json"
  assert_file "${output_root}/prepare_grt_inputs.sh"
  assert_file "${output_root}/run_grt_step1.sh"
  assert_file "${output_root}/run_grt_step23.sh"
  assert_file "${output_root}/run_grt_telomere_finalize.sh"
  assert_file "${output_root}/finalize_grt_evidence.sh"
  assert_file "${output_root}/package_full_zip.sh"
  assert_file "${output_root}/package_light_no_fasta_zip.sh"
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref"
  assert_package_metadata "${output_root}/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned"
  assert_tsv_has_self_alignment_flag "${output_root}/metadata/datasets.tsv" "true"
}

test_removed_package_mode_flags_are_rejected() {
  local ref="${TMP_DIR}/ref-flags.fa"
  local ds="${TMP_DIR}/ds-flags.fa"
  write_fasta "$ref" ref_flags
  write_fasta "$ds" ds_flags

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_flags "$ref" \
    --ds ds_flags "$ds" \
    --global >/dev/null 2>"${TMP_DIR}/global.err"; then
    echo "expected --global to be rejected" >&2
    exit 1
  fi
  grep -q "Unknown argument: --global" "${TMP_DIR}/global.err" || {
    echo "expected --global unknown-argument error" >&2
    cat "${TMP_DIR}/global.err" >&2
    exit 1
  }

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_flags "$ref" \
    --ds ds_flags "$ds" \
    --fast >/dev/null 2>"${TMP_DIR}/fast.err"; then
    echo "expected --fast to be rejected" >&2
    exit 1
  fi
  grep -q "Unknown argument: --fast" "${TMP_DIR}/fast.err" || {
    echo "expected --fast unknown-argument error" >&2
    cat "${TMP_DIR}/fast.err" >&2
    exit 1
  }
}

test_removed_grt_tool_path_flags_are_rejected() {
  local ref="${TMP_DIR}/ref-grt-tool-flags.fa"
  local ds="${TMP_DIR}/ds-grt-tool-flags.fa"
  write_fasta "$ref" ref_grt_tool_flags
  write_fasta "$ds" ds_grt_tool_flags

  local option
  for option in \
    --grt-meryl \
    --grt-merqury \
    --grt-craq \
    --grt-minimap2 \
    --grt-nucmer \
    --grt-delta-filter \
    --grt-show-coords
  do
    local error_path="${TMP_DIR}/${option#--}.err"
    if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
      --ref ref_grt_tool_flags "$ref" \
      --ds ds_grt_tool_flags "$ds" \
      "$option" "${FAKE_BIN}/minimap2" \
      >/dev/null 2>"$error_path"; then
      echo "expected ${option} to be rejected" >&2
      exit 1
    fi
    grep -F "Unknown argument: ${option}" "$error_path" >/dev/null || {
      echo "expected ${option} unknown-argument error" >&2
      cat "$error_path" >&2
      exit 1
    }
  done
}

test_grt_tool_discovery_fails_fast_for_missing_commands() {
  local ref="${TMP_DIR}/ref-missing-grt-tools.fa"
  local ds="${TMP_DIR}/ds-missing-grt-tools.fa"
  local reads="${TMP_DIR}/reads-missing-grt-tools.fastq"
  write_fasta "$ref" ref_missing_grt_tools
  write_fasta "$ds" ds_missing_grt_tools
  printf 'reads\n' > "$reads"

  make_restricted_path() {
    local output_dir="$1"
    local missing_command="$2"
    mkdir -p "$output_dir"
    local command_name
    for command_name in bash dirname gzip python3; do
      ln -s "$(command -v "$command_name")" "${output_dir}/${command_name}"
    done
    for command_name in \
    samtools zip minimap2 nucmer delta-filter show-coords meryl merqury.sh craq
    do
      if [[ "$command_name" != "$missing_command" ]]; then
        ln -s "${FAKE_BIN}/${command_name}" "${output_dir}/${command_name}"
      fi
    done
  }

  local missing_base_bin="${TMP_DIR}/missing-show-coords-bin"
  make_restricted_path "$missing_base_bin" show-coords
  if PATH="$missing_base_bin" /bin/bash "$SCRIPT" \
    --ref ref_missing_grt_tools "$ref" \
    --ds ds_missing_grt_tools "$ds" \
    -o "${TMP_DIR}/missing-show-coords-output" \
    >/dev/null 2>"${TMP_DIR}/missing-show-coords.err"; then
    echo "expected missing show-coords to fail" >&2
    exit 1
  fi
  grep -F 'Required command not found in PATH: show-coords' \
    "${TMP_DIR}/missing-show-coords.err" >/dev/null || {
    echo "expected missing show-coords preflight error" >&2
    cat "${TMP_DIR}/missing-show-coords.err" >&2
    exit 1
  }

  local missing_qc_bin="${TMP_DIR}/missing-craq-bin"
  make_restricted_path "$missing_qc_bin" craq
  if PATH="$missing_qc_bin" /bin/bash "$SCRIPT" \
    --ref ref_missing_grt_qc "$ref" \
    --ds ds_missing_grt_qc "$ds" \
    --reads "$reads" \
    -o "${TMP_DIR}/missing-craq-output" \
    >/dev/null 2>"${TMP_DIR}/missing-craq.err"; then
    echo "expected missing craq with reads to fail" >&2
    exit 1
  fi
  grep -F 'Required command not found in PATH: craq' \
    "${TMP_DIR}/missing-craq.err" >/dev/null || {
    echo "expected missing craq preflight error" >&2
    cat "${TMP_DIR}/missing-craq.err" >&2
    exit 1
  }
}

test_default_output_root_uses_current_working_directory() {
  local upload_root="${TMP_DIR}/upload"
  local ref="${TMP_DIR}/ref-default.fa"
  local ds="${TMP_DIR}/ds-default.fa"
  mkdir -p "$upload_root"
  cp -R "${REPO_ROOT}/server" "${upload_root}/server"
  write_fasta "$ref" ref_default
  write_fasta "$ds" ds_default

  (
    cd "$TMP_DIR"
    PATH="${FAKE_BIN}:$PATH" bash "${upload_root}/server/prepare.sh" \
      --ref ref_default "$ref" \
      --ds ds_default "$ds" >/dev/null
  )

  assert_file "${TMP_DIR}/gpm_server/metadata/reference.tsv"
  assert_file "${TMP_DIR}/gpm_server/run_all.sh"
  assert_file "${TMP_DIR}/gpm_server/export_final_path_fasta.sh"
  assert_file "${TMP_DIR}/gpm_server/.prepare_lib/lib/final_path.sh"
  assert_file "${TMP_DIR}/gpm_server/.prepare_lib/tools/add_dataset_package.py"
}

test_skip_self_option_omits_self_runs() {
  local ref="${TMP_DIR}/ref-skip.fa"
  local ds_a="${TMP_DIR}/ds-skip-a.fa"
  local ds_b="${TMP_DIR}/ds-skip-b.fa"
  local output_root="${TMP_DIR}/skip_self_gpm_server"
  write_fasta "$ref" ref_skip
  write_fasta "$ds_a" ds_skip_a
  write_fasta "$ds_b" ds_skip_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_skip "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --skip-self \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/run_all.sh"
  [[ ! -d "${output_root}/runs/ds_a_vs_self" ]] || {
    echo "expected --skip-self not to create ds_a_vs_self" >&2
    exit 1
  }
  [[ ! -d "${output_root}/runs/ds_b_vs_self" ]] || {
    echo "expected --skip-self not to create ds_b_vs_self" >&2
    exit 1
  }
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref_skip"
  assert_package_metadata "${output_root}/metadata/package.tsv" "fast" "true" "none" "chr_partition" "partitioned"
  assert_tsv_has_self_alignment_flag "${output_root}/metadata/datasets.tsv" "false"
}

test_prepare_writes_package_metadata_and_stages_runs() {
  local ref="${TMP_DIR}/ref-partitioned.fa"
  local ds_a="${TMP_DIR}/ds-fast-a.fa"
  local ds_b="${TMP_DIR}/ds-fast-b.fa"
  local output_root="${TMP_DIR}/partitioned_gpm_server"
  write_fasta "$ref" ref_partitioned
  write_fasta "$ds_a" ds_a
  write_fasta "$ds_b" ds_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_partitioned "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/metadata/package.tsv"
  [[ ! -f "${output_root}/metadata/chr_assignments.tsv" ]] || {
    echo "expected prepare not to precompute metadata/chr_assignments.tsv" >&2
    exit 1
  }
  assert_file "${output_root}/assign_chr_groups.sh"
  assert_file "${output_root}/runs/chr_ref_partitioned/command.sh"
  assert_package_metadata "${output_root}/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned"
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref_partitioned"
}

test_prepare_rejects_reference_without_sequences() {
  local ref="${TMP_DIR}/ref-empty.fa"
  local ds="${TMP_DIR}/ds-empty-ref.fa"
  local output_root="${TMP_DIR}/empty_ref_gpm_server"
  : > "$ref"
  write_fasta "$ds" ds_empty_ref

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_empty "$ref" \
    --ds ds_empty_ref "$ds" \
    -o "$output_root" >/dev/null 2>"${TMP_DIR}/empty_ref.err"; then
    echo "expected empty reference FASTA to fail" >&2
    exit 1
  fi
  grep -F "Reference FASTA contains no sequence records:" \
    "${TMP_DIR}/empty_ref.err" >/dev/null || {
    echo "expected empty reference FASTA domain error" >&2
    cat "${TMP_DIR}/empty_ref.err" >&2
    exit 1
  }
  if grep -F "unbound variable" "${TMP_DIR}/empty_ref.err" >/dev/null; then
    echo "empty reference validation leaked a nounset error" >&2
    cat "${TMP_DIR}/empty_ref.err" >&2
    exit 1
  fi
}

test_assignment_helper_generates_chr_assignments_and_chr_local_runs() {
  local ref="${TMP_DIR}/ref-partitioned-assign.fa"
  local ds_a="${TMP_DIR}/ds-fast-assign-a.fa"
  local ds_b="${TMP_DIR}/ds-fast-assign-b.fa"
  local output_root="${TMP_DIR}/assign_gpm_server"
  write_multi_fasta "$ref" \
    "Chr01" "AAAAAA" \
    "Chr02" "CCCCCC"
  write_multi_fasta "$ds_a" "tig_multi" "AAAAAAAAAA"
  write_multi_fasta "$ds_b" \
    "tig_chr1" "CCNNCCCCCC" \
    "tig_unplaced" "TTNNNNTTTT"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_partitioned_assign "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    -o "$output_root" >/dev/null

  cat > "${output_root}/runs/ds_a_vs_ref/result.paf" <<'EOF'
tig_multi	10	0	4	+	Chr01	30	4	8	4	4	60
tig_multi	10	2	6	-	Chr01	30	9	13	4	4	60
tig_multi	10	0	6	+	Chr02	30	14	20	6	6	60
EOF
  cat > "${output_root}/runs/ds_b_vs_ref/result.paf" <<'EOF'
tig_chr1	10	1	8	-	Chr01	30	7	14	7	7	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/assign_chr_groups.sh" >/dev/null

  assert_file "${output_root}/metadata/chr_assignments.tsv"
  assert_chr_assignments_tsv "${output_root}/metadata/chr_assignments.tsv"
  assert_file "${output_root}/metadata/reference_chr_locator.tsv"
  assert_file "${output_root}/metadata/source_seq_locator.tsv"
  assert_file "${output_root}/metadata/source_seq_n_regions.tsv"
  assert_reference_chr_locator_tsv "${output_root}/metadata/reference_chr_locator.tsv"
  assert_source_seq_locator_tsv "${output_root}/metadata/source_seq_locator.tsv"
  grep -F $'ds_b\ttig_chr1\t3\t4\t2' "${output_root}/metadata/source_seq_n_regions.tsv" >/dev/null || {
    echo "expected assigned tig_chr1 N region to be scanned" >&2
    cat "${output_root}/metadata/source_seq_n_regions.tsv" >&2
    exit 1
  }
  ! grep -F $'ds_b\ttig_unplaced\t3\t6\t4' "${output_root}/metadata/source_seq_n_regions.tsv" >/dev/null || {
    echo "expected unplaced tig_unplaced N region not to be scanned" >&2
    cat "${output_root}/metadata/source_seq_n_regions.tsv" >&2
    exit 1
  }
  assert_text_fasta_contents "${output_root}/data/reference/chrs/Chr01.fa" $'>Chr01\nAAAAAA\n'
  assert_text_fasta_contents "${output_root}/data/reference/chrs/Chr02.fa" $'>Chr02\nCCCCCC\n'
  assert_text_fasta_contents "${output_root}/data/partitions/chr/Chr01/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/data/partitions/chr/Chr01/ds_b.fa" $'>tig_chr1\nCCNNCCCCCC\n'
  assert_text_fasta_contents "${output_root}/data/partitions/chr/Chr02/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/data/partitions/unplaced/ds_b.fa" $'>tig_unplaced\nTTNNNNTTTT\n'
  assert_text_fasta_contents "${output_root}/runs/chr_Chr01/datasets/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/runs/chr_Chr01/datasets/ds_b.fa" $'>tig_chr1\nCCNNCCCCCC\n'
  assert_text_fasta_contents "${output_root}/runs/chr_Chr02/datasets/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  [[ ! -f "${output_root}/runs/chr_Chr02/datasets/ds_b.fa" ]] || {
    echo "expected chr_Chr02 not to include ds_b" >&2
    exit 1
  }
  assert_file "${output_root}/runs/chr_Chr01/generated_command.sh"
  assert_file "${output_root}/runs/chr_Chr01/ds_a_vs_self/command.sh"
  assert_file "${output_root}/runs/chr_Chr01/ds_b_vs_self/command.sh"
  assert_file "${output_root}/runs/chr_Chr01/ds_a_vs_ds_b/command.sh"
  assert_file "${output_root}/runs/chr_Chr02/generated_command.sh"
  assert_file "${output_root}/runs/chr_Chr02/ds_a_vs_self/command.sh"
  [[ ! -d "${output_root}/runs/chr_Chr02/ds_a_vs_ds_b" ]] || {
    echo "expected chr_Chr02 not to include cross-dataset run" >&2
    exit 1
  }

  if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/package_full_zip.sh" \
      >"${TMP_DIR}/premature-package.out" 2>"${TMP_DIR}/premature-package.err"; then
    echo "expected packaging before GRT finalization to fail" >&2
    exit 1
  fi
  grep -q "MISSING_REQUIRED_FILE" "${TMP_DIR}/premature-package.err" || {
    echo "expected package preflight to report the incomplete GRT contract" >&2
    cat "${TMP_DIR}/premature-package.err" >&2
    exit 1
  }
}

test_reads_lock_qc_recipe_and_generated_command() {
  local ref="${TMP_DIR}/ref-grt-reads.fa"
  local ds_a="${TMP_DIR}/ds-grt-reads-a.fa"
  local ds_b="${TMP_DIR}/ds-grt-reads-b.fa"
  local reads_a="${TMP_DIR}/reads-a.fastq.gz"
  local reads_b="${TMP_DIR}/reads-b.fastq.gz"
  local output_root="${TMP_DIR}/reads_gpm_server"
  write_fasta "$ref" Chr01
  write_fasta "$ds_a" primary_ctg
  write_fasta "$ds_b" support_ctg
  printf 'reads-a\n' > "$reads_a"
  printf 'reads-b\n' > "$reads_b"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_grt_reads "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --reads "$reads_a" \
    --reads "$reads_b" \
    --grt-qc-memory-gb 96 \
    --grt-kmer-size 31 \
    -o "$output_root" >/dev/null

  awk -F '\t' '
    NR == 1 { for (i = 1; i <= NF; i++) column[$i] = i; next }
    NR == 2 { exit ($(column["reads_qc_enabled"]) == "true" ? 0 : 1) }
  ' "${output_root}/metadata/package.tsv"
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_primary_dataset ds_a
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_reads_qc_enabled true
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_meryl "${FAKE_BIN}/meryl"
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_merqury "${FAKE_BIN}/merqury.sh"
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_craq "${FAKE_BIN}/craq"
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_qc_memory_gb 96
  assert_prepare_option "${output_root}/metadata/prepare_options.tsv" grt_kmer_size 31
  grep -F -- "--reads ${reads_a}" "${output_root}/prepare_grt_inputs.sh" >/dev/null
  grep -F -- "--reads ${reads_b}" "${output_root}/prepare_grt_inputs.sh" >/dev/null
  grep -F -- "--memory-gb 96 --kmer-size 31" "${output_root}/prepare_grt_inputs.sh" >/dev/null
  grep -F -- "--meryl ${FAKE_BIN}/meryl --merqury ${FAKE_BIN}/merqury.sh --craq ${FAKE_BIN}/craq" \
    "${output_root}/prepare_grt_inputs.sh" >/dev/null
}

test_skip_self_omits_chr_local_self_runs() {
  local ref="${TMP_DIR}/ref-partitioned-skip.fa"
  local ds_a="${TMP_DIR}/ds-fast-skip-a.fa"
  local ds_b="${TMP_DIR}/ds-fast-skip-b.fa"
  local output_root="${TMP_DIR}/skip_assign_gpm_server"
  write_multi_fasta "$ref" \
    "Chr01" "AAAAAA" \
    "Chr02" "CCCCCC"
  write_multi_fasta "$ds_a" "tig_multi" "AAAAAAAAAA"
  write_multi_fasta "$ds_b" "tig_chr1" "CCCCCCCCCC"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_partitioned_skip "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --skip-self \
    -o "$output_root" >/dev/null

  cat > "${output_root}/runs/ds_a_vs_ref/result.paf" <<'EOF'
tig_multi	10	0	6	+	Chr01	30	4	10	6	6	60
EOF
  cat > "${output_root}/runs/ds_b_vs_ref/result.paf" <<'EOF'
tig_chr1	10	1	8	+	Chr01	30	7	14	7	7	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/assign_chr_groups.sh" >/dev/null

  assert_file "${output_root}/runs/chr_Chr01/generated_command.sh"
  assert_file "${output_root}/runs/chr_Chr01/ds_a_vs_ds_b/command.sh"
  [[ ! -d "${output_root}/runs/chr_Chr01/ds_a_vs_self" ]] || {
    echo "expected --skip-self to suppress chr-local ds_a_vs_self" >&2
    exit 1
  }
  [[ ! -d "${output_root}/runs/chr_Chr01/ds_b_vs_self" ]] || {
    echo "expected --skip-self to suppress chr-local ds_b_vs_self" >&2
    exit 1
  }
  ! grep -q '_vs_self' "${output_root}/runs/chr_Chr01/generated_command.sh" || {
    echo "expected generated chr command not to contain self runs when --skip-self is set" >&2
    exit 1
  }
}

test_prepare_writes_reference_segments_metadata() {
  local ref="${TMP_DIR}/ref-gap.fa"
  local ds="${TMP_DIR}/ds-gap.fa"
  local output_root="${TMP_DIR}/gap_gpm_server"
  write_gap_ref_partitioneda "$ref"
  write_fasta "$ds" ds_gap

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_gap "$ref" \
    --ds ds_gap "$ds" \
    -o "$output_root" >/dev/null

  assert_reference_segments_tsv "${output_root}/metadata/reference_segments.tsv"
}

test_prepare_normalizes_plain_fna_inputs_to_package_fa() {
  local ref="${TMP_DIR}/ref-input.fna"
  local ds="${TMP_DIR}/ds-input.fna"
  local output_root="${TMP_DIR}/fna_gpm_server"
  local expected_ref=$'>ref_from_fna\nACGT\n'
  local expected_ds=$'>ds_from_fna\nACGT\n'
  printf '%s' "$expected_ref" > "$ref"
  printf '%s' "$expected_ds" > "$ds"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_from_fna "$ref" \
    --ds ds_from_fna "$ds" \
    -o "$output_root" >/dev/null

  assert_text_fasta_contents "${output_root}/data/reference/ref_from_fna.fa" "$expected_ref"
  assert_text_fasta_contents "${output_root}/data/datasets/ds_from_fna.fa" "$expected_ds"
}

test_prepare_decompresses_gzip_inputs_to_package_fa() {
  local ref_plain="${TMP_DIR}/ref-input.fa"
  local ds_plain="${TMP_DIR}/ds-input.fna"
  local ref_gz="${TMP_DIR}/ref-input.fa.gz"
  local ds_gz="${TMP_DIR}/ds-input.fna.gz"
  local output_root="${TMP_DIR}/gz_gpm_server"
  local expected_ref=$'>ref_from_gz\nACGT\n'
  local expected_ds=$'>ds_from_gz\nACGT\n'
  printf '%s' "$expected_ref" > "$ref_plain"
  printf '%s' "$expected_ds" > "$ds_plain"
  gzip_copy "$ref_plain" "$ref_gz"
  gzip_copy "$ds_plain" "$ds_gz"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_from_gz "$ref_gz" \
    --ds ds_from_gz "$ds_gz" \
    -o "$output_root" >/dev/null

  assert_text_fasta_contents "${output_root}/data/reference/ref_from_gz.fa" "$expected_ref"
  assert_text_fasta_contents "${output_root}/data/datasets/ds_from_gz.fa" "$expected_ds"
}

test_tel_options_generate_chr_local_tel_marks() {
  local ref="${TMP_DIR}/ref-tel.fa"
  local ds="${TMP_DIR}/ds-tel.fa"
  local output_root="${TMP_DIR}/tel_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  python3 - <<'PY' > "$ds"
print(">tig_tel")
print("AA" + "TTAGGG" * 20 + "CC" + "CCCTAA" * 20 + "GG")
PY

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_tel "$ref" \
    --ds ds_a "$ds" \
    --tel TTAGGG 20 \
    --tel TTTAGGG 10 \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/tel/rules.tsv"
  grep -F $'tel1\tTTAGGG\t20\ttrue' "${output_root}/tel/rules.tsv" >/dev/null || {
    echo "expected TTAGGG tel rule" >&2
    cat "${output_root}/tel/rules.tsv" >&2
    exit 1
  }
  grep -F $'tel2\tTTTAGGG\t10\ttrue' "${output_root}/tel/rules.tsv" >/dev/null || {
    echo "expected TTTAGGG tel rule" >&2
    cat "${output_root}/tel/rules.tsv" >&2
    exit 1
  }

  cat > "${output_root}/runs/ds_a_vs_ref/result.paf" <<'EOF'
tig_tel	248	0	200	+	Chr01	1000	1	201	200	200	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/assign_chr_groups.sh" >/dev/null
  assert_file "${output_root}/runs/chr_Chr01/tel_scan/command.sh"
  assert_file "${output_root}/runs/chr_Chr01/generated_command.sh"
  grep -F 'tel_scan/command.sh' "${output_root}/runs/chr_Chr01/generated_command.sh" >/dev/null || {
    echo "expected generated chr command to include tel scan" >&2
    cat "${output_root}/runs/chr_Chr01/generated_command.sh" >&2
    exit 1
  }

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/runs/chr_Chr01/command.sh" >/dev/null
  assert_file "${output_root}/tel/chr_Chr01/ds_a.tsv"
  grep -F $'tel1\tds_a\ttig_tel\tChr01\tTTAGGG\t20\t20\t3\t122\t+' "${output_root}/tel/chr_Chr01/ds_a.tsv" >/dev/null || {
    echo "expected forward TTAGGG tel mark" >&2
    cat "${output_root}/tel/chr_Chr01/ds_a.tsv" >&2
    exit 1
  }
  grep -F $'tel1\tds_a\ttig_tel\tChr01\tTTAGGG\t20\t20\t125\t244\t-' "${output_root}/tel/chr_Chr01/ds_a.tsv" >/dev/null || {
    echo "expected reverse-complement TTAGGG tel mark" >&2
    cat "${output_root}/tel/chr_Chr01/ds_a.tsv" >&2
    exit 1
  }
}

test_cen_option_generates_chr_local_cen_marks() {
  local ref="${TMP_DIR}/ref-cen.fa"
  local cen="${TMP_DIR}/ref-cen-regions.fa"
  local ds="${TMP_DIR}/ds-cen.fa"
  local output_root="${TMP_DIR}/cen_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  write_multi_fasta "$cen" "Chr01_centromere" "AAAAAAAAAAAAAAAAAAAA"
  write_multi_fasta "$ds" "tig_cen" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_cen "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    --cen-min-len 5 \
    --cen-min-identity 80 \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/cen/reference.tsv"
  grep -F $'cen\tChr01\tChr01_centromere\tdata/centromere/ref_cen_regions.fa\t5\t80' "${output_root}/cen/reference.tsv" >/dev/null || {
    echo "expected Chr01 cen reference row" >&2
    cat "${output_root}/cen/reference.tsv" >&2
    exit 1
  }

  cat > "${output_root}/runs/ds_a_vs_ref/result.paf" <<'EOF'
tig_cen	40	0	40	+	Chr01	1000	1	41	40	40	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/assign_chr_groups.sh" >/dev/null
  assert_file "${output_root}/runs/chr_Chr01/cen_scan/command.sh"
  grep -F 'cen_scan/command.sh' "${output_root}/runs/chr_Chr01/generated_command.sh" >/dev/null || {
    echo "expected generated chr command to include cen scan" >&2
    cat "${output_root}/runs/chr_Chr01/generated_command.sh" >&2
    exit 1
  }
  grep -F 'minimap2 -x asm10 -t 10 -c --cs -o result.paf' "${output_root}/runs/chr_Chr01/cen_scan/command.sh" >/dev/null || {
    echo "expected cen scan minimap2 command with cs/cigar output" >&2
    cat "${output_root}/runs/chr_Chr01/cen_scan/command.sh" >&2
    exit 1
  }

  cat > "${output_root}/runs/chr_Chr01/cen_scan/result.paf" <<'EOF'
Chr01_centromere	20	0	20	+	tig_cen	40	5	25	18	20	60	dv:f:0.0500
EOF
  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/runs/chr_Chr01/cen_scan/command.sh" >/dev/null

  assert_file "${output_root}/cen/chr_Chr01/marks.tsv"
  grep -F $'cen\tChr01\tChr01_centromere\tds_a\ttig_cen\t6\t25\t+\t20\t95.000\t60' "${output_root}/cen/chr_Chr01/marks.tsv" >/dev/null || {
    echo "expected accepted cen mark" >&2
    cat "${output_root}/cen/chr_Chr01/marks.tsv" >&2
    exit 1
  }
}

test_cen_rejects_duplicate_chr_headers() {
  local ref="${TMP_DIR}/ref-cen-dup.fa"
  local cen="${TMP_DIR}/ref-cen-dup-regions.fa"
  local ds="${TMP_DIR}/ds-cen-dup.fa"
  local output_root="${TMP_DIR}/cen_dup_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  write_multi_fasta "$cen" "Chr01_centromere" "AAAAAAAAAA" "Chr01_centromere" "CCCCCCCCCC"
  write_multi_fasta "$ds" "tig_cen" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_cen_dup "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    -o "$output_root" >/dev/null 2>"${TMP_DIR}/cen_dup.err"; then
    echo "expected duplicate cen chr headers to fail" >&2
    exit 1
  fi
  grep -F 'Duplicate --cen chromosome entry: Chr01' "${TMP_DIR}/cen_dup.err" >/dev/null || {
    echo "expected duplicate cen chr error" >&2
    cat "${TMP_DIR}/cen_dup.err" >&2
    exit 1
  }
}

test_cen_rejects_unknown_reference_chr() {
  local ref="${TMP_DIR}/ref-cen-missing.fa"
  local cen="${TMP_DIR}/ref-cen-missing-regions.fa"
  local ds="${TMP_DIR}/ds-cen-missing.fa"
  local output_root="${TMP_DIR}/cen_missing_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  write_multi_fasta "$cen" "Chr99_centromere" "AAAAAAAAAA"
  write_multi_fasta "$ds" "tig_cen" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" \
    --ref ref_cen_missing "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    -o "$output_root" >/dev/null 2>"${TMP_DIR}/cen_missing.err"; then
    echo "expected missing cen chr to fail" >&2
    exit 1
  fi
  grep -F 'Unknown --cen chromosome entry: Chr99' "${TMP_DIR}/cen_missing.err" >/dev/null || {
    echo "expected unknown cen chr error" >&2
    cat "${TMP_DIR}/cen_missing.err" >&2
    exit 1
  }
}

test_custom_output_root
test_default_output_root_uses_current_working_directory
test_removed_package_mode_flags_are_rejected
test_removed_grt_tool_path_flags_are_rejected
test_grt_tool_discovery_fails_fast_for_missing_commands
test_score_option_sets_chr_assignment_threshold
test_minimap_options_set_preset_and_threads
test_alignment_engine_defaults_and_validation
test_out_alias_sets_output_root
test_skip_self_option_omits_self_runs
test_prepare_writes_reference_segments_metadata
test_prepare_normalizes_plain_fna_inputs_to_package_fa
test_prepare_decompresses_gzip_inputs_to_package_fa
test_tel_options_generate_chr_local_tel_marks
test_cen_option_generates_chr_local_cen_marks
test_cen_rejects_duplicate_chr_headers
test_cen_rejects_unknown_reference_chr
test_prepare_writes_package_metadata_and_stages_runs
test_prepare_rejects_reference_without_sequences
test_assignment_helper_generates_chr_assignments_and_chr_local_runs
test_reads_lock_qc_recipe_and_generated_command
test_skip_self_omits_chr_local_self_runs

echo "prepare_full_test.sh: ok"
