#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/server/prepare.sh"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_BIN="${TMP_DIR}/bin"
mkdir -p "$FAKE_BIN"

cp "${REPO_ROOT}/tests/gpm_server/fixture_faidx.py" "${FAKE_BIN}/samtools"

cat > "${FAKE_BIN}/minimap2" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

preset=""
emit_cigar=false
output=""
declare -a positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -c)
      emit_cigar=true
      shift
      ;;
    -x)
      preset="$2"
      shift 2
      ;;
    -o)
      output="$2"
      shift 2
      ;;
    -*)
      if [[ "${2:-}" != "" && "$2" != -* && "$1" =~ ^-(t|K|f)$ ]]; then
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
printf '%s\t%s\t0\t%s\t+\t%s\t%s\t0\t%s\t%s\t%s\t60' \
  "$query_name" "$query_len" "$align_len" "$target_name" "$target_len" "$align_len" "$align_len" "$align_len" > "$output"
if [[ "$emit_cigar" == "true" ]]; then
  printf '\tcg:Z:%sM' "$align_len" >> "$output"
fi
printf '\n' >> "$output"
printf 'preset=%s target=%s query=%s output=%s\n' "$preset" "$target" "$query" "$output" >> "${GPM_TEST_MINIMAP_LOG:?}"
EOF

for grt_tool in nucmer delta-filter show-coords; do
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
if [[ "\${1:-}" == "--version" ]]; then
  printf '%s fixture 1\n' "${grt_tool}"
fi
exit 0
EOF
done

cat > "${FAKE_BIN}/zip" <<'PYZIP'
#!/usr/bin/env python3
import fnmatch
import os
from pathlib import Path
import sys
import zipfile

arguments = sys.argv[1:]
roots = []
excludes = []
output = None
index = 0
while index < len(arguments):
    value = arguments[index]
    if value == "-r":
        index += 1
    elif value == "-x":
        excludes.append(arguments[index + 1])
        index += 2
    elif value.startswith("-"):
        index += 1
    elif output is None:
        output = Path(value).resolve()
        index += 1
    else:
        roots.append(Path(value))
        index += 1
if output is None:
    raise SystemExit(1)
output.parent.mkdir(parents=True, exist_ok=True)
listing = bytearray()
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in paths:
            arcname = path.as_posix()
            if any(fnmatch.fnmatch(arcname, pattern) for pattern in excludes):
                continue
            archive.write(path, arcname)
            listing.extend(f"--- {arcname}\n".encode())
            listing.extend(path.read_bytes())
            listing.extend(b"\n")
    archive.writestr("__fake_zip_listing__.txt", listing)
PYZIP

chmod +x "${FAKE_BIN}/samtools" "${FAKE_BIN}/minimap2" "${FAKE_BIN}/zip" \
  "${FAKE_BIN}/nucmer" "${FAKE_BIN}/delta-filter" "${FAKE_BIN}/show-coords"

