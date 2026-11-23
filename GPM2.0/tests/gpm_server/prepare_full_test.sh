#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/server/prepare.sh"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_BIN="${TMP_DIR}/bin"
mkdir -p "$FAKE_BIN"
REAL_PYTHON="$(command -v python3)"
cat > "${FAKE_BIN}/python3" <<EOF
#!/usr/bin/env bash
if [[ "\${1:-}" == */post_lgz_refinement.py && "\${2:-}" == --check-environment ]]; then
  # Exercise the real reads/tool validation, replacing only the locked runtime
  # probe because this preparation fixture supplies fake external commands.
  exec "$REAL_PYTHON" -c '
import sys
from pathlib import Path
sys.argv = sys.argv[1:]
sys.path.insert(0, str(Path(sys.argv[0]).parent))
import refinement_config
refinement_config.validate_runtime = lambda **kwargs: None
from post_lgz_refinement import main
sys.exit(main())
' "\$@"
fi
exec "$REAL_PYTHON" "\$@"
EOF
chmod +x "${FAKE_BIN}/python3"


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
  show-coords:-THrcl)
    if [[ -n "\${FAKE_CEN_COORDS:-}" ]]; then cat "\$FAKE_CEN_COORDS"; fi
    ;;
  delta-filter:-h|show-coords:-h)
    printf '%s\n' '-r    reference-order option' '-l    sequence-length option'
    ;;
esac
exit 0
EOF
done

cat > "${FAKE_BIN}/meryl" <<'EOF'
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

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/meryl" "${FAKE_BIN}/zip" \
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
          $(columns["schema_version"]) != "4" ||
          $(columns["grt_precompute_enabled"]) != "true" ||
          $(columns["recipe_locked"]) != "true" ||
          $(columns["final_path_schema_version"]) != "1") {
        print "package.tsv missing locked LGZ v1 identity" > "/dev/stderr"
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_score "$ref" \
    --ds ds_score "$ds" \
    --score 72 \
    -o "$output_root" >/dev/null

  assert_package_metadata "${output_root}/.runtime/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned" "72"

  local short_output_root="${TMP_DIR}/score_short_gpm_server"
  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_score "$ref" \
    --ds ds_score "$ds" \
    -s 65 \
    -o "$short_output_root" >/dev/null

  assert_package_metadata "${short_output_root}/.runtime/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned" "65"
}

test_minimap_options_set_preset_and_threads() {
  local ref="${TMP_DIR}/ref-minimap.fa"
  local ds_a="${TMP_DIR}/ds-minimap-a.fa"
  local ds_b="${TMP_DIR}/ds-minimap-b.fa"
  local output_root="${TMP_DIR}/minimap_options_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAA"
  write_multi_fasta "$ds_a" \
    "tig_a1" "AAAAAAAAAA" \
    "tig_a2" "AAAAACCCCC"
  write_multi_fasta "$ds_b" "tig_b" "CCCCCCCCCC"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_minimap "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --minimap-preset asm5 \
    --threads 12 \
    -o "$output_root" >/dev/null

  grep -F 'minimap2 -c -x asm5 -K "${GPM_RUN_MINIMAP_BATCH:-1G}" -t "${GPM_TASK_THREADS:-12}" -o result.paf' "${output_root}/02_alignments/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected ds-vs-ref command to emit CIGAR (-c), use asm5, default K1G and 12 threads" >&2
    cat "${output_root}/02_alignments/ds_a_vs_ref/command.sh" >&2
    exit 1
  }

  grep -Fx $'minimap_batch\t1G' "${output_root}/.runtime/metadata/prepare_options.tsv" >/dev/null
  grep -Fx $'minimap_filter\tdefault' "${output_root}/.runtime/metadata/prepare_options.tsv" >/dev/null

  cat > "${output_root}/02_alignments/ds_a_vs_ref/result.paf" <<'EOF'
tig_a1	10	0	6	+	Chr01	6	0	6	6	6	60
tig_a2	10	0	6	+	Chr01	6	0	6	6	6	60
EOF
  cat > "${output_root}/02_alignments/ds_b_vs_ref/result.paf" <<'EOF'
tig_b	10	0	6	+	Chr01	6	0	6	6	6	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null

  python3 - "$output_root" <<'PYBATCH'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
run = root / "02_alignments/chr_Chr01/ds_a_vs_self"
manifest_path = run / "self_batch_manifest.json"
manifest = json.loads(manifest_path.read_text())
assert manifest["preset"] == "asm5"
assert manifest["min_chain_score"] == 200
assert manifest["minimizers"] == 100
assert Path(manifest["restore"]) == run / "restore_self_paf.py"
assert Path(manifest["restore"]).is_file()
assert Path(manifest["target"]).read_text().startswith(">gpm_pair_000000001a\n")
assert Path(manifest["query"]).read_text().startswith(">gpm_pair_000000001b\n")
assert len(manifest["batches"]) == 1
batch = manifest["batches"][0]
command = Path(batch["directory"]) / "command.sh"
assert str(command) in (run / "command.sh").read_text()
assert "self_alignment_batches.py" in command.read_text()
assert str(manifest_path) in command.read_text()
tasks = json.loads((run.parent / "q0_alignment_tasks.json").read_text())["tasks"]
self_task = next(row for row in tasks if root / row["command"] == command)
assert self_task["max_threads"] == 2  # Two query records, within the 12-thread budget.
late = json.loads((run.parent / "alignment_tasks.json").read_text())["tasks"]
assert all("_vs_" not in row["command"] for row in late)
assert "tel_scan" not in (run.parent / "q0_generated_command.sh").read_text()
assert "cen_scan" not in (run.parent / "q0_generated_command.sh").read_text()
assert "_vs_" not in (run.parent / "generated_command.sh").read_text()
PYBATCH
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_b_vs_self" ]] || {
    echo "expected the one-contig ds_b track not to schedule a self run" >&2
    exit 1
  }
  grep -F 'minimap2 -c -x asm5 -t "${GPM_TASK_THREADS:-12}" -o result.paf' "${output_root}/02_alignments/chr_Chr01/ds_a_vs_ds_b/command.sh" >/dev/null || {
    echo "expected chr-local pair command to emit CIGAR (-c), use asm5 and 12 threads" >&2
    cat "${output_root}/02_alignments/chr_Chr01/ds_a_vs_ds_b/command.sh" >&2
    exit 1
  }
  # Completed raw evidence and self caches survive identical assignment regeneration.
  PATH="${FAKE_BIN}:$PATH" python3 - "$output_root" <<'PYCACHE'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / ".lib/tools"))
