#!/usr/bin/env python3

import argparse
import csv
import hashlib
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

DERIVED_DATASET = "derived_ctg"


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_key_values(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows or rows[0] != ["key", "value"]:
        fail(f"invalid key/value metadata: {path}")
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


def read_tsv(path):
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def write_tsv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_single_tsv_row(path):
    rows, _fieldnames = read_tsv(path)
    if len(rows) != 1:
        fail(f"expected exactly one row in {path}")
    return rows[0]


def read_fasta_records(path):
    records = []
    name = None
    parts = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    records.append((name, "".join(parts)))
                name = line[1:].split()[0]
                parts = []
                continue
            parts.append(line)
    if name is not None:
        records.append((name, "".join(parts)))
    return records


def write_single_record_fasta(path, name, sequence):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f">{name}\n{sequence}\n")


def write_fasta_index(path):
    rows = []
    name = None
    length = 0
    first_base_offset = None
    line_bases = None
    line_width = None
    with path.open("rb") as handle:
        while True:
            offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            stripped = raw_line.rstrip(b"\r\n")
            if not stripped:
                continue
            if stripped.startswith(b">"):
                if name is not None:
                    rows.append((name, length, first_base_offset, line_bases, line_width))
                name = stripped[1:].split()[0].decode("utf-8")
                length = 0
                first_base_offset = None
                line_bases = None
                line_width = None
                continue
            if name is None:
                fail(f"invalid FASTA sequence before header: {path}")
            bases = len(stripped)
            if first_base_offset is None:
                first_base_offset = offset
                line_bases = bases
                line_width = len(raw_line)
            length += bases
    if name is not None:
        rows.append((name, length, first_base_offset, line_bases, line_width))
    if not rows:
        fail(f"cannot index empty FASTA: {path}")
    with Path(f"{path}.fai").open("w", encoding="utf-8") as handle:
        for row_name, row_length, row_offset, row_bases, row_width in rows:
            handle.write(f"{row_name}\t{row_length}\t{row_offset}\t{row_bases}\t{row_width}\n")


def append_or_create_fasta(path, name, sequence):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if path.exists() and path.stat().st_size > 0 else "w"
    with path.open(mode, encoding="utf-8") as handle:
        handle.write(f">{name}\n{sequence}\n")


