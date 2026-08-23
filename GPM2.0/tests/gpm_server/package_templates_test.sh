#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TMP_DIR"' EXIT

FAKE_BIN="${TMP_DIR}/bin"
SERVER_DIR="${TMP_DIR}/gpm_server"
mkdir -p "$FAKE_BIN" "${SERVER_DIR}/.prepare_lib/tools" "${SERVER_DIR}/data/datasets" "${SERVER_DIR}/metadata"

cat > "${FAKE_BIN}/zip" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

archive=""
declare -a roots=()
declare -a excludes=()
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
      if [[ -z "$archive" ]]; then
        archive="$1"
      else
        roots+=("$1")
      fi
      shift
      ;;
  esac
done

[[ -n "$archive" ]]
mkdir -p "$(dirname "$archive")"
if [[ ! -e "$archive" ]]; then
  : > "$archive"
fi
if [[ "${FAKE_ZIP_FAIL:-false}" == "true" ]]; then
  printf 'partial archive\n' >> "$archive"
  exit 23
fi

if [[ "${#roots[@]}" -gt 0 ]]; then
  for root in "${roots[@]}"; do
    while IFS= read -r path; do
      skip=false
      if [[ "${#excludes[@]}" -gt 0 ]]; then
        for pattern in "${excludes[@]}"; do
          if [[ "$path" == $pattern ]]; then
            skip=true
            break
          fi
        done
      fi
      "$skip" && continue
      printf '%s\n' "--- $path" >> "$archive"
    done < <(find "$root" -type f | LC_ALL=C sort)
  done
fi
EOF
chmod +x "${FAKE_BIN}/zip"

cat > "${SERVER_DIR}/.prepare_lib/tools/grt_contract.py" <<'PY'
import os
import sys

if os.environ.get("FAKE_CONTRACT_FAIL") == "true":
    raise SystemExit(2)
sys.stdout.write('{"valid":true}\n')
PY

cat > "${SERVER_DIR}/.prepare_lib/tools/grt_app_package.py" <<'PY'
import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--staging', type=Path, required=True)
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument('--include-fasta', action='store_true')
mode.add_argument('--no-fasta', action='store_true')
args = parser.parse_args()
if args.staging.exists():
    shutil.rmtree(args.staging)
args.staging.mkdir(parents=True)
for source in args.source.rglob('*'):
    if not source.is_file() or '.prepare_lib' in source.parts:
        continue
    if args.no_fasta and source.suffix.lower() in {'.fa', '.fasta'}:
        continue
    target = args.staging / source.relative_to(args.source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
PY

cp "${REPO_ROOT}/server/templates/package_full_zip.sh" "${SERVER_DIR}/package_full_zip.sh"
cp "${REPO_ROOT}/server/templates/package_light_no_fasta_zip.sh" "${SERVER_DIR}/package_light_no_fasta_zip.sh"
chmod +x "${SERVER_DIR}/package_full_zip.sh" "${SERVER_DIR}/package_light_no_fasta_zip.sh"

printf '>example\nACGT\n' > "${SERVER_DIR}/data/datasets/example.fa"
printf 'example\t4\t0\t4\t5\n' > "${SERVER_DIR}/data/datasets/example.fa.fai"
printf 'key\tvalue\n' > "${SERVER_DIR}/metadata/state.tsv"

PATH="${FAKE_BIN}:$PATH" bash "${SERVER_DIR}/package_full_zip.sh" >/dev/null
FULL_ARCHIVE="${TMP_DIR}/gpm_server.zip"
LIGHT_ARCHIVE="${TMP_DIR}/gpm_server.no_fasta.zip"
[[ -f "$FULL_ARCHIVE" ]]
grep -Fx -- '--- gpm_server/data/datasets/example.fa' "$FULL_ARCHIVE" >/dev/null

printf '%s\n' '--- stale/removed.fa' >> "$FULL_ARCHIVE"
PATH="${FAKE_BIN}:$PATH" bash "${SERVER_DIR}/package_full_zip.sh" >/dev/null
if grep -Fx -- '--- stale/removed.fa' "$FULL_ARCHIVE" >/dev/null; then
  echo "full packager updated an old archive instead of replacing it" >&2
  exit 1
fi

full_before_failure="$(sha256sum "$FULL_ARCHIVE" | awk '{print $1}')"
if PATH="${FAKE_BIN}:$PATH" FAKE_ZIP_FAIL=true bash "${SERVER_DIR}/package_full_zip.sh" >/dev/null 2>&1; then
  echo "expected simulated full zip failure" >&2
  exit 1
fi
full_after_zip_failure="$(sha256sum "$FULL_ARCHIVE" | awk '{print $1}')"
[[ "$full_after_zip_failure" == "$full_before_failure" ]]

if PATH="${FAKE_BIN}:$PATH" FAKE_CONTRACT_FAIL=true bash "${SERVER_DIR}/package_full_zip.sh" >/dev/null 2>&1; then
  echo "expected simulated contract validation failure" >&2
  exit 1
fi
full_after_contract_failure="$(sha256sum "$FULL_ARCHIVE" | awk '{print $1}')"
[[ "$full_after_contract_failure" == "$full_before_failure" ]]

PATH="${FAKE_BIN}:$PATH" bash "${SERVER_DIR}/package_light_no_fasta_zip.sh" >/dev/null
[[ -f "$LIGHT_ARCHIVE" ]]
if grep -Fx -- '--- gpm_server/data/datasets/example.fa' "$LIGHT_ARCHIVE" >/dev/null; then
  echo "light archive contains a FASTA payload" >&2
  exit 1
fi
grep -Fx -- '--- gpm_server/data/datasets/example.fa.fai' "$LIGHT_ARCHIVE" >/dev/null

light_before_failure="$(sha256sum "$LIGHT_ARCHIVE" | awk '{print $1}')"
if PATH="${FAKE_BIN}:$PATH" FAKE_ZIP_FAIL=true bash "${SERVER_DIR}/package_light_no_fasta_zip.sh" >/dev/null 2>&1; then
  echo "expected simulated light zip failure" >&2
  exit 1
fi
light_after_failure="$(sha256sum "$LIGHT_ARCHIVE" | awk '{print $1}')"
[[ "$light_after_failure" == "$light_before_failure" ]]

if find "$TMP_DIR" -maxdepth 1 -type d -name '.gpm_server.package-*' -print -quit | grep -q .; then
  echo "package script left a temporary directory behind" >&2
  exit 1
fi

echo "gpm_server_package_templates_test.sh: ok"
