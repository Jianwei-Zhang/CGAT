#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/server/prepare.sh"
PREPARE_BASH="$(command -v "${GPM_TEST_BASH:-bash}")" || {
  echo "prepare test Bash not found: ${GPM_TEST_BASH:-bash}" >&2
  exit 1
}

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
exit 0
EOF

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/makeblastdb" "${FAKE_BIN}/blastn" "${FAKE_BIN}/meryl" "${FAKE_BIN}/winnowmap" "${FAKE_BIN}/zip" \
  "${FAKE_BIN}/nucmer" "${FAKE_BIN}/delta-filter" "${FAKE_BIN}/show-coords" "${FAKE_BIN}/merqury.sh" "${FAKE_BIN}/craq"

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

make_restricted_path() {
  local output_dir="$1"
  local missing_command="$2"
  mkdir -p "$output_dir"
  local command_name
  for command_name in awk basename bash cat chmod cp dirname find gzip mkdir python3 rm sed; do
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

(
  cd "$TMP_DIR"
  PATH="${FAKE_BIN}:$PATH" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_add_options "$ref" \
    --ds ds_add "$ds" \
    --skip-self \
    --score 71 \
    --minimap-preset asm5 \
    --tel TTAGGG 2 \
    --cen "$cen" \
    -o "$output_root" >/dev/null
)

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
assert_prepare_option "$metadata_path" grt_reads_qc_enabled false
! grep -F -- " --reads " "${output_root}/prepare_grt_inputs.sh" >/dev/null || {
  echo "no-reads prepare generated an unexpected --reads argument" >&2
  exit 1
}

plan_path="${output_root}/.run_all/plan.tsv"
[[ -f "$plan_path" ]] || {
  echo "expected generated run_all plan: $plan_path" >&2
  exit 1
}
grep -F $'unit_id\tcommand_relpath\tdetail_log_relpath' "$plan_path" >/dev/null
[[ "$(tail -n +2 "$plan_path" | wc -l)" -eq 10 ]] || {
  echo "expected 10 units in generated run_all plan" >&2
  exit 1
}
expected_plan="$(cat <<'EOF'
unit_id	command_relpath	detail_log_relpath
ref:ds_add	runs/ds_add_vs_ref/command.sh	runs/ds_add_vs_ref/stderr.log
assign	assign_chr_groups.sh	logs/run_all.log
grt_prepare	prepare_grt_inputs.sh	logs/run_all.log
grt_step1	run_grt_step1.sh	logs/run_all.log
grt_step23	run_grt_step23.sh	logs/run_all.log
grt_telomere_finalize	run_grt_telomere_finalize.sh	logs/run_all.log
chr:Chr01	runs/chr_Chr01/command.sh	logs/run_all.log
finalize_evidence	finalize_grt_evidence.sh	logs/run_all.log
package_full	package_full_zip.sh	logs/run_all.log
package_light	package_light_no_fasta_zip.sh	logs/run_all.log
EOF
)"
[[ "$(cat "$plan_path")" == "$expected_plan" ]] || {
  echo "generated run_all plan does not match canonical order" >&2
  cat "$plan_path" >&2
  exit 1
}
grep -F -- '.prepare_lib/tools/run_all_runner.py' "${output_root}/run_all.sh" >/dev/null
! grep -q '^bash ' "${output_root}/run_all.sh" || {
  echo "generated run_all.sh still contains a static bash chain" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/tools/run_all_runner.py" ]] || {
  echo "generated workspace is missing run_all_runner.py" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/tools/reference_segments.py" ]] || {
  echo "generated workspace is missing reference_segments.py" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/lib/incremental_common.sh" ]] || {
  echo "generated workspace is missing incremental shell helpers" >&2
  exit 1
}
for tool_name in \
  add_dataset_stage.py \
  assign_chr_groups.py \
  cen_reference_metadata.py \
  promote_server_stage.py \
  render_template.py \
  validate_add_dataset_stage.py; do
  [[ -f "${output_root}/.prepare_lib/tools/${tool_name}" ]] || {
    echo "generated workspace is missing ${tool_name}" >&2
    exit 1
  }
