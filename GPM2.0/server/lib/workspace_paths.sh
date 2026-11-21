#!/usr/bin/env bash
# Resolve physical workspace paths through the same manifest as the Python tools.
# This file can be sourced from an installation or from a prepared runtime.
cgat_layout_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cgat_layout_tool="${cgat_layout_lib_dir}/../tools/workspace_layout.py"

cgat_workspace_path() {
  python3 "$cgat_layout_tool" --server-dir "$1" --path "$2"
}

cgat_workspace_relative() {
  python3 "$cgat_layout_tool" --server-dir "$1" --relative "$2"
}
