#!/usr/bin/env bash
# Manage only the user-local annotation library; official entries are read-only.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
case "${1:---help}" in
  list|add-tel|add-cen|remove) ;;
  -h|--help)
    cat <<'HELP'
Usage: bash library.sh <command>
  list [tel|cen]                              Show official + local entries and notes
  add-tel <motif> <min_repeat> [--note <text>] Add a local tel rule
  add-cen <repeats.fa> [--note <text>]         Copy repeats into the local cen library
  remove <local_id>                          Remove a local entry (official entries are read-only)
Notes may be empty. To edit an entry, remove then add it again.
Updates never replace local/library/. Existing projects keep their prepared snapshot.
HELP
    exit 0 ;;
  *) printf 'ERROR: unknown library command; see library.sh --help\n' >&2; exit 2 ;;
esac
exec python3 "${SCRIPT_DIR}/tools/annotation_library.py" --server-root "$SCRIPT_DIR" "$@"
