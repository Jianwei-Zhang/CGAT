#!/usr/bin/env python3
"""Build a small example3.zip package for mirror support ds-ctg bridge demos."""

import argparse
import csv
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


REFERENCE_NAME = "rice_IRGSP_1_0"
CHR_NAME = "Chr05"
DEMO_CHR_LENGTH = 7000
SOURCE_CHR_PATH = "gpm_server/data/reference/chrs/Chr05.fa"


@dataclass(frozen=True)
class DemoCtg:
    dataset: str
    name: str
    ref_start: int
    ref_end: int

    @property
    def length(self):
        return self.ref_end - self.ref_start + 1


CTGS = [
    DemoCtg("hifiasm", "hifiasm_demo_ctg1", 1, 2000),
    DemoCtg("hifiasm", "hifiasm_demo_ctg2", 2201, 4200),
    DemoCtg("hifiasm", "hifiasm_demo_ctg3", 4401, 6400),
    DemoCtg("flye", "flye_bridge_gap1_ctg", 1701, 2500),
    DemoCtg("flye", "flye_ctg2_tail", 2501, 4200),
    DemoCtg("flye", "flye_ctg3_same_gap2", 4401, 6400),
    DemoCtg("canu2", "canu2_ctg1_same_gap1", 1, 2000),
    DemoCtg("canu2", "canu2_ctg2_head", 2201, 3900),
    DemoCtg("canu2", "canu2_bridge_gap2_ctg", 3901, 4700),
    DemoCtg("canu2", "canu2_ctg3_tail", 4701, 6400),
]
DATASET_ORDER = ["hifiasm", "flye", "canu2"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build compact example3.zip from a full GPM server zip."
    )
    parser.add_argument(
        "--source-zip",
        default="/mnt/d/Desktop/new_zyy_tel_cen.zip",
        help="Source full gpm_server zip. Default: %(default)s",
    )
    parser.add_argument(
        "--output",
        default="/mnt/d/Desktop/example3.zip",
        help="Output example3 zip path. Default: %(default)s",
    )
    parser.add_argument(
        "--work-dir",
        default="/tmp/gpm_example3_build",
        help="Temporary build directory. Default: %(default)s",
    )
    parser.add_argument(
        "--source-start",
        type=int,
        default=10_000_001,
        help="1-based start coordinate in source Chr05. Default: %(default)s",
    )
    return parser.parse_args()


def read_fasta_record_from_zip(zip_path, member_path, record_name):
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_path) as handle:
            current_name = None
            chunks = []
            for raw_line in handle:
                line = raw_line.decode("ascii").strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if current_name == record_name:
                        break
                    current_name = line[1:].split()[0]
                    chunks = []
                    continue
                if current_name == record_name:
                    chunks.append(line.upper())
            if current_name != record_name or not chunks:
                raise SystemExit(f"record {record_name} not found in {member_path}")
            return "".join(chunks)


def write_fasta(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    fai_rows = []
    offset = 0
    with path.open("w", encoding="ascii", newline="\n") as handle:
        for name, sequence in records:
            header = f">{name}\n"
            handle.write(header)
            offset += len(header.encode("ascii"))
            seq_offset = offset
            for index in range(0, len(sequence), 80):
                line = f"{sequence[index:index + 80]}\n"
                handle.write(line)
                offset += len(line.encode("ascii"))
            line_bases = min(80, len(sequence)) if sequence else 80
            line_width = line_bases + 1
            fai_rows.append((name, len(sequence), seq_offset, line_bases, line_width))
    with Path(f"{path}.fai").open("w", encoding="ascii", newline="\n") as handle:
        for row in fai_rows:
            handle.write("\t".join(str(value) for value in row) + "\n")


def write_tsv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def paf_line(query_name, query_len, target_name, target_len, query_start, query_end, target_start, target_end):
    align_len = query_end - query_start + 1
    return "\t".join(
        [
            query_name,
            str(query_len),
            str(query_start - 1),
            str(query_end),
            "+",
            target_name,
            str(target_len),
            str(target_start - 1),
            str(target_end),
            str(align_len),
            str(align_len),
            "60",
            f"cg:Z:{align_len}M",
        ]
    )


def write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line.rstrip("\n") + "\n")


def relative_dataset_fasta(dataset_name):
    return f"data/datasets/{dataset_name}.fa"


