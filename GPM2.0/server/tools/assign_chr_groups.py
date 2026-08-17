#!/usr/bin/env python3

"""Materialize chromosome assignments and chr-local run scripts.

This remains one assignment compiler because weighted placement, partitioned
FASTA output, and the chr-local command graph form one atomic generated result.
The shell entrypoint only supplies a locked environment and then delegates here;
focused Server integration tests exercise minimap2, BLAST, and winnowmap output.
"""

import csv
import os
import shlex
import shutil
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_tsv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_single_tsv_row(path):
    rows = read_tsv_rows(path)
    if len(rows) != 1:
        fail(f"expected exactly one data row in {path}")
    return rows[0]


def read_fasta_records(path):
    records = []
    current_name = None
    current_sequence_parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_name is not None:
                    records.append((current_name, "".join(current_sequence_parts)))
                current_name = line[1:].split()[0]
                current_sequence_parts = []
                continue
            current_sequence_parts.append(line)
    if current_name is not None:
        records.append((current_name, "".join(current_sequence_parts)))
    return records


def merged_interval_coverage(intervals):
    if not intervals:
        return 0
    sorted_intervals = sorted(intervals)
    total = 0
    current_start, current_end = sorted_intervals[0]
    for start, end in sorted_intervals[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start + 1
        current_start, current_end = start, end
    return total + (current_end - current_start + 1)


def weighted_median_of_positions(values):
    sorted_values = sorted(values, key=lambda item: item[0])
    total_weight = sum(max(0, weight) for _, weight in sorted_values)
    if total_weight <= 0:
        return sorted_values[len(sorted_values) // 2][0]

    threshold = (total_weight // 2) + 1
    cumulative = 0
    for position, weight in sorted_values:
        cumulative += max(0, weight)
        if cumulative >= threshold:
            return position
    return sorted_values[-1][0]


def write_selected_fasta(path, ordered_records, selected_names):
    with path.open("w", encoding="utf-8") as handle:
        for name, sequence in ordered_records:
            if name not in selected_names:
                continue
            handle.write(f">{name}\n{sequence}\n")


def write_single_record_fasta(path, name, sequence):
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f">{name}\n{sequence}\n")


def iter_n_regions(sequence):
    index = 0
    while index < len(sequence):
        if sequence[index] not in {"N", "n"}:
            index += 1
            continue
        start = index
        while index < len(sequence) and sequence[index] in {"N", "n"}:
            index += 1
        yield start + 1, index, index - start


def write_run_command_script(path, run_dir, left_fa, right_fa, self_mode, threads, minimap_preset):
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}"]
    if alignment_engine == "minimap2":
        args = ["minimap2", "-x", minimap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, "-o", "result.paf", str(left_fa), str(right_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
    elif alignment_engine == "blastn":
        outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
        lines.extend(
            [
                "rm -rf blastdb_result",
                "mkdir -p blastdb_result",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "makeblastdb",
                        "-in",
                        str(left_fa),
                        "-dbtype",
                        "nucl",
                        "-out",
                        "blastdb_result/target",
                    ]
                )
                + " > makeblastdb.stdout.log 2> makeblastdb.stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "blastn",
                        "-task",
                        blastn_task,
                        "-query",
                        str(right_fa),
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
                        blast6_to_paf,
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
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "meryl",
                        "count",
                        f"k={winnowmap_kmer}",
                        "output",
                        "merylDB_result",
                        str(left_fa),
                    ]
                )
                + " > meryl.stdout.log 2> meryl.stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "meryl",
                        "print",
                        "greater-than",
                        f"distinct={winnowmap_repeat_fraction}",
                        "merylDB_result",
                    ]
                )
                + f" > {shlex.quote('repetitive_' + winnowmap_kmer + '_result.txt')}",
            ]
        )
        args = ["winnowmap", "-W", f"repetitive_{winnowmap_kmer}_result.txt", "-x", winnowmap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, str(left_fa), str(right_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > result.paf 2> stderr.log")
        lines.append(": > stdout.log")
    else:
        fail(f"unsupported alignment engine: {alignment_engine}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tel_scan_command_script(path, run_dir, work_root, chr_name, selected_dataset_fastas):
    args = [str(work_root), chr_name]
    args.extend(f"{dataset_name}={fasta_path}" for dataset_name, fasta_path in selected_dataset_fastas)
    python_invocation = "python3 - " + " ".join(shlex.quote(part) for part in args) + " <<'PY'"
    scanner = r'''import csv
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_rules(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rules = []
    for row in rows:
        rule_id = str(row.get("rule_id", "")).strip()
        motif = str(row.get("motif", "")).strip().upper()
        try:
            min_repeat = int(row.get("min_repeat", ""))
        except ValueError:
            fail(f"invalid tel min_repeat in {path}: {row!r}")
        if not rule_id or not motif or min_repeat < 1:
            fail(f"invalid tel rule in {path}: {row!r}")
        rules.append(
            {
                "rule_id": rule_id,
                "motif": motif,
                "min_repeat": min_repeat,
            }
        )
    return rules


def read_fasta_records(path):
    records = []
    current_name = None
    current_parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_name is not None:
                    records.append((current_name, "".join(current_parts)))
                current_name = line[1:].split()[0]
                current_parts = []
                continue
            current_parts.append(line)
    if current_name is not None:
        records.append((current_name, "".join(current_parts)))
    return records


def reverse_complement(motif):
    table = str.maketrans("ACGTacgt", "TGCAtgca")
    return motif.translate(table)[::-1].upper()


def scan_pattern(sequence, pattern, min_repeat):
    seq = sequence.upper()
    motif = pattern.upper()
    motif_len = len(motif)
    if motif_len < 1:
        return
    index = 0
    limit = len(seq) - motif_len
    while index <= limit:
        count = 0
        while seq[index + count * motif_len : index + (count + 1) * motif_len] == motif:
            count += 1
        if count >= min_repeat:
            start_bp = index + 1
            end_bp = index + count * motif_len
            yield start_bp, end_bp, count
            index += count * motif_len
            continue
        index += 1


def iter_rule_hits(sequence, rule):
    motif = rule["motif"]
    min_repeat = rule["min_repeat"]
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, motif, min_repeat):
        yield start_bp, end_bp, repeat_count, "+"
    rc = reverse_complement(motif)
    if rc == motif:
        return
    for start_bp, end_bp, repeat_count in scan_pattern(sequence, rc, min_repeat):
        yield start_bp, end_bp, repeat_count, "-"


def parse_dataset_specs(values):
    specs = []
    for value in values:
        if "=" not in value:
            fail(f"invalid dataset spec: {value}")
        dataset_name, fasta_path = value.split("=", 1)
        dataset_name = dataset_name.strip()
        fasta = Path(fasta_path)
        if not dataset_name or not fasta.exists():
            fail(f"invalid dataset spec: {value}")
        specs.append((dataset_name, fasta))
    return specs


work_root = Path(sys.argv[1])
chr_name = sys.argv[2]
dataset_specs = parse_dataset_specs(sys.argv[3:])
rules = read_rules(work_root / "tel" / "rules.tsv")
output_dir = work_root / "tel" / f"chr_{chr_name}"
output_dir.mkdir(parents=True, exist_ok=True)

header = [
    "rule_id",
    "dataset_name",
    "seq_name",
    "assigned_chr_name",
    "motif",
    "min_repeat",
    "repeat_count",
    "start_bp",
    "end_bp",
    "strand",
]

for dataset_name, fasta_path in dataset_specs:
    output_path = output_dir / f"{dataset_name}.tsv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        for seq_name, sequence in read_fasta_records(fasta_path):
            for rule in rules:
                for start_bp, end_bp, repeat_count, strand in iter_rule_hits(sequence, rule):
                    writer.writerow(
                        [
                            rule["rule_id"],
                            dataset_name,
                            seq_name,
                            chr_name,
                            rule["motif"],
                            rule["min_repeat"],
                            repeat_count,
                            start_bp,
                            end_bp,
                            strand,
                        ]
                    )
'''
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(run_dir))}\n"
        f"{python_invocation}\n"
        f"{scanner}\n"
        "PY\n",
        encoding="utf-8",
    )


