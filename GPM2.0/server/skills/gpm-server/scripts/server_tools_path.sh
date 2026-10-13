#!/usr/bin/env bash
# Resolve the recorded Server tools location, or explicitly bind an installed copy.
set -euo pipefail
SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOCATION_FILE="$SKILL_DIR/server-tools.path"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

validate_server() {
  local candidate="$1" root relative
  [[ -d "$candidate" ]] || fail "Recorded Server directory is unavailable: $candidate. Bind its actual absolute path with --set; no directory search was performed."
  root="$(cd -- "$candidate" && pwd -P)"
  for relative in run.sh prepare.sh install.sh tools/server_run.py; do
    [[ -f "$root/$relative" && -r "$root/$relative" ]] || fail "Not a complete companion Server tools directory: $root (missing $relative)."
  done
  [[ -d "$root/tools/grt_core" ]] || fail "Not a complete companion Server tools directory: $root (missing tools/grt_core)."
  printf '%s\n' "$root"
}

case "${1:-}" in
  --help|-h)
    [[ $# == 1 ]] || fail "Use --help without other arguments."
    printf '%s\n' 'Usage: bash server_tools_path.sh [--set /absolute/path/to/Server]' \
      'No arguments: validate and print the location recorded in server-tools.path.' \
      '--set: validate and record an absolute location for this skill installation.'
    exit 0
    ;;
  --set)
    [[ $# == 2 ]] || fail "--set requires one absolute Server directory."
    [[ "$2" == /* && "$2" != *$'\n'* && "$2" != *$'\r'* ]] || fail "--set requires a single-line absolute path."
    [[ ! -L "$LOCATION_FILE" ]] || fail "Refusing to replace a symlinked server-tools.path."
    resolved="$(validate_server "$2")"
    temporary="$(mktemp "$SKILL_DIR/.server-tools.path.XXXXXX")"
    trap 'rm -f -- "$temporary"' EXIT
    printf '%s\n' "$resolved" > "$temporary"
    mv -f -- "$temporary" "$LOCATION_FILE"
    printf '%s\n' "$resolved"
    exit 0
    ;;
  '') [[ $# == 0 ]] || fail "Unexpected empty argument." ;;
  *) fail "Unknown argument: $1. Use --help." ;;
esac

[[ -r "$LOCATION_FILE" ]] || fail "Missing server-tools.path. Bind the actual Server directory with --set."
mapfile -t recorded < "$LOCATION_FILE"
[[ ${#recorded[@]} == 1 && -n "${recorded[0]}" ]] || fail "server-tools.path must contain exactly one nonempty path line."
[[ "${recorded[0]}" != *$'\r'* ]] || fail "server-tools.path must use LF line endings."
candidate="${recorded[0]}"
if [[ "$candidate" != /* ]]; then
  candidate="$SKILL_DIR/$candidate"
fi
validate_server "$candidate"