from run_outer_checkpoints import OuterCheckpointManager
run = root / "02_alignments/chr_Chr01"
for name in ("ds_a_vs_self", "ds_a_vs_ds_b"):
    (run / name / "result.paf").write_text("")
(run / "ds_a_vs_self/cache-marker").write_text("preserve")
manager = OuterCheckpointManager(root)
manager.commit(manager.prepare("q0_chr:Chr01", "02_alignments/chr_Chr01/q0_command.sh"))
PYCACHE
  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null
  PATH="${FAKE_BIN}:$PATH" python3 - "$output_root" <<'PYCACHE'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / ".lib/tools"))
from run_outer_checkpoints import OuterCheckpointManager
manager = OuterCheckpointManager(root)
valid, reason = manager.validate(manager.prepare("q0_chr:Chr01", "02_alignments/chr_Chr01/q0_command.sh"))
assert valid, reason
assert (root / "02_alignments/chr_Chr01/ds_a_vs_self/cache-marker").read_text() == "preserve"
PYCACHE
  # Removing an operation retires its data outside active runs/, rather than deleting it.
  : > "${output_root}/02_alignments/ds_b_vs_ref/result.paf"
  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_a_vs_ds_b" ]] || exit 1
  find "${output_root}/.runtime/run_all/retired_chr_operations/Chr01" -path '*/ds_a_vs_ds_b.*/result.paf' | grep -q .
}

test_self_alignment_restores_unique_cross_contig_pairs() {
  local ref="${TMP_DIR}/ref-self-pairs.fa"
  local ds="${TMP_DIR}/ds-self-pairs.fa"
  local output_root="${TMP_DIR}/self_pairs_gpm_server"
  local pair_bin="${TMP_DIR}/pair-bin"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAA"
  write_multi_fasta "$ds" \
    "tig_z" "AAAAAAAAAA" \
    "tig_a" "CCCCCCCCCC" \
    "tig_m" "GGGGGGGGGG"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_self_pairs "$ref" \
    --ds assembly "$ds" \
    -o "$output_root" >/dev/null

  cat > "${output_root}/02_alignments/assembly_vs_ref/result.paf" <<'EOF'
tig_z	10	0	10	+	Chr01	10	0	10	10	10	60
tig_a	10	0	10	+	Chr01	10	0	10	10	10	60
tig_m	10	0	10	+	Chr01	10	0	10	10	10	60
EOF

  mkdir -p "$pair_bin"
  cat > "${pair_bin}/minimap2" <<'PYFAKE'
#!/usr/bin/env python3
import sys
from pathlib import Path


def fasta(path):
    records = []
    name = None
    parts = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith(">"):
                if name is not None:
                    records.append((name, "".join(parts)))
                name = line[1:].split()[0]
                parts = []
            elif line:
                parts.append(line)
    if name is not None:
        records.append((name, "".join(parts)))
    return records


args = sys.argv[1:]
if "-d" in args:
    # Model the official index build, retaining target records for the fake mapper.
    Path(args[args.index("-d") + 1]).write_bytes(Path(args[-1]).read_bytes())
    print("[M::mm_idx_stat] distinct minimizers: 3", file=sys.stderr)
    raise SystemExit(0)
assert all(flag in args for flag in ("-c", "-X", "--no-hash-name"))
assert args[args.index("-x") + 1] == "asm10"
assert args[args.index("-m") + 1] == "200"
assert args[args.index("-n") + 1] == "100"
assert int(args[args.index("-t") + 1]) > 0
targets = fasta(args[-2])
queries = fasta(args[-1])
for query_name, query in queries:
    for target_name, target in targets:
        if query_name > target_name:
            continue
        length = min(len(query), len(target))
        print(
            f"{query_name}\t{len(query)}\t0\t{length}\t+\t{target_name}\t{len(target)}"
            f"\t0\t{length}\t{length}\t{length}\t60\tcg:Z:{length}M"
        )
PYFAKE
  chmod +x "${pair_bin}/minimap2"
  PATH="${pair_bin}:${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null

  PATH="${pair_bin}:${FAKE_BIN}:$PATH" bash \
    "${output_root}/02_alignments/chr_Chr01/assembly_vs_self/command.sh"

  local result="${output_root}/02_alignments/chr_Chr01/assembly_vs_self/result.paf"
  assert_file "$result"
  [[ "$(wc -l < "$result")" -eq 3 ]] || {
    echo "expected exactly three unordered cross-contig pairs" >&2
    cat "$result" >&2
    exit 1
  }
  awk -F '\t' '$1 == $6 { exit 1 }' "$result" || {
    echo "same-contig self alignment survived canonical restoration" >&2
    cat "$result" >&2
    exit 1
  }
  cut -f1,6 "$result" | sort > "${TMP_DIR}/self-pairs.actual"
  cat > "${TMP_DIR}/self-pairs.expected" <<'EOF'
tig_a	tig_m
tig_a	tig_z
tig_m	tig_z
EOF
  cmp "${TMP_DIR}/self-pairs.expected" "${TMP_DIR}/self-pairs.actual"
  ! grep -q 'gpm_pair_' "$result" || {
    echo "temporary pair aliases leaked into the canonical PAF" >&2
    cat "$result" >&2
    exit 1
  }
}