done
cmp "${REPO_ROOT}/server/templates/add_dataset.sh" "${output_root}/add_dataset.sh"
cmp "${REPO_ROOT}/server/templates/add_ctg.sh" "${output_root}/add_ctg.sh"
bash -n "${output_root}/add_dataset.sh"
bash -n "${output_root}/add_ctg.sh"
grep -F -- '.prepare_lib/tools/assign_chr_groups.py' "${output_root}/assign_chr_groups.sh" >/dev/null
! grep -Eq '__[A-Z][A-Z0-9_]*__' "${output_root}/assign_chr_groups.sh" || {
  echo "generated assignment script contains an unresolved template variable" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/tools/grt_core/__init__.py" ]] || {
  echo "generated workspace is missing the recursive grt_core package" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/tools/grt_core/stage_replay.py" ]] || {
  echo "generated workspace is missing grt_core stage services" >&2
  exit 1
}
[[ -f "${output_root}/.prepare_lib/tools/grt_core/contract/validator.py" ]] || {
  echo "generated workspace is missing the recursive grt_core contract package" >&2
  exit 1
}
python3 "${output_root}/.prepare_lib/tools/grt_prepare_inputs.py" --help >/dev/null
python3 "${output_root}/.prepare_lib/tools/grt_step1.py" --help >/dev/null
python3 "${output_root}/.prepare_lib/tools/grt_step23.py" --help >/dev/null
python3 "${output_root}/.prepare_lib/tools/grt_telomere_finalize.py" --help >/dev/null
python3 "${output_root}/.prepare_lib/tools/grt_evidence_package.py" --help >/dev/null
python3 "${output_root}/.prepare_lib/tools/grt_contract.py" --help >/dev/null

grep -F -- "--minimap2 ${FAKE_BIN}/minimap2" "${output_root}/run_grt_step1.sh" >/dev/null
grep -F -- "--minimap2 ${FAKE_BIN}/minimap2 --nucmer ${FAKE_BIN}/nucmer --delta-filter ${FAKE_BIN}/delta-filter --show-coords ${FAKE_BIN}/show-coords" \
  "${output_root}/run_grt_step23.sh" >/dev/null

no_chmod_bin="${TMP_DIR}/no-chmod-bin"
no_chmod_log="${TMP_DIR}/no-chmod.log"
no_chmod_output="${TMP_DIR}/no-chmod-gpm_server"
mkdir -p "$no_chmod_bin"
cat > "${no_chmod_bin}/chmod" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${GPM_TEST_CHMOD_LOG:?}"
exit 1
EOF
chmod +x "${no_chmod_bin}/chmod"

GPM_TEST_CHMOD_LOG="$no_chmod_log" PATH="${no_chmod_bin}:${FAKE_BIN}:$PATH" \
  "$PREPARE_BASH" "$SCRIPT" \
  --ref ref_no_chmod "$ref" \
  --ds ds_no_chmod "$ds" \
  --skip-self \
  -o "$no_chmod_output" >/dev/null

[[ -s "$no_chmod_log" ]] || {
  echo "expected prepare to attempt best-effort executable-bit updates" >&2
  exit 1
}
[[ ! -x "${no_chmod_output}/run_all.sh" ]] || {
  echo "run_all.sh unexpectedly became executable through failing chmod" >&2
  exit 1
}
bash "${no_chmod_output}/run_all.sh" --help >/dev/null
while IFS= read -r generated_script; do
  bash -n "$generated_script"
done < <(find "$no_chmod_output" -type f -name '*.sh' | LC_ALL=C sort)
! grep -q '\.chmod(0o755)' "$SCRIPT" || {
  echo "prepare.sh still embeds mandatory Python chmod calls" >&2
  exit 1
}
! grep -q '\.chmod(0o755)' "${REPO_ROOT}/server/tools/add_ctg_stage.py" || {
  echo "add_ctg_stage.py still requires generated command scripts to be executable" >&2
  exit 1
}

help_output="$("$PREPARE_BASH" "$SCRIPT" --help)"
for removed_option in \
  --grt-meryl \
  --grt-merqury \
  --grt-craq \
  --grt-minimap2 \
  --grt-nucmer \
  --grt-delta-filter \
  --grt-show-coords
