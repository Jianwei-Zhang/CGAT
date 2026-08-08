#!/usr/bin/env bash

set -euo pipefail

gpm_fake_invocation_matches() {
  local configured_tool="$1"
  local configured_invocation="$2"
  local actual_tool="$3"
  local actual_invocation="$4"

  [[ -n "$configured_tool" && "$configured_tool" == "$actual_tool" ]] || return 1
  [[ -z "$configured_invocation" || "$configured_invocation" == "$actual_invocation" ]]
}

gpm_fake_before() {
  local tool_name="$1"
  shift
  [[ "$tool_name" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "invalid fake tool name: $tool_name" >&2
    return 2
  }

  local control_dir="${GPM_TEST_CONTROL_DIR:?GPM_TEST_CONTROL_DIR is required}"
  local count_dir="${control_dir}/counts"
  local ready_dir="${control_dir}/ready"
  local count_path="${count_dir}/${tool_name}"
  mkdir -p "$count_dir" "$ready_dir"

  local invocation=1
  if [[ -f "$count_path" ]]; then
    invocation=$(( $(<"$count_path") + 1 ))
  fi
  printf '%s\n' "$invocation" > "$count_path"

  local quoted_args=""
  if [[ $# -gt 0 ]]; then
    printf -v quoted_args '%q ' "$@"
    quoted_args="${quoted_args% }"
  fi
  printf '%s\t%s\t%s\t%s\n' \
    "$tool_name" "$invocation" "$$" "$quoted_args" >> "${control_dir}/invocations.tsv"
  : > "${ready_dir}/${tool_name}.${invocation}"

  if gpm_fake_invocation_matches \
    "${GPM_TEST_DELAY_TOOL:-}" \
    "${GPM_TEST_DELAY_ON_INVOCATION:-}" \
    "$tool_name" \
    "$invocation"; then
    sleep "${GPM_TEST_DELAY_SECONDS:-1}"
  fi

  if gpm_fake_invocation_matches \
    "${GPM_TEST_FAIL_TOOL:-}" \
    "${GPM_TEST_FAIL_ON_INVOCATION:-}" \
    "$tool_name" \
    "$invocation"; then
    return "${GPM_TEST_FAIL_EXIT_CODE:-1}"
  fi
}

gpm_fake_should_emit_empty() {
  local tool_name="$1"
  [[ -n "${GPM_TEST_EMPTY_TOOL:-}" && "${GPM_TEST_EMPTY_TOOL}" == "$tool_name" ]]
}