test_alignment_engine_defaults_and_validation() {
  local ref="${TMP_DIR}/ref-aligner.fa"
  local ds="${TMP_DIR}/ds-aligner.fa"
  local default_root="${TMP_DIR}/aligner_default_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAA"
  write_multi_fasta "$ds" "tig_a" "AAAAAAAAAA"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_aligner "$ref" \
    --ds ds_a "$ds" \
    -o "$default_root" >/dev/null
  grep -F 'long_cigar_recovery/server_alignment.py' "${default_root}/02_alignments/ds_a_vs_ref/command.sh" >/dev/null
  grep -F -- '--threads "${GPM_TASK_THREADS:-10}" --preset asm10 --result result.paf' "${default_root}/02_alignments/ds_a_vs_ref/command.sh" >/dev/null || {
    echo "expected proactive initial-reference adapter with native asm10 and 10 threads" >&2
    cat "${default_root}/02_alignments/ds_a_vs_ref/command.sh" >&2
    exit 1
  }
  assert_file "${default_root}/.lib/tools/long_cigar_recovery/branch-runtime.json"
  cmp "${default_root}/run_all.sh" "${REPO_ROOT}/server/lib/run_all_launcher.sh"
  assert_prepare_option "${default_root}/.runtime/metadata/prepare_options.tsv" alignment_engine minimap2
  assert_prepare_option "${default_root}/.runtime/metadata/prepare_options.tsv" threads 10

  local option value
  for option in --aligner --blastn-task --blastn-evalue --winnowmap-kmer; do
    value=unused
    [[ "$option" != --aligner ]] || value=minimap2
    if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
      --ref ref_aligner "$ref" \
      --ds ds_a "$ds" \
      "$option" "$value" \
      -o "${TMP_DIR}/removed_option_gpm_server" > /dev/null 2>"${TMP_DIR}/removed_option.err"; then
      echo "expected removed option to fail: $option" >&2
      exit 1
    fi
    grep -F -- "Unknown argument: $option" "${TMP_DIR}/removed_option.err" >/dev/null
    [[ ! -e "${TMP_DIR}/removed_option_gpm_server" ]]
  done
}

test_out_alias_sets_output_root() {
  local ref="${TMP_DIR}/ref-out.fa"
  local ds="${TMP_DIR}/ds-out.fa"
  local output_root="${TMP_DIR}/out_alias_gpm_server"
  write_fasta "$ref" ref_out
  write_fasta "$ds" ds_out

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_out "$ref" \
    --ds ds_out "$ds" \
    --out "$output_root" >/dev/null

  assert_file "${output_root}/.runtime/metadata/package.tsv"
  assert_file "${output_root}/run_all.sh"
}