def write_cen_scan_command_script(path, run_dir, work_root, chr_name, selected_dataset_fastas, threads, minimap_preset):
    cen_reference_path = work_root / "cen" / "reference.tsv"
    rows = read_tsv_rows(cen_reference_path)
    cen_row = next((row for row in rows if row.get("chr_name") == chr_name), None)
    if cen_row is None:
        return False

    cen_fasta = work_root / cen_row["fasta_relpath"]
    cen_query_name = cen_row["sequence_name"]
    cen_chr_fasta = run_dir / f"{chr_name}_centromere.fa"
    for name, sequence in read_fasta_records(cen_fasta):
        if name == cen_query_name:
            write_single_record_fasta(cen_chr_fasta, name, sequence)
            break
    else:
        fail(f"missing centromere sequence {cen_query_name} in {cen_fasta}")

    output_dir = work_root / "cen" / f"chr_{chr_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_specs = []
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}", ""]
    for index, (dataset_name, fasta_path) in enumerate(selected_dataset_fastas):
        result_name = "result.paf" if len(selected_dataset_fastas) == 1 else f"result_{dataset_name}.paf"
        result_path = run_dir / result_name
        dataset_specs.append(f"{dataset_name}={result_path}")
        if alignment_engine == "minimap2":
            args = [
                "minimap2",
                "-x",
                minimap_preset,
                "-t",
                threads,
                "-c",
                "--cs",
                "-o",
                result_name,
                str(fasta_path),
                str(cen_chr_fasta),
            ]
            command = " ".join(shlex.quote(part) for part in args)
            lines.append(f"{command} > stdout_{dataset_name}.log 2> stderr_{dataset_name}.log")
        elif alignment_engine == "blastn":
            blast6_name = result_name.replace(".paf", ".blast6")
            db_dir = f"blastdb_{dataset_name}"
            outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
            lines.extend(
                [
                    f"rm -rf {shlex.quote(db_dir)}",
                    f"mkdir -p {shlex.quote(db_dir)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "makeblastdb",
                            "-in",
                            str(fasta_path),
                            "-dbtype",
                            "nucl",
                            "-out",
                            f"{db_dir}/target",
                        ]
                    )
                    + f" > makeblastdb_{dataset_name}.stdout.log 2> makeblastdb_{dataset_name}.stderr.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "blastn",
                            "-task",
                            blastn_task,
                            "-query",
                            str(cen_chr_fasta),
                            "-db",
                            f"{db_dir}/target",
                            "-num_threads",
                            threads,
                            "-dust",
                            blastn_dust,
                            "-evalue",
                            blastn_evalue,
                            "-outfmt",
                            outfmt,
                            "-out",
                            blast6_name,
                        ]
                    )
                    + f" > stdout_{dataset_name}.log 2> stderr_{dataset_name}.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "python3",
                            blast6_to_paf,
                            "--input",
                            blast6_name,
                            "--output",
                            result_name,
                        ]
                    ),
                ]
            )
        elif alignment_engine == "winnowmap":
            meryl_dir = f"merylDB_{dataset_name}"
            repetitive_txt = f"repetitive_{winnowmap_kmer}_{dataset_name}.txt"
            lines.extend(
                [
                    f"rm -rf {shlex.quote(meryl_dir)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "meryl",
                            "count",
                            f"k={winnowmap_kmer}",
                            "output",
                            meryl_dir,
                            str(fasta_path),
                        ]
                    )
                    + f" > meryl_{dataset_name}.stdout.log 2> meryl_{dataset_name}.stderr.log",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "meryl",
                            "print",
                            "greater-than",
                            f"distinct={winnowmap_repeat_fraction}",
                            meryl_dir,
                        ]
                    )
                    + f" > {shlex.quote(repetitive_txt)}",
                    " ".join(
                        shlex.quote(part)
                        for part in [
                            "winnowmap",
                            "-W",
                            repetitive_txt,
                            "-x",
                            winnowmap_preset,
                            "-t",
                            threads,
                            str(fasta_path),
                            str(cen_chr_fasta),
                        ]
                    )
                    + f" > {shlex.quote(result_name)} 2> stderr_{dataset_name}.log",
                    f": > stdout_{dataset_name}.log",
                ]
            )
        else:
            fail(f"unsupported alignment engine: {alignment_engine}")
    args = [
        str(work_root),
        chr_name,
        cen_row["sequence_name"],
        cen_row["min_len"],
        cen_row["min_identity"],
    ]
    args.extend(dataset_specs)
    python_invocation = "python3 - " + " ".join(shlex.quote(part) for part in args) + " <<'PY'"
    parser = r'''import csv
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def parse_dataset_specs(values):
    specs = []
    for value in values:
        if "=" not in value:
            fail(f"invalid dataset spec: {value}")
        dataset_name, paf_path = value.split("=", 1)
        dataset_name = dataset_name.strip()
        paf = Path(paf_path)
        if not dataset_name or not paf.exists():
            fail(f"invalid dataset spec: {value}")
        specs.append((dataset_name, paf))
    return specs


def parse_identity(fields):
    block_length = int(fields[10])
    if block_length <= 0:
        return 0.0
    for tag in fields[12:]:
        parts = tag.split(":", 2)
        if len(parts) != 3:
            continue
        key, tag_type, value = parts
        if key in {"dv", "de"} and tag_type == "f":
            try:
                divergence = float(value)
            except ValueError:
                continue
            return max(0.0, min(100.0, (1.0 - divergence) * 100.0))
    matches = int(fields[9])
    return max(0.0, min(100.0, (matches * 100.0) / block_length))


work_root = Path(sys.argv[1])
chr_name = sys.argv[2]
query_name = sys.argv[3]
min_len = int(sys.argv[4])
min_identity = float(sys.argv[5])
dataset_specs = parse_dataset_specs(sys.argv[6:])
output_dir = work_root / "cen" / f"chr_{chr_name}"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "marks.tsv"

header = [
    "cen_id",
    "chr_name",
    "query_name",
    "dataset_name",
    "ctg_name",
    "ctg_start",
    "ctg_end",
    "strand",
    "align_length",
    "identity",
    "mapq",
]

with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    for dataset_name, paf_path in dataset_specs:
        with paf_path.open(encoding="utf-8") as paf_handle:
            for raw_line in paf_handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 12:
                    continue
                if fields[0] != query_name:
                    continue
                strand = fields[4]
                if strand not in {"+", "-"}:
                    continue
                align_length = int(fields[10])
                identity = parse_identity(fields)
                if align_length < min_len or identity < min_identity:
                    continue
                writer.writerow(
                    [
                        "cen",
                        chr_name,
                        query_name,
                        dataset_name,
                        fields[5],
                        int(fields[7]) + 1,
                        int(fields[8]),
                        strand,
                        align_length,
                        f"{identity:.3f}",
                        fields[11],
                    ]
                )
'''
    lines.extend(["", python_invocation, parser, "PY"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def write_generated_command_script(path, command_paths, chr_name):
    if not command_paths:
        body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"echo {shlex.quote(f'No chr-local alignments to run for {chr_name}.')} >&2\n"
        )
        path.write_text(body, encoding="utf-8")
        return

    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for index, command_path in enumerate(command_paths):
        quoted = shlex.quote(str(command_path))
        if index < len(command_paths) - 1:
            lines.append(f"bash {quoted} && \\")
        else:
            lines.append(f"bash {quoted}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


work_root = Path(os.environ["GPM_FAST_WORK_ROOT"])
threads = os.environ["GPM_FAST_THREADS"]
alignment_engine = os.environ.get("GPM_FAST_ALIGNMENT_ENGINE", "minimap2")
minimap_preset = os.environ["GPM_FAST_MINIMAP_PRESET"]
blastn_task = os.environ.get("GPM_FAST_BLASTN_TASK", "blastn")
blastn_evalue = os.environ.get("GPM_FAST_BLASTN_EVALUE", "1e-10")
blastn_dust = os.environ.get("GPM_FAST_BLASTN_DUST", "no")
winnowmap_preset = os.environ.get("GPM_FAST_WINNOWMAP_PRESET", "asm20")
winnowmap_kmer = os.environ.get("GPM_FAST_WINNOWMAP_KMER", "19")
winnowmap_repeat_fraction = os.environ.get("GPM_FAST_WINNOWMAP_REPEAT_FRACTION", "0.9998")
blast6_to_paf = os.environ.get(
    "GPM_FAST_BLAST6_TO_PAF",
    str(work_root / ".prepare_lib" / "tools" / "blast6_to_paf.py"),
)
metadata_dir = work_root / "metadata"
runs_dir = work_root / "runs"
package = read_single_tsv_row(metadata_dir / "package.tsv")
datasets = read_tsv_rows(metadata_dir / "datasets.tsv")
reference = read_single_tsv_row(metadata_dir / "reference.tsv")

try:
    threshold = float(package["chr_assignment_min_coverage_percent"])
except (KeyError, ValueError) as exc:
    fail(f"invalid chr_assignment_min_coverage_percent in package.tsv: {exc}")

skip_self = package.get("self_alignment_scope", "") == "none"
reference_fasta = work_root / reference["fasta_relpath"]
reference_records = read_fasta_records(reference_fasta)
reference_chr_names = [name for name, _sequence in reference_records]
reference_by_name = {name: sequence for name, sequence in reference_records}
if not reference_chr_names:
    fail(f"reference fasta has no chromosome records: {reference_fasta}")

dataset_infos = {}
dataset_order = []
for row in datasets:
    dataset_name = row["dataset_name"]
    fasta_path = work_root / row["fasta_relpath"]
    ordered_records = read_fasta_records(fasta_path)
    records_by_name = {name: sequence for name, sequence in ordered_records}
    dataset_order.append(dataset_name)
    dataset_infos[dataset_name] = {
        "fasta_path": fasta_path,
        "ordered_records": ordered_records,
        "records_by_name": records_by_name,
    }

candidate_map = {}
for dataset_name in dataset_order:
    paf_path = runs_dir / f"{dataset_name}_vs_ref" / "result.paf"
    if not paf_path.exists():
        fail(f"missing ref alignment result: {paf_path}")
    dataset_info = dataset_infos[dataset_name]
    records_by_name = dataset_info["records_by_name"]
    assert isinstance(records_by_name, dict)

    with paf_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                continue
            query_name = fields[0]
            sequence = records_by_name.get(query_name)
            if sequence is None:
                continue
            seq_length = max(len(sequence), 1)
            query_start = int(fields[2]) + 1
            query_end = int(fields[3])
            strand = fields[4]
            target_name = fields[5]
            ref_start = int(fields[7]) + 1
            block_length = int(fields[10])
            if strand not in ("+", "-"):
                continue
            if target_name not in reference_chr_names:
                continue
            if query_start < 1 or query_end < query_start or ref_start < 1:
                continue
            qualified = block_length >= 1000 or ((block_length * 100.0) / seq_length) >= 25.0
            if not qualified:
                continue
            candidate_anchor = (
                ref_start - query_start + 1
                if strand == "+"
                else ref_start - seq_length + query_end
            )
            key = (dataset_name, query_name, seq_length, target_name)
            bucket = candidate_map.setdefault(
                key,
                {
                    "intervals": [],
                    "anchor_weights": [],
                    "strand_block_bp": {"+": 0, "-": 0},
                },
            )
            bucket["intervals"].append((query_start, query_end))
            bucket["anchor_weights"].append((candidate_anchor, block_length))
            bucket["strand_block_bp"][strand] += block_length

assignment_rows = []
selected_by_chr_dataset = {
    chr_name: {} for chr_name in reference_chr_names
}
for dataset_name in dataset_order:
    dataset_info = dataset_infos[dataset_name]
    ordered_records = dataset_info["ordered_records"]
    assert isinstance(ordered_records, list)
    for seq_name, sequence in ordered_records:
        seq_length = max(len(sequence), 1)
        for chr_name in reference_chr_names:
            key = (dataset_name, seq_name, seq_length, chr_name)
            bucket = candidate_map.get(key)
            if bucket is None:
                continue
            intervals = bucket["intervals"]
            anchor_weights = bucket["anchor_weights"]
            strand_block_bp = bucket["strand_block_bp"]
            assert isinstance(intervals, list)
            assert isinstance(anchor_weights, list)
            assert isinstance(strand_block_bp, dict)
            support_bp = merged_interval_coverage(intervals)
            support_percent = (support_bp * 100.0) / seq_length
            if support_percent < threshold:
                continue
            source_orientation = (
                "-"
                if int(strand_block_bp.get("-", 0)) > int(strand_block_bp.get("+", 0))
                else "+"
            )
            assignment_rows.append(
                {
                    "dataset_name": dataset_name,
                    "seq_name": seq_name,
                    "seq_length_bp": seq_length,
                    "assigned_chr_name": chr_name,
                    "source_orientation": source_orientation,
                    "orientation_source": "ref_alignment",
                    "support_bp": support_bp,
                    "support_percent": f"{support_percent:.3f}",
                    "anchor_start": weighted_median_of_positions(anchor_weights),
                }
            )
            selected_by_chr_dataset.setdefault(chr_name, {}).setdefault(dataset_name, set()).add(seq_name)

chr_assignments_path = metadata_dir / "chr_assignments.tsv"
with chr_assignments_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "source_orientation",
            "orientation_source",
            "support_bp",
            "support_percent",
            "anchor_start",
        ]
    )
    for row in assignment_rows:
        writer.writerow(
            [
                row["dataset_name"],
                row["seq_name"],
                row["seq_length_bp"],
                row["assigned_chr_name"],
                row["source_orientation"],
                row["orientation_source"],
                row["support_bp"],
                row["support_percent"],
                row["anchor_start"],
            ]
        )

