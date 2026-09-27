#!/usr/bin/env python3

"""Stage one dataset and its reference-alignment command."""

import csv
import shlex
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


stage_dir = Path(sys.argv[1])
dataset_name = sys.argv[2]
minimap_preset = sys.argv[3]
threads = sys.argv[4]
skip_self = sys.argv[5].lower() == "true"
metadata_dir = stage_dir / "metadata"

datasets_path = metadata_dir / "datasets.tsv"
with datasets_path.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
if any(row.get("dataset_name") == dataset_name for row in rows):
    fail(f"Duplicate dataset name: {dataset_name}")
fieldnames = [
    "dataset_name",
    "assembler",
    "assembler_version",
    "fasta_relpath",
    "fai_relpath",
    "self_alignment_available",
]
rows.append(
    {
        "dataset_name": dataset_name,
        "assembler": dataset_name,
        "assembler_version": "",
        "fasta_relpath": f"data/datasets/{dataset_name}.fa",
        "fai_relpath": f"data/datasets/{dataset_name}.fa.fai",
        "self_alignment_available": "false" if skip_self else "true",
    }
)
with datasets_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

assign_script = stage_dir / "assign_chr_groups.sh"
text = assign_script.read_text(encoding="utf-8")
replacements = {
    "export GPM_FAST_WORK_ROOT=": shlex.quote(str(stage_dir)),
    "export GPM_FAST_THREADS=": shlex.quote(threads),
    "export GPM_FAST_ALIGNMENT_ENGINE=": "minimap2",
    "export GPM_FAST_MINIMAP_PRESET=": shlex.quote(minimap_preset),
}
updated_lines = []
for line in text.splitlines():
    for prefix, value in replacements.items():
        if line.startswith(prefix):
            line = prefix + value
            break
    updated_lines.append(line)
assign_script.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

ref_path = metadata_dir / "reference.tsv"
with ref_path.open(newline="", encoding="utf-8") as handle:
    reference_rows = list(csv.DictReader(handle, delimiter="\t"))
if len(reference_rows) != 1:
    fail(f"expected exactly one reference row in {ref_path}")
reference_fa = stage_dir / reference_rows[0]["fasta_relpath"]
run_dir = stage_dir / "runs" / f"{dataset_name}_vs_ref"
command_path = run_dir / "command.sh"
dataset_fa = stage_dir / f"data/datasets/{dataset_name}.fa"
lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}"]
args = ["minimap2", "-c", "-x", minimap_preset, "-t", threads, "-o", "result.paf", str(reference_fa), str(dataset_fa)]
lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
command_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