assert_chr_partition_run_all_staging() {
  local run_all="$1"
  local output_root="$2"
  local chr_name="$3"
  local plan="${output_root}/.runtime/run_all/plan.tsv"

  bash -n "$run_all"
  cmp "${REPO_ROOT}/server/lib/run_all_launcher.sh" "$run_all"
  [[ -f "$plan" ]] || {
    echo "missing run_all execution plan: $plan" >&2
    exit 1
  }
  mapfile -t command_lines < <(tail -n +2 "$plan")
  [[ "${#command_lines[@]}" -eq 14 ]] || {
    echo "expected 14 staged plan units, got ${#command_lines[@]}" >&2
    if [[ "${#command_lines[@]}" -gt 0 ]]; then
      printf '%s\n' "${command_lines[@]}" >&2
    fi
    exit 1
  }

  [[ "${command_lines[0]}" == $'ref:ds_a\t02_alignments/ds_a_vs_ref/command.sh\t02_alignments/ds_a_vs_ref/stderr.log' ]] || {
    echo "unexpected first run_all plan unit" >&2
    printf '%s\n' "${command_lines[0]}" >&2
    exit 1
  }
  [[ "${command_lines[1]}" == $'ref:ds_b\t02_alignments/ds_b_vs_ref/command.sh\t02_alignments/ds_b_vs_ref/stderr.log' ]] || {
    echo "unexpected second run_all plan unit" >&2
    printf '%s\n' "${command_lines[1]}" >&2
    exit 1
  }
  local expected_tail
  expected_tail="$(cat <<EOF
assign	.runtime/commands/assign_chr_groups.sh	.runtime/logs/run_all.log
q0_chr:${chr_name}	02_alignments/chr_${chr_name}/q0_command.sh	.runtime/logs/run_all.log
q0_evidence	.runtime/commands/prepare_q0_evidence.sh	.runtime/logs/run_all.log
lgz_prepare	.runtime/commands/prepare_lgz_inputs.sh	.runtime/logs/run_all.log
grt_step1	.runtime/commands/run_lgz_step1.sh	.runtime/logs/run_all.log
grt_step2	.runtime/commands/run_lgz_step2.sh	.runtime/logs/run_all.log
grt_step3	.runtime/commands/run_lgz_step3.sh	.runtime/logs/run_all.log
chr:${chr_name}	02_alignments/chr_${chr_name}/command.sh	.runtime/logs/run_all.log
finalize_evidence	.runtime/commands/finalize_lgz_evidence.sh	.runtime/logs/run_all.log
refinement	.runtime/commands/run_refinement.sh	.runtime/logs/run_all.log
package_full	.runtime/commands/package_full_zip.sh	.runtime/logs/run_all.log
package_light	.runtime/commands/package_light_zip.sh	.runtime/logs/run_all.log
EOF
)"
  [[ "$(printf '%s\n' "${command_lines[@]:2}")" == "$expected_tail" ]] || {
    echo "unexpected run_all plan tail" >&2
    printf '%s\n' "${command_lines[@]:2}" >&2
    exit 1
  }
  [[ -f "${output_root}/.lib/tools/run_all_runner.py" ]] || {
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
ds_a	tig_multi	01_inputs/04_derived/partitions/chr/Chr01/ds_a.fa
ds_b	tig_chr1	01_inputs/04_derived/partitions/chr/Chr01/ds_b.fa
ds_b	tig_unplaced	01_inputs/04_derived/partitions/unplaced/ds_b.fa
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
  local output_root="${TMP_DIR}/run01"
  local prepare_log="${TMP_DIR}/custom_prepare.log"
  write_fasta "$ref" ref
  write_fasta "$ds_a" ds_a
  write_fasta "$ds_b" ds_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --lgz-execution-profile optimized \
    --lgz-step2-mummer-scope gap-screen \
    --lgz-qc-memory-gb 80 \
    --lgz-kmer-size 21 \
    -o "$output_root" >"$prepare_log"

  grep -F 'Both archives contain top-level run01/{metadata,data,runs,report}' "$prepare_log" >/dev/null || {
    echo "delivery reminder must use the custom workspace basename" >&2
    exit 1
  }
  if grep -F 'Both archives contain top-level gpm_server/' "$prepare_log" >/dev/null; then
    echo "delivery reminder must not hard-code the default root" >&2
    exit 1
  fi

  assert_dir "${output_root}/.runtime/metadata"
  assert_file "${output_root}/.runtime/metadata/reference.tsv"
  assert_file "${output_root}/.runtime/metadata/package.tsv"
  assert_file "${output_root}/.runtime/metadata/datasets.tsv"
  assert_file "${output_root}/run_all.sh"
  assert_file "${output_root}/.runtime/commands/export_final_path_fasta.sh"
  assert_file "${output_root}/.lib/lib/final_path.sh"
  assert_file "${output_root}/.lib/tools/add_dataset_package.py"
  assert_file "${output_root}/.lib/tools/grt_prepare_inputs.py"
  assert_file "${output_root}/.lib/tools/grt_step1.py"
  [[ ! -e "${output_root}/.lib/tools/grt_step12.py" ]]
  assert_file "${output_root}/.lib/tools/grt_core/step1_engine.py"
  assert_file "${output_root}/.lib/tools/grt_core/step2_engine.py"
  assert_file "${output_root}/.lib/tools/grt_step1.py"
  assert_file "${output_root}/.lib/tools/grt_step2.py"
  assert_file "${output_root}/.lib/tools/grt_step3.py"
  assert_file "${output_root}/.lib/tools/grt_evidence_package.py"
  assert_file "${output_root}/.lib/contracts/grt_precomputed_v2.json"
  assert_file "${output_root}/.runtime/commands/prepare_lgz_inputs.sh"
  [[ -f "${output_root}/.runtime/commands/run_lgz_step1.sh" ]]
  assert_file "${output_root}/.runtime/commands/run_lgz_step1.sh"
  assert_file "${output_root}/.runtime/commands/run_lgz_step2.sh"
  assert_file "${output_root}/.runtime/commands/run_lgz_step3.sh"
  assert_file "${output_root}/.runtime/commands/finalize_lgz_evidence.sh"
  for name in prepare_grt_inputs run_grt_step1 run_grt_step2 run_grt_step3 finalize_grt_evidence; do
    assert_file "${output_root}/.runtime/commands/${name}.sh"
    grep -F 'exec bash ' "${output_root}/.runtime/commands/${name}.sh" >/dev/null
    bash -n "${output_root}/.runtime/commands/${name}.sh"
  done
  assert_file "${output_root}/.lib/tools/lgz_compat.py"
  assert_file "${output_root}/.lib/tools/lgz_core/step1_engine.py"
  assert_file "${output_root}/.lib/tools/lgz_core/step2_engine.py"
  assert_file "${output_root}/.lib/tools/lgz_step1.py"
  assert_file "${output_root}/.lib/tools/lgz_step2.py"

  assert_file "${output_root}/.runtime/commands/package_full_zip.sh"
  assert_file "${output_root}/.runtime/commands/package_light_zip.sh"
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref"
  assert_package_metadata "${output_root}/.runtime/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned"
  assert_tsv_has_self_alignment_flag "${output_root}/.runtime/metadata/datasets.tsv" "true"
  # Test legacy forwarding with a harmless spy, never by executing real analysis.
  local alias_dir="${output_root}/alias forwarding"
  mkdir -p "$alias_dir"
  cp "${output_root}/.runtime/commands/run_grt_step2.sh" "${alias_dir}/run_grt_step2.sh"
  cat > "${alias_dir}/run_lgz_step2.sh" <<'SPY'
#!/usr/bin/env bash
printf '%s\n' "$@"
SPY
  [[ "$(bash "${alias_dir}/run_grt_step2.sh" one "two words")" == $'one\ntwo words' ]]

}

