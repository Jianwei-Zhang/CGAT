#!/usr/bin/env bash

# Shared runtime helpers for prepare.sh and generated incremental scripts.

incremental_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
incremental_base_lib="${incremental_lib_dir}/common.sh"
[[ -f "$incremental_base_lib" ]] || {
  echo "ERROR: Missing Server shell library: $incremental_base_lib" >&2
  exit 1
}
# shellcheck source=common.sh
source "$incremental_base_lib"

validate_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || die "Invalid name '$value'. Use only letters, numbers, dot, underscore, and hyphen."
}

ensure_readable_file() {
  local path="$1"
  [[ -f "$path" ]] || die "File not found: $path"
  [[ -r "$path" ]] || die "File is not readable: $path"
}

resolve_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$(pwd)/$path"
  fi
}

read_prepare_option() {
  local key="$1"
  awk -F '\t' -v key="$key" '
    NR == 1 { next }
    $1 == key { print $2; found = 1; exit }
    END { if (!found) exit 1 }
  ' "${server_dir}/metadata/prepare_options.tsv"
}

materialize_fasta_input() {
  local src="$1"
  local dst="$2"
  case "${src,,}" in
    *.gz)
      gzip -dc -- "$src" > "$dst" || die "Failed to decompress gzip FASTA: $src"
      ;;
    *)
      cp -f "$src" "$dst"
      ;;
  esac
}

ensure_fai() {
  local fasta="$1"
  rm -f "${fasta}.fai"
  samtools faidx "$fasta"
}