def fasta_has_record(path, name):
    if not path.exists():
        return False
    return any(record_name == name for record_name, _sequence in read_fasta_records(path))


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
    total_weight = sum(max(0, weight) for _position, weight in sorted_values)
    if total_weight <= 0:
        return sorted_values[len(sorted_values) // 2][0]
    threshold = (total_weight // 2) + 1
    cumulative = 0
    for position, weight in sorted_values:
        cumulative += max(0, weight)
        if cumulative >= threshold:
            return position
    return sorted_values[-1][0]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_unique_row(path, fieldnames, row, duplicate_predicate, duplicate_message):
    rows, existing_fieldnames = read_tsv(path)
    if existing_fieldnames and existing_fieldnames != fieldnames:
        fail(f"unexpected header in {path}: {existing_fieldnames}")
    if any(duplicate_predicate(existing) for existing in rows):
        fail(duplicate_message)
    rows.append(row)
    write_tsv(path, fieldnames, rows)


def ensure_derived_dataset_row(server_dir, skip_self):
    path = server_dir / "metadata" / "datasets.tsv"
    rows, fieldnames = read_tsv(path)
    expected = [
        "dataset_name",
        "assembler",
        "assembler_version",
        "fasta_relpath",
        "fai_relpath",
        "self_alignment_available",
    ]
    if fieldnames != expected:
        fail(f"unexpected header in {path}: {fieldnames}")
    if any(row.get("dataset_name") == DERIVED_DATASET for row in rows):
        return
    rows.append(
        {
            "dataset_name": DERIVED_DATASET,
            "assembler": DERIVED_DATASET,
            "assembler_version": "",
            "fasta_relpath": f"data/datasets/{DERIVED_DATASET}.fa",
            "fai_relpath": f"data/datasets/{DERIVED_DATASET}.fa.fai",
            "self_alignment_available": "false" if skip_self else "true",
        }
    )
    write_tsv(path, expected, rows)


def find_reference_chr_fasta(server_dir, chr_name):
    rows, _fieldnames = read_tsv(server_dir / "metadata" / "reference_chr_locator.tsv")
    for row in rows:
        if row.get("reference_chr_name") == chr_name:
            relpath = row.get("fasta_relpath", "")
            if not relpath:
                fail(f"metadata/reference_chr_locator.tsv has empty fasta_relpath for {chr_name}")
            path = server_dir / relpath
            if not path.exists():
                fail(f"reference chromosome FASTA is missing: {path}")
            return path
    fail(f"Unknown chromosome for add_ctg: {chr_name}. Run gpm_server/run_all.sh before add_ctg.sh.")


def target_track_member_names(server_dir, chr_name, target_track):
    rows, _fieldnames = read_tsv(server_dir / "metadata" / "chr_assignments.tsv")
    names = [
        row.get("seq_name", "")
        for row in rows
        if row.get("dataset_name") == target_track and row.get("assigned_chr_name") == chr_name
    ]
    return [name for name in names if name]


def chr_dataset_names(server_dir, chr_name):
    rows, _fieldnames = read_tsv(server_dir / "metadata" / "chr_assignments.tsv")
    names = []
    seen = set()
    for row in rows:
        dataset_name = row.get("dataset_name", "")
        if (
            not dataset_name
            or dataset_name == DERIVED_DATASET
            or row.get("assigned_chr_name") != chr_name
            or dataset_name in seen
        ):
            continue
        seen.add(dataset_name)
        names.append(dataset_name)
    return names


def ensure_no_duplicate_ctg(server_dir, ctg_name):
    paths = [
        server_dir / "metadata" / "source_seq_locator.tsv",
        server_dir / "metadata" / "chr_assignments.tsv",
        server_dir / "metadata" / "derived_ctgs.tsv",
    ]
    for path in paths:
        rows, _fieldnames = read_tsv(path)
        for row in rows:
            if row.get("seq_name") == ctg_name or row.get("ctg_name") == ctg_name:
                fail(
                    f"ctg name already exists: {ctg_name}\n"
                    "Please choose a different --ctg name and rerun add_ctg.sh."
                )


def ensure_target_track(server_dir, target_track):
    rows, _fieldnames = read_tsv(server_dir / "metadata" / "datasets.tsv")
    if not any(row.get("dataset_name") == target_track for row in rows):
        fail(f"Unknown --track dataset: {target_track}")
    if target_track == DERIVED_DATASET:
        fail(f"--track must be an existing primary/support dataset, not {DERIVED_DATASET}")


def write_alignment_command(path, run_dir, target_fa, query_fa, options, self_mode=False):
    alignment_engine = options.get("alignment_engine", "minimap2")
    threads = options.get("threads", "10")
    minimap_preset = options.get("minimap_preset", "asm10")
    blastn_task = options.get("blastn_task", "blastn")
    blastn_evalue = options.get("blastn_evalue", "1e-10")
    blastn_dust = options.get("blastn_dust", "no")
    winnowmap_preset = options.get("winnowmap_preset", "asm20")
    winnowmap_kmer = options.get("winnowmap_kmer", "19")
    winnowmap_repeat_fraction = options.get("winnowmap_repeat_fraction", "0.9998")
    blast6_to_paf = server_tool_path(run_dir, "blast6_to_paf.py")

    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd {shlex.quote(str(run_dir))}"]
    if alignment_engine == "minimap2":
        args = ["minimap2", "-x", minimap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, "-o", "result.paf", str(target_fa), str(query_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > stdout.log 2> stderr.log")
    elif alignment_engine == "blastn":
        outfmt = "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen nident gaps"
        lines.extend(
            [
                "rm -rf blastdb_result",
                "mkdir -p blastdb_result",
                " ".join(shlex.quote(part) for part in ["makeblastdb", "-in", str(target_fa), "-dbtype", "nucl", "-out", "blastdb_result/target"])
                + " > makeblastdb.stdout.log 2> makeblastdb.stderr.log",
                " ".join(
                    shlex.quote(part)
                    for part in [
                        "blastn",
                        "-task",
                        blastn_task,
                        "-query",
                        str(query_fa),
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
                        str(blast6_to_paf),
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
                " ".join(shlex.quote(part) for part in ["meryl", "count", f"k={winnowmap_kmer}", "output", "merylDB_result", str(target_fa)])
                + " > meryl.stdout.log 2> meryl.stderr.log",
                " ".join(shlex.quote(part) for part in ["meryl", "print", "greater-than", f"distinct={winnowmap_repeat_fraction}", "merylDB_result"])
                + f" > {shlex.quote('repetitive_' + winnowmap_kmer + '_result.txt')}",
            ]
        )
        args = ["winnowmap", "-W", f"repetitive_{winnowmap_kmer}_result.txt", "-x", winnowmap_preset]
        if self_mode:
            args.append("-X")
        args.extend(["-t", threads, str(target_fa), str(query_fa)])
        lines.append(" ".join(shlex.quote(part) for part in args) + " > result.paf 2> stderr.log")
        lines.append(": > stdout.log")
    else:
        fail(f"unsupported alignment engine: {alignment_engine}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def server_tool_path(run_dir, tool_name):
    current = Path(run_dir)
    while current != current.parent:
        candidate = current / ".prepare_lib" / "tools" / tool_name
        if candidate.exists():
            return candidate
        current = current.parent
    return Path(tool_name)


def parse_ref_paf_assignment(server_dir, ctg_name, chr_name, sequence):
    paf_path = server_dir / "runs" / "add_ctg" / f"{ctg_name}_vs_ref" / "result.paf"
    if not paf_path.exists():
        fail(f"missing add_ctg reference alignment result: {paf_path}")

    seq_length = max(len(sequence), 1)
    intervals = []
    anchor_weights = []
    with paf_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                continue
            if fields[0] != ctg_name or fields[5] != chr_name:
                continue
            try:
                query_start = int(fields[2]) + 1
                query_end = int(fields[3])
                ref_start = int(fields[7]) + 1
                block_length = int(fields[10])
            except ValueError:
                continue
            strand = fields[4]
            if strand not in ("+", "-"):
                continue
            if query_start < 1 or query_end < query_start or ref_start < 1:
                continue
            qualified = block_length >= 1000 or ((block_length * 100.0) / seq_length) >= 25.0
            if not qualified:
                continue
            candidate_anchor = ref_start - query_start + 1 if strand == "+" else ref_start - seq_length + query_end
            intervals.append((query_start, query_end))
            anchor_weights.append((candidate_anchor, block_length))

    if not intervals:
        fail(f"add_ctg reference alignment has no qualified hit for {ctg_name} on {chr_name}")

    support_bp = merged_interval_coverage(intervals)
    support_percent = (support_bp * 100.0) / seq_length
    return {
        "dataset_name": DERIVED_DATASET,
        "seq_name": ctg_name,
        "seq_length_bp": str(seq_length),
        "assigned_chr_name": chr_name,
        "support_bp": str(support_bp),
        "support_percent": f"{support_percent:.3f}",
        "anchor_start": str(weighted_median_of_positions(anchor_weights)),
    }


def write_manifest(server_dir, ctg_name, chr_name, target_track, source, created_at):
    metadata_dir = server_dir / "metadata"
    options = read_key_values(metadata_dir / "prepare_options.tsv")
    reference = read_single_tsv_row(metadata_dir / "reference.tsv")
    manifest_dir = metadata_dir / "add_ctg_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        ("package_type", "add_ctg"),
        ("ctg_name", ctg_name),
        ("derived_dataset", DERIVED_DATASET),
        ("target_chr", chr_name),
        ("target_track", target_track),
        ("source", source),
        ("reference_name", reference.get("reference_name", "")),
        ("alignment_engine", options.get("alignment_engine", "minimap2")),
        ("minimap_preset", options.get("minimap_preset", "asm10")),
        ("blastn_task", options.get("blastn_task", "blastn")),
        ("blastn_evalue", options.get("blastn_evalue", "1e-10")),
        ("blastn_dust", options.get("blastn_dust", "no")),
        ("winnowmap_preset", options.get("winnowmap_preset", "asm20")),
        ("winnowmap_kmer", options.get("winnowmap_kmer", "19")),
        ("winnowmap_repeat_fraction", options.get("winnowmap_repeat_fraction", "0.9998")),
        ("skip_self", options.get("skip_self", "false")),
        ("self_alignment_scope", options.get("self_alignment_scope", "")),
        ("cross_alignment_scope", options.get("cross_alignment_scope", "")),
        ("sequence_layout", options.get("sequence_layout", "")),
        ("preassigned_chr", options.get("preassigned_chr", "")),
        ("contains_fasta", "true"),
        ("created_at", created_at),
    ]
    with (manifest_dir / f"{ctg_name}.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def command_prepare(args):
    server_dir = Path(args.server_dir)
    input_fasta = Path(args.input)
    if input_fasta.suffix.lower() == ".gz" or str(input_fasta).lower().endswith(".fa.gz"):
        fail(".fa.gz inputs are not supported by add_ctg.sh; provide a plain single-sequence FASTA.")
    if "\t" in args.source or "\n" in args.source or "\r" in args.source:
        fail("--source must not contain tabs or newlines")

    metadata_dir = server_dir / "metadata"
    options = read_key_values(metadata_dir / "prepare_options.tsv")
    skip_self = options.get("skip_self", "false").lower() == "true"
    ensure_no_duplicate_ctg(server_dir, args.ctg)
    ensure_target_track(server_dir, args.track)
    reference_chr_fa = find_reference_chr_fasta(server_dir, args.chr)
    member_names = target_track_member_names(server_dir, args.chr, args.track)
    if not member_names:
        fail(f"target track {args.track} has no members on {args.chr}")

    records = read_fasta_records(input_fasta)
    if len(records) != 1:
        fail(f"add_ctg -i must contain exactly one FASTA sequence, found {len(records)}: {input_fasta}")
    _original_name, sequence = records[0]
    if not sequence:
        fail(f"add_ctg -i sequence is empty: {input_fasta}")

    unique_fa = server_dir / "data" / "derived_ctgs" / f"{args.ctg}.fa"
    write_single_record_fasta(unique_fa, args.ctg, sequence)
    write_fasta_index(unique_fa)

    aggregate_fa = server_dir / "data" / "datasets" / f"{DERIVED_DATASET}.fa"
    if not fasta_has_record(aggregate_fa, args.ctg):
        append_or_create_fasta(aggregate_fa, args.ctg, sequence)
    write_fasta_index(aggregate_fa)

    chr_dataset_fa = server_dir / "runs" / f"chr_{args.chr}" / "datasets" / f"{DERIVED_DATASET}.fa"
    if not fasta_has_record(chr_dataset_fa, args.ctg):
        append_or_create_fasta(chr_dataset_fa, args.ctg, sequence)
    write_fasta_index(chr_dataset_fa)

    ensure_derived_dataset_row(server_dir, skip_self)

    ref_run_dir = server_dir / "runs" / "add_ctg" / f"{args.ctg}_vs_ref"
    write_alignment_command(ref_run_dir / "command.sh", ref_run_dir, reference_chr_fa, unique_fa, options)

    if not skip_self:
        for dataset_name in chr_dataset_names(server_dir, args.chr):
            target_chr_fa = server_dir / "runs" / f"chr_{args.chr}" / "datasets" / f"{dataset_name}.fa"
            if not target_chr_fa.exists():
                fail(f"target chromosome FASTA is missing for {dataset_name}: {target_chr_fa}")
            pair_run_dir = server_dir / "runs" / f"chr_{args.chr}" / "add_ctg" / f"{dataset_name}_vs_{args.ctg}"
            pair_query_fa = pair_run_dir / f"{DERIVED_DATASET}.fa"
            write_single_record_fasta(pair_query_fa, args.ctg, sequence)
            write_alignment_command(pair_run_dir / "command.sh", pair_run_dir, target_chr_fa, pair_query_fa, options)


def command_finalize(args):
    server_dir = Path(args.server_dir)
    input_fasta = Path(args.input)
    records = read_fasta_records(server_dir / "data" / "derived_ctgs" / f"{args.ctg}.fa")
    if len(records) != 1:
        fail(f"staged derived FASTA must contain exactly one sequence for {args.ctg}")
    _name, sequence = records[0]
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    assignment_row = parse_ref_paf_assignment(server_dir, args.ctg, args.chr, sequence)
    append_unique_row(
        server_dir / "metadata" / "chr_assignments.tsv",
        ["dataset_name", "seq_name", "seq_length_bp", "assigned_chr_name", "support_bp", "support_percent", "anchor_start"],
        assignment_row,
        lambda row: row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == args.ctg,
        f"ctg name already exists: {args.ctg}\nPlease choose a different --ctg name and rerun add_ctg.sh.",
    )

    rel_unique_fa = f"data/derived_ctgs/{args.ctg}.fa"
    append_unique_row(
        server_dir / "metadata" / "source_seq_locator.tsv",
        ["dataset_name", "seq_name", "fasta_relpath"],
        {"dataset_name": DERIVED_DATASET, "seq_name": args.ctg, "fasta_relpath": rel_unique_fa},
        lambda row: row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == args.ctg,
        f"ctg name already exists: {args.ctg}\nPlease choose a different --ctg name and rerun add_ctg.sh.",
    )

    n_rows, n_fieldnames = read_tsv(server_dir / "metadata" / "source_seq_n_regions.tsv")
    expected_n = ["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"]
    if n_fieldnames and n_fieldnames != expected_n:
        fail(f"unexpected header in metadata/source_seq_n_regions.tsv: {n_fieldnames}")
    n_rows = [
        row
        for row in n_rows
        if not (row.get("dataset_name") == DERIVED_DATASET and row.get("seq_name") == args.ctg)
    ]
    for start_bp, end_bp, length_bp in iter_n_regions(sequence):
        n_rows.append(
            {
                "dataset_name": DERIVED_DATASET,
                "seq_name": args.ctg,
                "start_bp": str(start_bp),
                "end_bp": str(end_bp),
                "length_bp": str(length_bp),
            }
        )
    write_tsv(server_dir / "metadata" / "source_seq_n_regions.tsv", expected_n, n_rows)

    append_unique_row(
        server_dir / "metadata" / "derived_ctgs.tsv",
        ["derived_dataset", "ctg_name", "source", "source_fasta_name", "source_fasta_sha256", "created_at"],
        {
            "derived_dataset": DERIVED_DATASET,
            "ctg_name": args.ctg,
            "source": args.source,
            "source_fasta_name": input_fasta.name,
            "source_fasta_sha256": sha256_file(input_fasta),
            "created_at": created_at,
        },
        lambda row: row.get("derived_dataset") == DERIVED_DATASET and row.get("ctg_name") == args.ctg,
        f"ctg name already exists: {args.ctg}\nPlease choose a different --ctg name and rerun add_ctg.sh.",
    )

    append_unique_row(
        server_dir / "metadata" / "track_members.tsv",
        ["member_dataset", "member_ctg", "target_chr", "target_track", "member_role", "created_at"],
        {
            "member_dataset": DERIVED_DATASET,
            "member_ctg": args.ctg,
            "target_chr": args.chr,
            "target_track": args.track,
            "member_role": "derived",
            "created_at": created_at,
        },
        lambda row: row.get("member_dataset") == DERIVED_DATASET and row.get("member_ctg") == args.ctg,
        f"ctg name already exists: {args.ctg}\nPlease choose a different --ctg name and rerun add_ctg.sh.",
    )

    write_manifest(server_dir, args.ctg, args.chr, args.track, args.source, created_at)


def build_parser():
    parser = argparse.ArgumentParser(description="Stage add_ctg server metadata and run commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--server-dir", required=True)
        command.add_argument("--ctg", required=True)
        command.add_argument("--chr", required=True)
        command.add_argument("--track", required=True)
        command.add_argument("--input", required=True)
        command.add_argument("--source", default="")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "prepare":
        command_prepare(args)
    elif args.command == "finalize":
        command_finalize(args)
    else:
        fail(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