def relative_partition_fasta(dataset_name):
    return f"data/partitions/chr/{CHR_NAME}/{dataset_name}.fa"


def ctgs_for_dataset(dataset_name):
    return [ctg for ctg in CTGS if ctg.dataset == dataset_name]


def ctg_sequence(demo_ref_seq, ctg):
    return demo_ref_seq[ctg.ref_start - 1 : ctg.ref_end]


def overlap_paf_line(query, target):
    overlap_start = max(query.ref_start, target.ref_start)
    overlap_end = min(query.ref_end, target.ref_end)
    if overlap_end < overlap_start:
        return None
    query_start = overlap_start - query.ref_start + 1
    query_end = overlap_end - query.ref_start + 1
    target_start = overlap_start - target.ref_start + 1
    target_end = overlap_end - target.ref_start + 1
    return paf_line(
        query.name,
        query.length,
        target.name,
        target.length,
        query_start,
        query_end,
        target_start,
        target_end,
    )


def pairwise_lines(query_dataset, target_dataset):
    lines = []
    for query in ctgs_for_dataset(query_dataset):
        for target in ctgs_for_dataset(target_dataset):
            line = overlap_paf_line(query, target)
            if line:
                lines.append(line)
    return lines


def write_pairwise_run(bundle_root, query_dataset, target_dataset):
    run_name = (
        f"{query_dataset}_vs_self"
        if query_dataset == target_dataset
        else f"{target_dataset}_vs_{query_dataset}"
    )
    lines = pairwise_lines(query_dataset, target_dataset)
    write_lines(bundle_root / "runs" / f"chr_{CHR_NAME}" / run_name / "result.paf", lines)