do
  if grep -F -- "$removed_option" <<<"$help_output" >/dev/null; then
    echo "prepare.sh --help still advertises removed option: ${removed_option}" >&2
    exit 1
  fi
  error_path="${TMP_DIR}/${removed_option#--}.err"
  if PATH="${FAKE_BIN}:$PATH" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_removed_grt_option "$ref" \
    --ds ds_removed_grt_option "$ds" \
    "$removed_option" "${FAKE_BIN}/minimap2" \
    >/dev/null 2>"$error_path"; then
    echo "expected removed option to fail: ${removed_option}" >&2
    exit 1
  fi
  grep -F "Unknown argument: ${removed_option}" "$error_path" >/dev/null || {
    echo "expected unknown-argument error for ${removed_option}" >&2
    cat "$error_path" >&2
    exit 1
  }
done

reads="${TMP_DIR}/reads.fastq"
reads_output_root="${TMP_DIR}/reads_gpm_server"
printf 'reads\n' > "$reads"
PATH="${FAKE_BIN}:$PATH" "$PREPARE_BASH" "$SCRIPT" \
  --ref ref_reads_qc "$ref" \
  --ds ds_reads_qc "$ds" \
  --reads "$reads" \
  -o "$reads_output_root" >/dev/null
reads_metadata_path="${reads_output_root}/metadata/prepare_options.tsv"
assert_prepare_option "$reads_metadata_path" grt_reads_qc_enabled true
assert_prepare_option "$reads_metadata_path" grt_meryl "${FAKE_BIN}/meryl"
assert_prepare_option "$reads_metadata_path" grt_merqury "${FAKE_BIN}/merqury.sh"
assert_prepare_option "$reads_metadata_path" grt_craq "${FAKE_BIN}/craq"
grep -F -- "--meryl ${FAKE_BIN}/meryl --merqury ${FAKE_BIN}/merqury.sh --craq ${FAKE_BIN}/craq" \
  "${reads_output_root}/prepare_grt_inputs.sh" >/dev/null
grep -F -- " --reads ${reads}" "${reads_output_root}/prepare_grt_inputs.sh" >/dev/null
[[ "$(grep -oF -- " --reads " "${reads_output_root}/prepare_grt_inputs.sh" | wc -l)" -eq 1 ]] || {
  echo "single-read prepare did not generate exactly one --reads argument" >&2
  exit 1
}

reads_second="${TMP_DIR}/reads-second.fastq"
multiple_reads_output_root="${TMP_DIR}/multiple-reads-gpm-server"
printf 'reads-second\n' > "$reads_second"
PATH="${FAKE_BIN}:$PATH" "$PREPARE_BASH" "$SCRIPT" \
  --ref ref_multiple_reads_qc "$ref" \
  --ds ds_multiple_reads_qc "$ds" \
  --reads "$reads" \
  --reads "$reads_second" \
  -o "$multiple_reads_output_root" >/dev/null
assert_prepare_option \
  "${multiple_reads_output_root}/metadata/prepare_options.tsv" \
  grt_reads_qc_enabled \
  true
grep -F -- " --reads ${reads} --reads ${reads_second}" \
  "${multiple_reads_output_root}/prepare_grt_inputs.sh" >/dev/null
[[ "$(grep -oF -- " --reads " "${multiple_reads_output_root}/prepare_grt_inputs.sh" | wc -l)" -eq 2 ]] || {
  echo "multiple-read prepare did not generate exactly two --reads arguments" >&2
  exit 1
}

for missing_command in minimap2 nucmer delta-filter show-coords; do
  restricted_bin="${TMP_DIR}/missing-${missing_command}-bin"
  error_path="${TMP_DIR}/missing-${missing_command}.err"
  make_restricted_path "$restricted_bin" "$missing_command"
  if PATH="$restricted_bin" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_missing_grt_tool "$ref" \
    --ds ds_missing_grt_tool "$ds" \
    -o "${TMP_DIR}/missing-${missing_command}-output" \
    >/dev/null 2>"$error_path"; then
    echo "expected missing ${missing_command} to fail" >&2
    exit 1
  fi
  grep -F "Required command not found in PATH: ${missing_command}" "$error_path" >/dev/null || {
    echo "expected missing-command error for ${missing_command}" >&2
    cat "$error_path" >&2
    exit 1
  }
done

capability_stub="${TMP_DIR}/mummer-capability-stub"
cat > "$capability_stub" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${GPM_TEST_MUMMER_HELP:-}"
EOF
chmod +x "$capability_stub"

