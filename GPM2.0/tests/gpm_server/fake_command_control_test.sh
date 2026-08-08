#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTROL_HELPER="${REPO_ROOT}/tests/gpm_server/fake_command_control.sh"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_TOOL="${TMP_DIR}/fake-tool"
cat > "$FAKE_TOOL" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source $(printf '%q' "$CONTROL_HELPER")
gpm_fake_before fake-tool "\$@" || exit \$?
if gpm_fake_should_emit_empty fake-tool; then
  printf 'empty\n'
else
  printf 'normal\n'
fi
EOF
chmod +x "$FAKE_TOOL"

control_dir="${TMP_DIR}/control"
GPM_TEST_CONTROL_DIR="$control_dir" "$FAKE_TOOL" first >/dev/null
GPM_TEST_CONTROL_DIR="$control_dir" "$FAKE_TOOL" second argument >/dev/null

[[ "$(<"${control_dir}/counts/fake-tool")" == "2" ]]
grep -F $'fake-tool\t1\t' "${control_dir}/invocations.tsv" >/dev/null
grep -F 'second argument' "${control_dir}/invocations.tsv" >/dev/null

if GPM_TEST_CONTROL_DIR="$control_dir" \
  GPM_TEST_FAIL_TOOL="fake-tool" \
  GPM_TEST_FAIL_ON_INVOCATION="3" \
  GPM_TEST_FAIL_EXIT_CODE="17" \
  "$FAKE_TOOL" should-fail >/dev/null 2>&1; then
  echo "expected controlled fake command failure" >&2
  exit 1
else
  status=$?
  [[ "$status" -eq 17 ]] || {
    echo "expected fake exit 17, got $status" >&2
    exit 1
  }
fi

[[ "$(GPM_TEST_CONTROL_DIR="$control_dir" GPM_TEST_EMPTY_TOOL="fake-tool" "$FAKE_TOOL")" == "empty" ]]

GPM_TEST_CONTROL_DIR="$control_dir" \
  GPM_TEST_DELAY_TOOL="fake-tool" \
  GPM_TEST_DELAY_ON_INVOCATION="5" \
  GPM_TEST_DELAY_SECONDS="30" \
  "$FAKE_TOOL" delayed >"${TMP_DIR}/delayed.out" 2>"${TMP_DIR}/delayed.err" &
delayed_pid=$!

for _ in $(seq 1 100); do
  [[ -f "${control_dir}/ready/fake-tool.5" ]] && break
  sleep 0.02
done
[[ -f "${control_dir}/ready/fake-tool.5" ]] || {
  echo "fake command did not publish its ready marker" >&2
  kill "$delayed_pid" 2>/dev/null || true
  wait "$delayed_pid" 2>/dev/null || true
  exit 1
}
kill -TERM "$delayed_pid"
if wait "$delayed_pid" 2>/dev/null; then
  echo "expected delayed fake command to be terminated" >&2
  exit 1
fi

echo "fake command control tests passed"
