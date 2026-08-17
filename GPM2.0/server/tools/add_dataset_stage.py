#!/usr/bin/env python3

"""Stage one dataset and its reference-alignment command."""

import csv
import shlex
import sys
from pathlib import Path


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_key_values(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)
    if not rows or rows[0] != ["key", "value"]:
        fail(f"invalid key/value metadata: {path}")
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


stage_dir = Path(sys.argv[1])
server_dir = Path(sys.argv[2])
dataset_name = sys.argv[3]
chr_score = sys.argv[4]
alignment_engine = sys.argv[5]
minimap_preset = sys.argv[6]
blastn_task = sys.argv[7]
blastn_evalue = sys.argv[8]
blastn_dust = sys.argv[9]
winnowmap_preset = sys.argv[10]
winnowmap_kmer = sys.argv[11]
winnowmap_repeat_fraction = sys.argv[12]
threads = sys.argv[13]
skip_self = sys.argv[14].lower() == "true"
metadata_dir = stage_dir / "metadata"
options = read_key_values(metadata_dir / "prepare_options.tsv")

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
    "export GPM_FAST_ALIGNMENT_ENGINE=": shlex.quote(alignment_engine),
    "export GPM_FAST_MINIMAP_PRESET=": shlex.quote(minimap_preset),
    "export GPM_FAST_BLASTN_TASK=": shlex.quote(blastn_task),
    "export GPM_FAST_BLASTN_EVALUE=": shlex.quote(blastn_evalue),
    "export GPM_FAST_BLASTN_DUST=": shlex.quote(blastn_dust),
    "export GPM_FAST_WINNOWMAP_PRESET=": shlex.quote(winnowmap_preset),
    "export GPM_FAST_WINNOWMAP_KMER=": shlex.quote(winnowmap_kmer),
    "export GPM_FAST_WINNOWMAP_REPEAT_FRACTION=": shlex.quote(winnowmap_repeat_fraction),
    "export GPM_FAST_BLAST6_TO_PAF=": shlex.quote(str(stage_dir / ".prepare_lib" / "tools" / "blast6_to_paf.py")),
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
if alignment_engine == "minimap2":
    args = ["minimap2", "-x", minimap_preset, "-t", threads, "-o", "result.paf", str(reference_fa), str(dataset_fa)]
    lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
elif alignment_engine == "blastn":
    outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
    lines.extend(
        [
            "rm -rf blastdb_result",
            "mkdir -p blastdb_result",
            " ".join(shlex.quote(part) for part in ["makeblastdb", "-in", str(reference_fa), "-dbtype", "nucl", "-out", "blastdb_result/target"])
            + " > makeblastdb.stdout.log 2> makeblastdb.stderr.log",
            " ".join(
                shlex.quote(part)
                for part in [
                    "blastn",
                    "-task",
                    blastn_task,
                    "-query",
                    str(dataset_fa),
                    "-db",
                    "blastdb_result/target",
                    "-num_threads",
                    threads,
                    "-dust",
                    blastn_dust,
                    "-evalue",
                    blastn_evalue,
                    "-outfmt",
                    outfmt,
                    "-out",
                    "result.blast6",
                ]
            )
            + " > stdout.log 2> stderr.log",
            " ".join(
                shlex.quote(part)
                for part in [
                    "python3",
                    str(stage_dir / ".prepare_lib" / "tools" / "blast6_to_paf.py"),
                    "--input",
                    "result.blast6",
                    "--output",
                    "result.paf",
                ]
            ),
        ]
    )
elif alignment_engine == "winnowmap":
    lines.extend(
        [
            "rm -rf merylDB_result",
            " ".join(shlex.quote(part) for part in ["meryl", "count", f"k={winnowmap_kmer}", "output", "merylDB_result", str(reference_fa)])
            + " > meryl.stdout.log 2> meryl.stderr.log",
            " ".join(shlex.quote(part) for part in ["meryl", "print", "greater-than", f"distinct={winnowmap_repeat_fraction}", "merylDB_result"])
            + f" > {shlex.quote('repetitive_' + winnowmap_kmer + '_result.txt')}",
            " ".join(
                shlex.quote(part)
                for part in [
                    "winnowmap",
                    "-W",
                    f"repetitive_{winnowmap_kmer}_result.txt",
                    "-x",
                    winnowmap_preset,
                    "-t",
                    threads,
                    str(reference_fa),
                    str(dataset_fa),
                ]
            )
            + " > result.paf 2> stderr.log",
            ": > stdout.log",
        ]
    )
else:
    fail(f"unsupported alignment engine: {alignment_engine}")
command_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