reference_chr_dir = work_root / "data" / "reference" / "chrs"
if reference_chr_dir.exists():
    shutil.rmtree(reference_chr_dir)
reference_chr_dir.mkdir(parents=True, exist_ok=True)
for chr_name in reference_chr_names:
    chr_sequence = reference_by_name.get(chr_name)
    if chr_sequence is None:
        fail(f"missing reference sequence for {chr_name}")
    write_single_record_fasta(reference_chr_dir / f"{chr_name}.fa", chr_name, chr_sequence)

reference_locator_path = metadata_dir / "reference_chr_locator.tsv"
with reference_locator_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["reference_chr_name", "fasta_relpath"])
    for chr_name in reference_chr_names:
        writer.writerow([chr_name, f"data/reference/chrs/{chr_name}.fa"])

partition_root = work_root / "data" / "partitions"
partition_chr_root = partition_root / "chr"
partition_unplaced_root = partition_root / "unplaced"
if partition_root.exists():
    shutil.rmtree(partition_root)
partition_chr_root.mkdir(parents=True, exist_ok=True)
partition_unplaced_root.mkdir(parents=True, exist_ok=True)

source_locator_map = {}
for chr_name in reference_chr_names:
    chr_partition_dir = partition_chr_root / chr_name
    chr_partition_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name in dataset_order:
        selected_names = selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set())
        if not selected_names:
            continue
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        partition_fasta = chr_partition_dir / f"{dataset_name}.fa"
        write_selected_fasta(partition_fasta, ordered_records, selected_names)
        relpath = partition_fasta.relative_to(work_root).as_posix()
        for seq_name, _sequence in ordered_records:
            if seq_name in selected_names and (dataset_name, seq_name) not in source_locator_map:
                source_locator_map[(dataset_name, seq_name)] = relpath