def build_package(source_zip, output_zip, work_dir, source_start):
    if source_start < 1:
        raise SystemExit("--source-start must be >= 1")
    source_chr = read_fasta_record_from_zip(source_zip, SOURCE_CHR_PATH, CHR_NAME)
    source_end = source_start + DEMO_CHR_LENGTH - 1
    if source_end > len(source_chr):
        raise SystemExit(
            f"source window {source_start}-{source_end} exceeds {CHR_NAME} length {len(source_chr)}"
        )
    demo_ref_seq = source_chr[source_start - 1 : source_end]

    if work_dir.exists():
        shutil.rmtree(work_dir)
    bundle_root = work_dir / "gpm_server"
    metadata_dir = bundle_root / "metadata"

    reference_records = [(CHR_NAME, demo_ref_seq)]
    write_fasta(bundle_root / "data/reference" / f"{REFERENCE_NAME}.fa", reference_records)
    write_fasta(bundle_root / "data/reference/chrs" / f"{CHR_NAME}.fa", reference_records)

    dataset_records = {}
    for dataset_name in DATASET_ORDER:
        records = [(ctg.name, ctg_sequence(demo_ref_seq, ctg)) for ctg in ctgs_for_dataset(dataset_name)]
        dataset_records[dataset_name] = records
        write_fasta(bundle_root / relative_dataset_fasta(dataset_name), records)
        write_fasta(bundle_root / relative_partition_fasta(dataset_name), records)
        write_fasta(bundle_root / "runs" / f"chr_{CHR_NAME}" / "datasets" / f"{dataset_name}.fa", records)

    write_tsv(
        metadata_dir / "reference.tsv",
        ["reference_name", "species_name", "assembly_label", "fasta_relpath", "fai_relpath"],
        [
            {
                "reference_name": REFERENCE_NAME,
                "species_name": "unknown",
                "assembly_label": "rice_IRGSP_1_0_example3",
                "fasta_relpath": f"data/reference/{REFERENCE_NAME}.fa",
                "fai_relpath": f"data/reference/{REFERENCE_NAME}.fa.fai",
            }
        ],
    )
    write_tsv(
        metadata_dir / "reference_chr_locator.tsv",
        ["reference_chr_name", "fasta_relpath"],
        [{"reference_chr_name": CHR_NAME, "fasta_relpath": f"data/reference/chrs/{CHR_NAME}.fa"}],
    )
    write_tsv(
        metadata_dir / "reference_segments.tsv",
        ["reference_chr_name", "segment_order", "segment_start_bp", "segment_end_bp"],
        [
            {
                "reference_chr_name": CHR_NAME,
                "segment_order": 1,
                "segment_start_bp": 1,
                "segment_end_bp": DEMO_CHR_LENGTH,
            }
        ],
    )
    write_tsv(
        metadata_dir / "datasets.tsv",
        ["dataset_name", "assembler", "assembler_version", "fasta_relpath", "fai_relpath", "self_alignment_available"],
        [
            {
                "dataset_name": dataset_name,
                "assembler": dataset_name,
                "assembler_version": "",
                "fasta_relpath": relative_dataset_fasta(dataset_name),
                "fai_relpath": f"{relative_dataset_fasta(dataset_name)}.fai",
                "self_alignment_available": "true",
            }
            for dataset_name in DATASET_ORDER
        ],
    )
    write_tsv(
        metadata_dir / "package.tsv",
        [
            "package_mode",
            "sequence_layout",
            "preassigned_chr",
            "chr_assignment_min_coverage_percent",
            "self_alignment_scope",
            "cross_alignment_scope",
        ],
        [
            {
                "package_mode": "fast",
                "sequence_layout": "partitioned",
                "preassigned_chr": "true",
                "chr_assignment_min_coverage_percent": "60",
                "self_alignment_scope": "chr_partition",
                "cross_alignment_scope": "chr_partition",
            }
        ],
    )

    write_tsv(
        metadata_dir / "chr_assignments.tsv",
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "support_bp",
            "support_percent",
            "anchor_start",
        ],
        [
            {
                "dataset_name": ctg.dataset,
                "seq_name": ctg.name,
                "seq_length_bp": ctg.length,
                "assigned_chr_name": CHR_NAME,
                "support_bp": ctg.length,
                "support_percent": "100.000",
                "anchor_start": ctg.ref_start,
            }
            for ctg in CTGS
        ],
    )
    write_tsv(
        metadata_dir / "source_seq_locator.tsv",
        ["dataset_name", "seq_name", "fasta_relpath"],
        [
            {
                "dataset_name": ctg.dataset,
                "seq_name": ctg.name,
                "fasta_relpath": relative_partition_fasta(ctg.dataset),
            }
            for ctg in CTGS
        ],
    )
    write_tsv(
        metadata_dir / "source_seq_n_regions.tsv",
        ["dataset_name", "seq_name", "start_bp", "end_bp", "length_bp"],
        [],
    )

    for dataset_name in DATASET_ORDER:
        ref_lines = [
            paf_line(ctg.name, ctg.length, CHR_NAME, DEMO_CHR_LENGTH, 1, ctg.length, ctg.ref_start, ctg.ref_end)
            for ctg in ctgs_for_dataset(dataset_name)
        ]
        write_lines(bundle_root / "runs" / f"{dataset_name}_vs_ref" / "result.paf", ref_lines)
        write_lines(bundle_root / "runs" / f"{dataset_name}_vs_ref" / "stdout.log", [])
        write_lines(bundle_root / "runs" / f"{dataset_name}_vs_ref" / "stderr.log", [])
        write_pairwise_run(bundle_root, dataset_name, dataset_name)

    for query_dataset in DATASET_ORDER:
        for target_dataset in DATASET_ORDER:
            if query_dataset != target_dataset:
                write_pairwise_run(bundle_root, query_dataset, target_dataset)

    write_lines(bundle_root / "README_example3.txt", [
        "example3 mirror support ds-ctg bridge demo",
        f"Source: {source_zip}",
        f"Source window: {CHR_NAME}:{source_start}-{source_end}",
        "Primary ds: hifiasm",
        "Support ds: flye, canu2",
        "hifiasm: ctg1 1-2000, gap1 2001-2200, ctg2 2201-4200, gap2 4201-4400, ctg3 4401-6400",
        "flye: flye_bridge_gap1_ctg spans 1701-2500; flye remains broken at gap2.",
        "canu2: canu2_bridge_gap2_ctg spans 3901-4700; canu2 remains broken at gap1.",
        "Pairwise PAF rows are generated only from true reference-coordinate overlaps.",
    ])

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(work_dir).as_posix())
    return output_zip, bundle_root


def main():
    args = parse_args()
    output_zip, bundle_root = build_package(
        Path(args.source_zip),
        Path(args.output),
        Path(args.work_dir),
        args.source_start,
    )
    print(f"bundle_root={bundle_root}")
    print(f"output_zip={output_zip}")


if __name__ == "__main__":
    main()
