#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="${REPO_ROOT}/server/tools/blast6_to_paf.py"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "${TMP_DIR}/input.blast6" <<'EOF'
q1	s1	95.0	20	1	0	1	20	40	21	1e-20	80	100	200	19	0
q2	s2	100.0	8	0	0	5	12	3	10	0.0	16	50	60	8	0
EOF

python3 "$TOOL" --input "${TMP_DIR}/input.blast6" --output "${TMP_DIR}/output.paf"

grep -F $'q1\t100\t0\t20\t-\ts1\t200\t20\t40\t19\t20\t255\tdv:f:0.050000' "${TMP_DIR}/output.paf" >/dev/null || {
  echo "expected reverse-strand BLAST row to convert to PAF coordinates" >&2
  cat "${TMP_DIR}/output.paf" >&2
  exit 1
}

grep -F $'q2\t50\t4\t12\t+\ts2\t60\t2\t10\t8\t8\t255\tdv:f:0.000000' "${TMP_DIR}/output.paf" >/dev/null || {
  echo "expected forward-strand BLAST row to convert to PAF coordinates" >&2
  cat "${TMP_DIR}/output.paf" >&2
  exit 1
}

echo "gpm_server_blast6_to_paf_test.sh: ok"