capability_commands=(nucmer nucmer delta-filter show-coords)
capability_help=(
  $' -t, --threads=NUM'
  $'     --batch=BASES'
  $'-r    reference-order option'
  $'-l    sequence-length option'
)
capability_missing=(--batch -t/--threads -l -r)

for capability_index in "${!capability_commands[@]}"; do
  capability_command="${capability_commands[$capability_index]}"
  restricted_bin="${TMP_DIR}/incompatible-${capability_index}-bin"
  output_path="${TMP_DIR}/incompatible-${capability_index}-output"
  error_path="${TMP_DIR}/incompatible-${capability_index}.err"
  make_restricted_path "$restricted_bin" ""
  rm -f "${restricted_bin}/${capability_command}"
  cp "$capability_stub" "${restricted_bin}/${capability_command}"

  if GPM_TEST_MUMMER_HELP="${capability_help[$capability_index]}" \
    PATH="$restricted_bin" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_incompatible_mummer "$ref" \
    --ds ds_incompatible_mummer "$ds" \
    -o "$output_path" \
    >/dev/null 2>"$error_path"; then
    echo "expected incompatible ${capability_command} to fail" >&2
    exit 1
  fi
  grep -F "Incompatible MUMmer tool '${restricted_bin}/${capability_command}': missing required option ${capability_missing[$capability_index]}." \
    "$error_path" >/dev/null || {
      echo "expected missing MUMmer capability error for ${capability_command}" >&2
      cat "$error_path" >&2
      exit 1
    }
  [[ ! -e "$output_path" ]] || {
    echo "incompatible MUMmer preflight created output workspace: $output_path" >&2
    exit 1
  }
done

delta_l_only_bin="${TMP_DIR}/delta-l-only-bin"
delta_l_only_output="${TMP_DIR}/delta-l-only-output"
make_restricted_path "$delta_l_only_bin" ""
rm -f "${delta_l_only_bin}/delta-filter"
cp "$capability_stub" "${delta_l_only_bin}/delta-filter"
GPM_TEST_MUMMER_HELP=$'-l    sequence-length option' \
  PATH="$delta_l_only_bin" "$PREPARE_BASH" "$SCRIPT" \
  --ref ref_delta_l_only "$ref" \
  --ds ds_delta_l_only "$ds" \
  -o "$delta_l_only_output" \
  >/dev/null
[[ -f "${delta_l_only_output}/metadata/package.tsv" ]] || {
  echo "delta-filter with required -l but no unused -r did not pass preflight" >&2
  exit 1
}

for missing_command in meryl merqury.sh craq; do
  no_reads_bin="${TMP_DIR}/no-reads-missing-${missing_command}-bin"
  make_restricted_path "$no_reads_bin" "$missing_command"
  PATH="$no_reads_bin" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_no_reads_qc_tool "$ref" \
    --ds ds_no_reads_qc_tool "$ds" \
    -o "${TMP_DIR}/no-reads-missing-${missing_command}-output" \
    >/dev/null

  restricted_bin="${TMP_DIR}/missing-${missing_command}-bin"
  error_path="${TMP_DIR}/missing-${missing_command}.err"
  make_restricted_path "$restricted_bin" "$missing_command"
  if PATH="$restricted_bin" "$PREPARE_BASH" "$SCRIPT" \
    --ref ref_missing_grt_qc "$ref" \
    --ds ds_missing_grt_qc "$ds" \
    --reads "$reads" \
    -o "${TMP_DIR}/missing-${missing_command}-output" \
    >/dev/null 2>"$error_path"; then
    echo "expected missing ${missing_command} with reads to fail" >&2
    exit 1
  fi
  grep -F "Required command not found in PATH: ${missing_command}" "$error_path" >/dev/null || {
    echo "expected missing-command error for ${missing_command}" >&2
    cat "$error_path" >&2
    exit 1
  }
done

grep -q $'^Chr01\t20\t' "${output_root}/data/reference/ref_add_options.fa.fai" || {
  echo "reference .fai was not regenerated from the current FASTA" >&2
  exit 1
}
grep -q $'^tig_add\t20\t' "${output_root}/data/datasets/ds_add.fa.fai" || {
  echo "dataset .fai was not regenerated from the current FASTA" >&2
  exit 1
}

echo "gpm_server_prepare_metadata_test.sh: ok"