for dataset_name in dataset_order:
    dataset_info = dataset_infos[dataset_name]
    ordered_records = dataset_info["ordered_records"]
    assert isinstance(ordered_records, list)
    assigned_names = set()
    for chr_name in reference_chr_names:
        assigned_names.update(selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set()))
    unassigned_names = {seq_name for seq_name, _sequence in ordered_records if seq_name not in assigned_names}
    if unassigned_names:
        unplaced_fasta = partition_unplaced_root / f"{dataset_name}.fa"
        write_selected_fasta(unplaced_fasta, ordered_records, unassigned_names)
        relpath = unplaced_fasta.relative_to(work_root).as_posix()
        for seq_name in unassigned_names:
            source_locator_map[(dataset_name, seq_name)] = relpath

source_locator_path = metadata_dir / "source_seq_locator.tsv"
with source_locator_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["dataset_name", "seq_name", "fasta_relpath"])
    for dataset_name in dataset_order:
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        for seq_name, _sequence in ordered_records:
            relpath = source_locator_map.get((dataset_name, seq_name))
            if relpath is None:
                fail(f"missing source locator for {dataset_name}:{seq_name}")
            writer.writerow([dataset_name, seq_name, relpath])

n_region_path = metadata_dir / "source_seq_n_regions.tsv"
assigned_by_dataset = {}
for chr_datasets in selected_by_chr_dataset.values():
    for dataset_name, selected_names in chr_datasets.items():
        assigned_by_dataset.setdefault(dataset_name, set()).update(selected_names)