fixture_sequence() {
  # Controlled, matching prefixes of one non-repetitive reference. This tests
  # add/import orchestration, not acceptance of low-complexity q0 anchors.
  python3 - "$1" "${2:-0}" <<'PYSEQ'
import random
import sys
length, offset = map(int, sys.argv[1:])
rng = random.Random(831)
print("".join(rng.choice("ACGT") for _ in range(length + offset))[offset:])
PYSEQ
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

write_fasta "$ref" "Chr01" "$(fixture_sequence 1500)"
write_fasta "$ds1" "ds1_ctg" "$(fixture_sequence 1200)"
write_fasta "$ds4" "ds4_ctg" "$(fixture_sequence 400)NNNN$(fixture_sequence 796 404)"

PATH="${FAKE_BIN}:$PATH" bash "$SCRIPT" --archive-format zip \
  --ref ref_add_script "$ref" \
  --ds ds1 "$ds1" \
  --skip-self \
  --score 71 \
  --minimap-preset asm5 \
  -o "$output_root" >/dev/null

test -x "${output_root}/.runtime/commands/add_dataset.sh"
add_dataset_help="$(bash "${output_root}/.runtime/commands/add_dataset.sh" --help)"
grep -F -- '--ds [<dataset_name>] <dataset_fasta_path>' <<<"$add_dataset_help" >/dev/null
grep -F -- 'FASTA basename: .gz and' <<<"$add_dataset_help" >/dev/null
grep -F -- 'one .fa, .fasta, or .fna suffix are removed case-insensitively' <<<"$add_dataset_help" >/dev/null
grep -F -- 'A-Z, a-z, 0-9, dot, underscore, and hyphen are replaced with _' <<<"$add_dataset_help" >/dev/null

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/run_all.sh" > "${TMP_DIR}/initial-run.out"

test -f "${output_root}/07_delivery/00_lgz/gpm_server.zip"
test -f "${output_root}/07_delivery/00_lgz/gpm_server.light.zip"
assert_file_contains "${output_root}/07_delivery/00_lgz/gpm_server.zip" "--- gpm_server/data/datasets/ds1.fa"
assert_file_not_contains "${output_root}/07_delivery/00_lgz/gpm_server.light.zip" '^--- gpm_server/data/datasets/ds1[.]fa$'
assert_file_contains "${output_root}/07_delivery/00_lgz/gpm_server.light.zip" "--- gpm_server/data/datasets/ds1.fa.fai"
python3 - "${output_root}/07_delivery/00_lgz/gpm_server.zip" "${output_root}/07_delivery/00_lgz/gpm_server.light.zip" <<'PY'
import sys
from zipfile import ZipFile

required = {
    "gpm_server/report/report.html",
    "gpm_server/report/manifest.json",
    "gpm_server/report/render_report.py",
}
for archive_path in sys.argv[1:]:
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None, archive_path
        assert required.issubset(archive.namelist()), archive_path
PY
test ! -e "${TMP_DIR}/gpm_server.report.zip"
test ! -e "${TMP_DIR}/gpm_server.report.html"
grep -Fq 'LGZ baseline App packages (not refined):' "${TMP_DIR}/initial-run.out"
grep -Fq 'Full package (FASTA + report):' "${output_root}/.runtime/logs/run_all.log"
grep -Fq 'Light package (report included, FASTA omitted):' "${output_root}/.runtime/logs/run_all.log"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/run_all.sh" --log-style detailed > "${TMP_DIR}/resume.out"
grep -Fq '[SKIP_VALID] [ref:ds1]' "${TMP_DIR}/resume.out"
grep -Fq '[SKIP_VALID] [assign]' "${TMP_DIR}/resume.out"
grep -Fq '[SKIP_VALID] [chr:Chr01]' "${TMP_DIR}/resume.out"
grep -Fq '[CACHE_HIT] [grt_prepare]' "${TMP_DIR}/resume.out"
grep -Fq '[CACHE_HIT] [grt_step1]' "${TMP_DIR}/resume.out"
grep -Fq '[CACHE_HIT] [grt_step1]' "${TMP_DIR}/resume.out"
grep -Fq '[CACHE_HIT] [grt_step2]' "${TMP_DIR}/resume.out"
grep -Fq '[CACHE_HIT] [grt_step3]' "${TMP_DIR}/resume.out"
awk -F '\t' '
  $1 == "ref:ds1" || $1 == "assign" || $1 == "chr:Chr01" {
    if ($4 != "success" || $5 != "1") exit 1
    seen += 1
  }
  END { exit seen == 3 ? 0 : 1 }
' "${output_root}/.runtime/logs/status.tsv"

awk -F '\t' 'BEGIN { OFS = "\t" } $1 == "chr_assignment_min_coverage_percent" { $2 = "72" } { print }' \
  "${output_root}/.runtime/metadata/prepare_options.tsv" > "${output_root}/.runtime/metadata/prepare_options.tsv.tmp"
mv "${output_root}/.runtime/metadata/prepare_options.tsv.tmp" "${output_root}/.runtime/metadata/prepare_options.tsv"

# Adding display data must not rewrite the original q0/final sequence or
# retroactively enlist the dataset in its locked recipe and donor freeze.
frozen_before="$(sha256sum "${output_root}/.runtime/metadata/grt_q0_freeze.json" \
  "${output_root}/.runtime/metadata/grt_recipe.tsv" "${output_root}/03_lgz/01_q0/q0.fa" "${output_root}/03_lgz/04_step3/q3.fa")"
PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/add_dataset.sh" --ds "$ds4" >/dev/null
[[ "$frozen_before" == "$(sha256sum "${output_root}/.runtime/metadata/grt_q0_freeze.json" \
  "${output_root}/.runtime/metadata/grt_recipe.tsv" "${output_root}/03_lgz/01_q0/q0.fa" "${output_root}/03_lgz/04_step3/q3.fa")" ]]

test -f "${output_root}/add_ds4.zip"
grep -q '^gpm_grt_precomputed_v2' "${output_root}/.runtime/metadata/package.tsv"
grep -q $'^recipe-.*\tds1\t\[\]\tfalse\t' "${output_root}/.runtime/metadata/grt_recipe.tsv"
grep -q $'^ds4\t' "${output_root}/.runtime/metadata/datasets.tsv"
grep -q $'^ds4\tds4_ctg\t' "${output_root}/.runtime/metadata/chr_assignments.tsv"
grep -q $'^ds4\tds4_ctg\t401\t404\t4$' "${output_root}/.runtime/metadata/source_seq_n_regions.tsv"
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
python3 - "${output_root}/add_ds4.zip" <<'PYAPP'
import csv
import io
import sys
from zipfile import ZipFile
with ZipFile(sys.argv[1]) as archive:
    assert archive.testzip() is None
    names = set(archive.namelist())
    assert not any(name.startswith(("gpm_server/01_inputs/", "gpm_server/02_alignments/", "gpm_server/.runtime/")) for name in names)
    for table, fields in (("datasets.tsv", ("fasta_relpath", "fai_relpath")),
                          ("source_seq_locator.tsv", ("fasta_relpath",))):
        text = archive.read(f"gpm_server/metadata/{table}").decode()
        rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
        assert len(rows) == 1 and rows[0]["dataset_name"] == "ds4", rows
        for field in fields:
            assert "gpm_server/" + rows[0][field] in names, (field, rows[0])
PYAPP

if PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/add_dataset.sh" --ds ds4 "$ds4" >"${TMP_DIR}/duplicate.out" 2>&1; then
  echo "duplicate dataset add should fail" >&2
  exit 1
fi
assert_file_contains "${TMP_DIR}/duplicate.out" "Duplicate dataset name: ds4"

PATH="${FAKE_BIN}:$PATH" bash "${output_root}/.runtime/commands/package_full_zip.sh" >/dev/null
test -f "${output_root}/07_delivery/00_lgz/gpm_server.zip"
assert_file_contains "${output_root}/07_delivery/00_lgz/gpm_server.zip" "metadata/datasets.tsv"
assert_file_contains "${output_root}/07_delivery/00_lgz/gpm_server.zip" $'ds4\tds4\t'

echo "gpm_server_add_dataset_test.sh: ok"