test_removed_package_mode_flags_are_rejected() {
  local ref="${TMP_DIR}/ref-flags.fa"
  local ds="${TMP_DIR}/ds-flags.fa"
  write_fasta "$ref" ref_flags
  write_fasta "$ds" ds_flags

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
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

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
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
    if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
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
    ln -s "${FAKE_BIN}/python3" "${output_dir}/python3"
    local command_name
    for command_name in bash dirname gzip; do
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
  if PATH="$missing_base_bin" /bin/bash "$SCRIPT" --archive-format zip \
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
  PATH="$missing_qc_bin:/usr/bin:/bin" /bin/bash "$SCRIPT" --archive-format zip \
    --ref ref_standard_without_craq "$ref" \
    --ds ds_standard_without_craq "$ds" \
    --hifi "$reads" \
    -o "${TMP_DIR}/standard-without-craq-output" \
    >/dev/null
  if PATH="$missing_qc_bin:/usr/bin:/bin" /bin/bash "$SCRIPT" --archive-format zip \
    --ref ref_missing_grt_qc "$ref" \
    --ds ds_missing_grt_qc "$ds" \
    --hifi "$reads" \
    --reads-qc full \
    -o "${TMP_DIR}/missing-craq-output" \
    >/dev/null 2>"${TMP_DIR}/missing-craq.err"; then
    echo "expected new reads QC preparation to fail" >&2
    exit 1
  fi
  grep -F 'legacy-only' \
    "${TMP_DIR}/missing-craq.err" >/dev/null || {
    echo "expected legacy QC rejection" >&2
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
    PATH="${FAKE_BIN}:$PATH" bash "${upload_root}/server/prepare.sh" --archive-format zip \
      --ref ref_default "$ref" \
      --ds ds_default "$ds" >/dev/null
  )

  assert_file "${TMP_DIR}/gpm_server/.runtime/metadata/reference.tsv"
  assert_file "${TMP_DIR}/gpm_server/run_all.sh"
  assert_file "${TMP_DIR}/gpm_server/.runtime/commands/export_final_path_fasta.sh"
  assert_file "${TMP_DIR}/gpm_server/.lib/lib/final_path.sh"
  assert_file "${TMP_DIR}/gpm_server/.lib/tools/add_dataset_package.py"
}

test_skip_self_option_omits_self_runs() {
  local ref="${TMP_DIR}/ref-skip.fa"
  local ds_a="${TMP_DIR}/ds-skip-a.fa"
  local ds_b="${TMP_DIR}/ds-skip-b.fa"
  local output_root="${TMP_DIR}/skip_self_gpm_server"
  write_fasta "$ref" ref_skip
  write_fasta "$ds_a" ds_skip_a
  write_fasta "$ds_b" ds_skip_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_skip "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --skip-self \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/run_all.sh"
  [[ ! -d "${output_root}/02_alignments/ds_a_vs_self" ]] || {
    echo "expected --skip-self not to create ds_a_vs_self" >&2
    exit 1
  }
  [[ ! -d "${output_root}/02_alignments/ds_b_vs_self" ]] || {
    echo "expected --skip-self not to create ds_b_vs_self" >&2
    exit 1
  }
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref_skip"
  assert_package_metadata "${output_root}/.runtime/metadata/package.tsv" "fast" "true" "none" "chr_partition" "partitioned"
  assert_tsv_has_self_alignment_flag "${output_root}/.runtime/metadata/datasets.tsv" "false"
}

test_prepare_writes_package_metadata_and_stages_runs() {
  local ref="${TMP_DIR}/ref-partitioned.fa"
  local ds_a="${TMP_DIR}/ds-fast-a.fa"
  local ds_b="${TMP_DIR}/ds-fast-b.fa"
  local output_root="${TMP_DIR}/partitioned_gpm_server"
  write_fasta "$ref" ref_partitioned
  write_fasta "$ds_a" ds_a
  write_fasta "$ds_b" ds_b

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_partitioned "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/.runtime/metadata/package.tsv"
  [[ ! -f "${output_root}/.runtime/metadata/chr_assignments.tsv" ]] || {
    echo "expected prepare not to precompute metadata/chr_assignments.tsv" >&2
    exit 1
  }
  assert_file "${output_root}/.runtime/commands/assign_chr_groups.sh"
  assert_file "${output_root}/02_alignments/chr_ref_partitioned/command.sh"
  assert_package_metadata "${output_root}/.runtime/metadata/package.tsv" "fast" "true" "chr_partition" "chr_partition" "partitioned"
  assert_chr_partition_run_all_staging "${output_root}/run_all.sh" "$output_root" "ref_partitioned"
}