with n_region_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"])
    for dataset_name in dataset_order:
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assigned_names = assigned_by_dataset.get(dataset_name, set())
        assert isinstance(ordered_records, list)
        for seq_name, sequence in ordered_records:
            if seq_name not in assigned_names:
                continue
            for start_bp, end_bp, length_bp in iter_n_regions(sequence):
                writer.writerow([dataset_name, seq_name, start_bp, end_bp, length_bp])

for chr_name in reference_chr_names:
    chr_run_dir = runs_dir / f"chr_{chr_name}"
    datasets_dir = chr_run_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    for stale_fasta in datasets_dir.glob("*.fa"):
        stale_fasta.unlink()
    for child in chr_run_dir.iterdir():
        if child.name in {"datasets", "command.sh", "generated_command.sh"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    selected_dataset_fastas = []
    for dataset_name in dataset_order:
        selected_names = selected_by_chr_dataset.get(chr_name, {}).get(dataset_name, set())
        if not selected_names:
            continue
        dataset_info = dataset_infos[dataset_name]
        ordered_records = dataset_info["ordered_records"]
        assert isinstance(ordered_records, list)
        output_fasta = datasets_dir / f"{dataset_name}.fa"
        write_selected_fasta(output_fasta, ordered_records, selected_names)
        selected_dataset_fastas.append((dataset_name, output_fasta))

    command_paths = []
    if not skip_self:
        for dataset_name, output_fasta in selected_dataset_fastas:
            run_dir = chr_run_dir / f"{dataset_name}_vs_self"
            run_dir.mkdir(parents=True, exist_ok=True)
            command_path = run_dir / "command.sh"
            write_run_command_script(
                command_path,
                run_dir,
                output_fasta,
                output_fasta,
                self_mode=True,
                threads=threads,
                minimap_preset=minimap_preset,
            )
            command_paths.append(command_path)

    for left_index, (left_name, left_fasta) in enumerate(selected_dataset_fastas):
        for right_name, right_fasta in selected_dataset_fastas[left_index + 1 :]:
            run_dir = chr_run_dir / f"{left_name}_vs_{right_name}"
            run_dir.mkdir(parents=True, exist_ok=True)
            command_path = run_dir / "command.sh"
            write_run_command_script(
                command_path,
                run_dir,
                left_fasta,
                right_fasta,
                self_mode=False,
                threads=threads,
                minimap_preset=minimap_preset,
            )
            command_paths.append(command_path)

    tel_rules_path = work_root / "tel" / "rules.tsv"
    if tel_rules_path.exists() and selected_dataset_fastas:
        run_dir = chr_run_dir / "tel_scan"
        run_dir.mkdir(parents=True, exist_ok=True)
        command_path = run_dir / "command.sh"
        write_tel_scan_command_script(
            command_path,
            run_dir,
            work_root,
            chr_name,
            selected_dataset_fastas,
        )
        command_paths.append(command_path)

    cen_reference_path = work_root / "cen" / "reference.tsv"
    if cen_reference_path.exists() and selected_dataset_fastas:
        run_dir = chr_run_dir / "cen_scan"
        run_dir.mkdir(parents=True, exist_ok=True)
        command_path = run_dir / "command.sh"
        if write_cen_scan_command_script(
            command_path,
            run_dir,
            work_root,
            chr_name,
            selected_dataset_fastas,
            threads,
            minimap_preset,
        ):
            command_paths.append(command_path)

    write_generated_command_script(chr_run_dir / "generated_command.sh", command_paths, chr_name)