test_prepare_rejects_reference_without_sequences() {
  local ref="${TMP_DIR}/ref-empty.fa"
  local ds="${TMP_DIR}/ds-empty-ref.fa"
  local output_root="${TMP_DIR}/empty_ref_gpm_server"
  : > "$ref"
  write_fasta "$ds" ds_empty_ref

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_partitioned_assign "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    -o "$output_root" >/dev/null

  cat > "${output_root}/02_alignments/ds_a_vs_ref/result.paf" <<'EOF'
tig_multi	10	0	4	+	Chr01	30	4	8	4	4	60
tig_multi	10	2	6	-	Chr01	30	9	13	4	4	60
tig_multi	10	0	6	+	Chr02	30	14	20	6	6	60
EOF
  cat > "${output_root}/02_alignments/ds_b_vs_ref/result.paf" <<'EOF'
tig_chr1	10	1	8	-	Chr01	30	7	14	7	7	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null

  assert_file "${output_root}/.runtime/metadata/chr_assignments.tsv"
  assert_chr_assignments_tsv "${output_root}/.runtime/metadata/chr_assignments.tsv"
  assert_file "${output_root}/.runtime/metadata/reference_chr_locator.tsv"
  assert_file "${output_root}/.runtime/metadata/source_seq_locator.tsv"
  assert_file "${output_root}/.runtime/metadata/source_seq_n_regions.tsv"
  assert_reference_chr_locator_tsv "${output_root}/.runtime/metadata/reference_chr_locator.tsv"
  assert_source_seq_locator_tsv "${output_root}/.runtime/metadata/source_seq_locator.tsv"
  grep -F $'ds_b\ttig_chr1\t3\t4\t2' "${output_root}/.runtime/metadata/source_seq_n_regions.tsv" >/dev/null || {
    echo "expected assigned tig_chr1 N region to be scanned" >&2
    cat "${output_root}/.runtime/metadata/source_seq_n_regions.tsv" >&2
    exit 1
  }
  grep -F $'ds_b\ttig_unplaced\t3\t6\t4' "${output_root}/.runtime/metadata/source_seq_n_regions.tsv" >/dev/null || {
    echo "expected unplaced tig_unplaced N region to be scanned" >&2
    cat "${output_root}/.runtime/metadata/source_seq_n_regions.tsv" >&2
    exit 1
  }
  assert_text_fasta_contents "${output_root}/01_inputs/01_reference/chrs/Chr01.fa" $'>Chr01\nAAAAAA\n'
  assert_text_fasta_contents "${output_root}/01_inputs/01_reference/chrs/Chr02.fa" $'>Chr02\nCCCCCC\n'
  assert_text_fasta_contents "${output_root}/01_inputs/04_derived/partitions/chr/Chr01/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/01_inputs/04_derived/partitions/chr/Chr01/ds_b.fa" $'>tig_chr1\nCCNNCCCCCC\n'
  assert_text_fasta_contents "${output_root}/01_inputs/04_derived/partitions/chr/Chr02/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/01_inputs/04_derived/partitions/unplaced/ds_b.fa" $'>tig_unplaced\nTTNNNNTTTT\n'
  assert_text_fasta_contents "${output_root}/02_alignments/chr_Chr01/datasets/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  assert_text_fasta_contents "${output_root}/02_alignments/chr_Chr01/datasets/ds_b.fa" $'>tig_chr1\nCCNNCCCCCC\n'
  assert_text_fasta_contents "${output_root}/02_alignments/chr_Chr02/datasets/ds_a.fa" $'>tig_multi\nAAAAAAAAAA\n'
  [[ ! -f "${output_root}/02_alignments/chr_Chr02/datasets/ds_b.fa" ]] || {
    echo "expected chr_Chr02 not to include ds_b" >&2
    exit 1
  }
  assert_file "${output_root}/02_alignments/chr_Chr01/generated_command.sh"
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_a_vs_self" ]] || {
    echo "expected one-contig chr_Chr01/ds_a track not to schedule a self run" >&2
    exit 1
  }
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_b_vs_self" ]] || {
    echo "expected one-contig chr_Chr01/ds_b track not to schedule a self run" >&2
    exit 1
  }
  assert_file "${output_root}/02_alignments/chr_Chr01/ds_a_vs_ds_b/command.sh"
  assert_file "${output_root}/02_alignments/chr_Chr02/generated_command.sh"
  [[ ! -d "${output_root}/02_alignments/chr_Chr02/ds_a_vs_self" ]] || {
    echo "expected one-contig chr_Chr02/ds_a track not to schedule a self run" >&2
    exit 1
  }
  [[ ! -d "${output_root}/02_alignments/chr_Chr02/ds_a_vs_ds_b" ]] || {
    echo "expected chr_Chr02 not to include cross-dataset run" >&2
    exit 1
  }

  if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/package_full_zip.sh" \
      >"${TMP_DIR}/premature-package.out" 2>"${TMP_DIR}/premature-package.err"; then
    echo "expected packaging before LGZ finalization to fail" >&2
    exit 1
  fi
  grep -q "MISSING_REQUIRED_FILE" "${TMP_DIR}/premature-package.err" || {
    echo "expected package preflight to report the incomplete LGZ contract" >&2
    cat "${TMP_DIR}/premature-package.err" >&2
    exit 1
  }
}

test_reads_enable_post_lgz_degap_without_qc() {
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_grt_reads "$ref" --ds ds_a "$ds_a" --ds ds_b "$ds_b" \
    --ont "$reads_a" "$reads_b" -o "$output_root" >/dev/null
  awk -F '\t' '
    NR == 1 { for (i = 1; i <= NF; i++) column[$i] = i; next }
    NR == 2 { exit ($(column["reads_qc_enabled"]) == "false" ? 0 : 1) }
  ' "${output_root}/.runtime/metadata/package.tsv"
  assert_prepare_option "${output_root}/.runtime/metadata/prepare_options.tsv" grt_reads_qc_enabled false
  ! grep -F -- " --reads " "${output_root}/.runtime/commands/prepare_lgz_inputs.sh" >/dev/null
  grep -F $'refinement\t.runtime/commands/run_refinement.sh' "${output_root}/.runtime/run_all/plan.tsv" >/dev/null
  python3 - "${output_root}/.runtime/refinement/config.json" "$reads_a" "$reads_b" <<'PYREADS'
import json, sys
value = json.load(open(sys.argv[1]))
assert value["schema"] == "cgat.refinement-config" and value["schema_version"] == 1
assert value["groups"]["ont"] == sys.argv[2:]
assert value["groups"]["hifi"] == []
PYREADS

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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_partitioned_skip "$ref" \
    --ds ds_a "$ds_a" \
    --ds ds_b "$ds_b" \
    --skip-self \
    -o "$output_root" >/dev/null

  cat > "${output_root}/02_alignments/ds_a_vs_ref/result.paf" <<'EOF'
tig_multi	10	0	6	+	Chr01	30	4	10	6	6	60
EOF
  cat > "${output_root}/02_alignments/ds_b_vs_ref/result.paf" <<'EOF'
tig_chr1	10	1	8	+	Chr01	30	7	14	7	7	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null

  assert_file "${output_root}/02_alignments/chr_Chr01/generated_command.sh"
  assert_file "${output_root}/02_alignments/chr_Chr01/ds_a_vs_ds_b/command.sh"
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_a_vs_self" ]] || {
    echo "expected --skip-self to suppress chr-local ds_a_vs_self" >&2
    exit 1
  }
  [[ ! -d "${output_root}/02_alignments/chr_Chr01/ds_b_vs_self" ]] || {
    echo "expected --skip-self to suppress chr-local ds_b_vs_self" >&2
    exit 1
  }
  ! grep -q '_vs_self' "${output_root}/02_alignments/chr_Chr01/q0_generated_command.sh" || {
    echo "expected generated chr command not to contain self runs when --skip-self is set" >&2
    exit 1
  }
  printf '>tig_second\nAAAAAAAAAA\n' >> "${output_root}/01_inputs/02_assemblies/ds_a.fa"
  printf 'tig_second\t10\t0\t6\t+\tChr01\t30\t4\t10\t6\t6\t60\n' >> "${output_root}/02_alignments/ds_a_vs_ref/result.paf"
  if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >"${TMP_DIR}/skip-conflict.log" 2>&1; then
    echo "expected --skip-self to reject multiple same-dataset q0 candidates" >&2
    exit 1
  fi
  grep -F -- '--skip-self conflicts with multiple candidate contigs' "${TMP_DIR}/skip-conflict.log" >/dev/null
}

test_prepare_writes_reference_segments_metadata() {
  local ref="${TMP_DIR}/ref-gap.fa"
  local ds="${TMP_DIR}/ds-gap.fa"
  local output_root="${TMP_DIR}/gap_gpm_server"
  write_gap_ref_partitioneda "$ref"
  write_fasta "$ds" ds_gap

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_gap "$ref" \
    --ds ds_gap "$ds" \
    -o "$output_root" >/dev/null

  assert_reference_segments_tsv "${output_root}/.runtime/metadata/reference_segments.tsv"
}

test_prepare_normalizes_plain_fna_inputs_to_package_fa() {
  local ref="${TMP_DIR}/ref-input.fna"
  local ds="${TMP_DIR}/ds-input.fna"
  local output_root="${TMP_DIR}/fna_gpm_server"
  local expected_ref=$'>ref_from_fna\nACGT\n'
  local expected_ds=$'>ds_from_fna\nACGT\n'
  printf '%s' "$expected_ref" > "$ref"
  printf '%s' "$expected_ds" > "$ds"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_from_fna "$ref" \
    --ds ds_from_fna "$ds" \
    -o "$output_root" >/dev/null

  assert_text_fasta_contents "${output_root}/01_inputs/01_reference/ref_from_fna.fa" "$expected_ref"
  assert_text_fasta_contents "${output_root}/01_inputs/02_assemblies/ds_from_fna.fa" "$expected_ds"
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_from_gz "$ref_gz" \
    --ds ds_from_gz "$ds_gz" \
    -o "$output_root" >/dev/null

  assert_text_fasta_contents "${output_root}/01_inputs/01_reference/ref_from_gz.fa" "$expected_ref"
  assert_text_fasta_contents "${output_root}/01_inputs/02_assemblies/ds_from_gz.fa" "$expected_ds"
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_tel "$ref" \
    --ds ds_a "$ds" \
    --tel TTAGGG 20 \
    --tel TTTAGGG 10 \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/03_lgz/06_annotations/tel/rules.tsv"
  grep -F $'\tTTAGGG\t20\ttrue' "${output_root}/03_lgz/06_annotations/tel/rules.tsv" >/dev/null || {
    echo "expected TTAGGG tel rule" >&2
    cat "${output_root}/03_lgz/06_annotations/tel/rules.tsv" >&2
    exit 1
  }
  grep -F $'\tTTTAGGG\t10\ttrue' "${output_root}/03_lgz/06_annotations/tel/rules.tsv" >/dev/null || {
    echo "expected TTTAGGG tel rule" >&2
    cat "${output_root}/03_lgz/06_annotations/tel/rules.tsv" >&2
    exit 1
  }

  cat > "${output_root}/02_alignments/ds_a_vs_ref/result.paf" <<'EOF'
tig_tel	248	0	200	+	Chr01	1000	1	201	200	200	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null
  assert_file "${output_root}/02_alignments/chr_Chr01/tel_scan/command.sh"
  assert_file "${output_root}/02_alignments/chr_Chr01/generated_command.sh"
  grep -F 'tel_scan/command.sh' "${output_root}/02_alignments/chr_Chr01/generated_command.sh" >/dev/null || {
    echo "expected generated chr command to include tel scan" >&2
    cat "${output_root}/02_alignments/chr_Chr01/generated_command.sh" >&2
    exit 1
  }

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/02_alignments/chr_Chr01/command.sh" >/dev/null
  assert_file "${output_root}/03_lgz/06_annotations/tel/chr_Chr01/ds_a.tsv"
  grep -F $'\tds_a\ttig_tel\tChr01\tTTAGGG\t20\t20\t3\t122\t+' "${output_root}/03_lgz/06_annotations/tel/chr_Chr01/ds_a.tsv" >/dev/null || {
    echo "expected forward TTAGGG tel mark" >&2
    cat "${output_root}/03_lgz/06_annotations/tel/chr_Chr01/ds_a.tsv" >&2
    exit 1
  }
  grep -F $'\tds_a\ttig_tel\tChr01\tTTAGGG\t20\t20\t125\t244\t-' "${output_root}/03_lgz/06_annotations/tel/chr_Chr01/ds_a.tsv" >/dev/null || {
    echo "expected reverse-complement TTAGGG tel mark" >&2
    cat "${output_root}/03_lgz/06_annotations/tel/chr_Chr01/ds_a.tsv" >&2
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

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_cen "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    --cen-min-len 5 \
    --cen-min-identity 80 \
    -o "$output_root" >/dev/null

  assert_file "${output_root}/03_lgz/06_annotations/cen/reference.tsv"
  local cen_query
  cen_query="$(python3 - "$output_root" <<'PYCEN'
import csv, json, sys
from pathlib import Path
root = Path(sys.argv[1])
rows = list(csv.DictReader((root / '03_lgz/06_annotations/cen/reference.tsv').open(), delimiter='\t'))
assert len(rows) == 5 and all(row['chr_name'] == '*' for row in rows)
row = next(row for row in rows if any(e['source'] == 'parameter' for e in json.loads(row['provenance'])))
assert int(row['min_len']) == 5 and float(row['min_identity']) == 80
print(row['sequence_name'])
PYCEN
)"

  cat > "${output_root}/02_alignments/ds_a_vs_ref/result.paf" <<'EOF'
tig_cen	40	0	40	+	Chr01	1000	1	41	40	40	60
EOF

  PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/assign_chr_groups.sh" >/dev/null
  assert_file "${output_root}/02_alignments/chr_Chr01/cen_scan/command.sh"
  grep -F 'cen_scan/command.sh' "${output_root}/02_alignments/chr_Chr01/generated_command.sh" >/dev/null || {
    echo "expected generated chr command to include cen scan" >&2
    cat "${output_root}/02_alignments/chr_Chr01/generated_command.sh" >&2
    exit 1
  }
  grep -F 'cen_scan.py' "${output_root}/02_alignments/chr_Chr01/cen_scan/command.sh" >/dev/null || {
    echo "expected repeat-aware cen scan command" >&2
    exit 1
  }
  local coords="${TMP_DIR}/cen.coords.tsv"
  printf '1\t20\t6\t25\t20\t20\t95.0\t20\t40\t100.0\t50.0\t%s\ttig_cen\n' "$cen_query" > "$coords"
  FAKE_CEN_COORDS="$coords" PATH="${FAKE_BIN}:$PATH" bash "${output_root}/02_alignments/chr_Chr01/cen_scan/command.sh" >/dev/null
  assert_file "${output_root}/03_lgz/06_annotations/cen/chr_Chr01/marks.tsv"
  grep -F "$(printf '%s\tChr01\t%s\tds_a\ttig_cen\t6\t25\t+\t20\t95.000\t0' "$cen_query" "$cen_query")" \
    "${output_root}/03_lgz/06_annotations/cen/chr_Chr01/marks.tsv" >/dev/null || {
    echo "expected merged candidate cen mark with real source provenance" >&2
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

  if PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_cen_dup "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    -o "$output_root" >/dev/null 2>"${TMP_DIR}/cen_dup.err"; then
    echo "expected duplicate cen chr headers to fail" >&2
    exit 1
  fi
  grep -F 'empty or duplicate FASTA name' "${TMP_DIR}/cen_dup.err" >/dev/null || {
    echo "expected duplicate cen chr error" >&2
    cat "${TMP_DIR}/cen_dup.err" >&2
    exit 1
  }
}

test_cen_accepts_unbound_sequence_names() {
  local ref="${TMP_DIR}/ref-cen-missing.fa"
  local cen="${TMP_DIR}/ref-cen-missing-regions.fa"
  local ds="${TMP_DIR}/ds-cen-missing.fa"
  local output_root="${TMP_DIR}/cen_missing_gpm_server"
  write_multi_fasta "$ref" "Chr01" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  write_multi_fasta "$cen" "Chr99_centromere" "AAAAAAAAAA"
  write_multi_fasta "$ds" "tig_cen" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

  PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
    --ref ref_cen_missing "$ref" \
    --ds ds_a "$ds" \
    --cen "$cen" \
    -o "$output_root" >/dev/null
  python3 - "$output_root" <<'PYCEN'
import csv, json, sys
from pathlib import Path
root = Path(sys.argv[1])
rows = list(csv.DictReader((root / '03_lgz/06_annotations/cen/reference.tsv').open(), delimiter='\t'))
assert all(row['chr_name'] == '*' for row in rows)
assert any(entry.get('sequence_name') == 'Chr99_centromere'
           for row in rows for entry in json.loads(row['provenance']))
PYCEN
}

test_custom_output_root
test_default_output_root_uses_current_working_directory
test_removed_package_mode_flags_are_rejected
test_removed_grt_tool_path_flags_are_rejected
test_grt_tool_discovery_fails_fast_for_missing_commands
test_score_option_sets_chr_assignment_threshold
test_minimap_options_set_preset_and_threads
test_self_alignment_restores_unique_cross_contig_pairs
test_alignment_engine_defaults_and_validation
test_out_alias_sets_output_root
test_skip_self_option_omits_self_runs
test_prepare_writes_reference_segments_metadata
test_prepare_normalizes_plain_fna_inputs_to_package_fa
test_prepare_decompresses_gzip_inputs_to_package_fa
test_tel_options_generate_chr_local_tel_marks
test_cen_option_generates_chr_local_cen_marks
test_cen_rejects_duplicate_chr_headers
test_cen_accepts_unbound_sequence_names
test_prepare_writes_package_metadata_and_stages_runs
test_prepare_rejects_reference_without_sequences
test_assignment_helper_generates_chr_assignments_and_chr_local_runs
test_reads_enable_post_lgz_degap_without_qc
test_skip_self_omits_chr_local_self_runs

echo "prepare_full_test.sh: ok"
