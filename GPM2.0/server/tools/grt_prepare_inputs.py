#!/usr/bin/env python3

"""Build the locked GRT recipe, q0, ordinary donor set, and telomere donor set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable


WORKFLOW = "gpm_grt_precomputed_v1"
SCHEMA_VERSION = "1"
Q_GAP_LENGTH = 100
MIN_DONOR_LENGTH = 1_000
MIN_QV = 30.0
MIN_QC_LENGTH = 100_000
MIN_TELOMERE_BP = 500
DNA_ALPHABET = frozenset("ACGTRYSWKMBDHVN")
COMPLEMENT = str.maketrans(
    "ACGTRYSWKMBDHVN",
    "TGCAYRSWMKVHDBN",
)

Q_SEGMENT_FIELDS = [
    "q_version",
    "chr",
    "segment_id",
    "segment_kind",
    "q_start",
    "q_end",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "source_card_key",
    "evidence_ids_json",
]
DONOR_MEMBER_FIELDS = [
    "donor_set_id",
    "member_id",
    "dataset_name",
    "contig_name",
    "source_start",
    "source_end",
    "orientation",
    "fasta_record_name",
    "sequence_sha256",
]
EVIDENCE_FIELDS = [
    "evidence_id",
    "stage",
    "evidence_type",
    "status",
    "q_version",
    "q_source_sha256",
    "query_artifact_relpath",
    "query_sha256",
    "donor_set_id",
    "target_artifact_relpath",
    "target_sha256",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "target_chr",
    "target_start",
    "target_end",
    "tool",
    "tool_version",
    "preset",
    "parameters_json",
    "raw_artifact_relpath",
    "raw_artifact_sha256",
    "coordinate_system",
    "projection_status",
]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, value: object, length: int = 24) -> str:
    return f"{prefix}-{sha256_bytes(canonical_json(value).encode('utf-8'))[:length]}"


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def read_tsv(path: Path, expected_header: list[str] | None = None) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"required TSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = list(reader.fieldnames or [])
        if expected_header is not None and header != expected_header:
            fail(f"unexpected header in {path}: expected {expected_header}, got {header}")
        return list(reader)


def read_key_values(path: Path) -> dict[str, str]:
    rows = read_tsv(path, ["key", "value"])
    return {row["key"]: row["value"] for row in rows}


def read_fasta(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        fail(f"FASTA is missing: {path}")
    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    name: str | None = None
    parts: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    records.append((name, "".join(parts).upper()))
                name = line[1:].split()[0]
                if not name or name in seen:
                    fail(f"empty or duplicate FASTA ID at {path}:{line_number}: {name!r}")
                seen.add(name)
                parts = []
            else:
                if name is None:
                    fail(f"sequence appears before FASTA header at {path}:{line_number}")
                parts.append(line)
    if name is not None:
        records.append((name, "".join(parts).upper()))
    if not records:
        fail(f"FASTA has no records: {path}")
    return records


def write_fasta(path: Path, records: Iterable[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def merged_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def intervals_cover(container: list[tuple[int, int]], subject: list[tuple[int, int]]) -> bool:
    if not subject:
        return False
    index = 0
    for start, end in subject:
        while index < len(container) and container[index][1] < start:
            index += 1
        if index == len(container) or container[index][0] > start or container[index][1] < end:
            return False
    return True


def path_hashes(paths: Iterable[Path], root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda value: value.as_posix())
    }


def executable_identity(command: str) -> dict[str, str]:
    resolved = shutil.which(command) if "/" not in command else str(Path(command).resolve())
    if not resolved or not Path(resolved).is_file() or not os.access(resolved, os.X_OK):
        fail(f"required executable is unavailable: {command}")
    version = "unknown"
    try:
        completed = subprocess.run(
            [resolved, "--version"], check=False, capture_output=True, text=True, timeout=10
        )
        text = (completed.stdout or completed.stderr).strip()
        if text:
            version = text.splitlines()[0][:200]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {
        "command": command,
        "resolved": str(Path(resolved).resolve()),
        "sha256": sha256_file(Path(resolved)),
        "version": version,
    }


def run_command(command: list[str], cwd: Path, log_prefix: Path) -> None:
    log_prefix.parent.mkdir(parents=True, exist_ok=True)
    log_prefix.with_suffix(".command.txt").write_text(
        shlex.join(command) + "\n", encoding="utf-8", newline=""
    )
    stdout_path = log_prefix.with_suffix(".stdout.log")
    stderr_path = log_prefix.with_suffix(".stderr.log")
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
    if completed.returncode != 0:
        fail(f"command failed ({completed.returncode}): {shlex.join(command)}")


def parse_merqury_qv(path: Path) -> dict[str, float]:
    scores: dict[str, float] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 4:
                fail(f"invalid Merqury QV row at {path}:{line_number}")
            value = 0.0 if fields[3] == "+inf" else float(fields[3])
            if fields[0] in scores:
                fail(f"duplicate Merqury contig score in {path}: {fields[0]}")
            scores[fields[0]] = value
    return scores


def parse_craq_report(path: Path) -> dict[str, float]:
    scores: dict[str, float] = {}
    started = False
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#Chr") or "Avg.CRE(R-AQI)" in line:
                started = True
                continue
            if not started or line.startswith("#"):
                continue
            fields = re.split(r"\s+", line)
            if len(fields) < 6 or fields[0] in {"Genome", "Total", "Summary"}:
                continue
            match = re.search(r"\(([^)]+)\)", fields[-2])
            if match is None:
                fail(f"invalid CRAQ score at {path}:{line_number}")
            if fields[0] in scores:
                fail(f"duplicate CRAQ contig score in {path}: {fields[0]}")
            scores[fields[0]] = float(match.group(1))
    return scores


def run_reads_qc(
    stage_grt: Path,
    server_dir: Path,
    datasets: list[dict[str, str]],
    sequences: dict[tuple[str, str], str],
    reads: list[Path],
    tools: dict[str, dict[str, str]],
    threads: int,
    memory_gb: int,
    kmer_size: int,
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    qc_root = stage_grt / "qc"
    qc_root.mkdir(parents=True, exist_ok=True)
    meryl_db = qc_root / f"reads_{kmer_size}mer.meryl"
    run_command(
        [
            tools["meryl"]["resolved"],
            f"k={kmer_size}",
            "count",
            f"memory={memory_gb}G",
            f"threads={threads}",
            "output",
            str(meryl_db),
            *[str(path) for path in reads],
        ],
        qc_root,
        qc_root / "meryl_count",
    )
    if not meryl_db.exists():
        fail(f"Meryl completed without producing database: {meryl_db}")

    qv_scores: dict[tuple[str, str], float] = {}
    craq_scores: dict[tuple[str, str], float] = {}
    reads_argument = " ".join(str(path) for path in reads)
    for dataset in datasets:
        dataset_name = dataset["dataset_name"]
        dataset_fasta = (server_dir / dataset["fasta_relpath"]).resolve()
        dataset_root = qc_root / dataset_name
        merqury_root = dataset_root / "merqury"
        merqury_root.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(meryl_db, merqury_root), merqury_root / "reads.meryl")
        os.symlink(dataset_fasta, merqury_root / "contigs.fasta")
        run_command(
            [tools["merqury"]["resolved"], "reads.meryl", "contigs.fasta", "merqury_out"],
            merqury_root,
            dataset_root / "merqury",
        )
        expected_qv = merqury_root / "merqury_out.contigs.qv"
        qv_candidates = sorted(merqury_root.rglob("*.qv"))
        if expected_qv.is_file():
            qv_path = expected_qv
        elif len(qv_candidates) == 1:
            qv_path = qv_candidates[0]
        elif not qv_candidates:
            fail(f"Merqury produced no QV file for dataset {dataset_name}")
        else:
            fail(f"Merqury produced ambiguous QV files for dataset {dataset_name}: {qv_candidates}")
        parsed_qv = parse_merqury_qv(qv_path)
        (merqury_root / "reads.meryl").unlink()
        (merqury_root / "contigs.fasta").unlink()

        craq_root = dataset_root / "craq_output"
        craq_root.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                tools["craq"]["resolved"],
                "-g",
                str(dataset_fasta),
                "-sms",
                reads_argument,
                "-t",
                str(threads),
                "-o",
                str(craq_root / dataset_name),
            ],
            dataset_root,
            dataset_root / "craq",
        )
        reports = sorted(
            craq_root.rglob("*.Report"),
            key=lambda path: (0 if path.name == "out_final.Report" else 1, path.as_posix()),
        )
        if not reports:
            fail(f"CRAQ produced no report for dataset {dataset_name}")
        parsed_craq = parse_craq_report(reports[0])

        contig_names = [name for ds, name in sequences if ds == dataset_name]
        missing_qv = sorted(set(contig_names) - set(parsed_qv))
        missing_craq = sorted(set(contig_names) - set(parsed_craq))
        if missing_qv or missing_craq:
            fail(
                f"incomplete reads QC for {dataset_name}: "
                f"missing Merqury={missing_qv}, missing CRAQ={missing_craq}"
            )
        for contig_name in contig_names:
            qv_scores[(dataset_name, contig_name)] = parsed_qv[contig_name]
            craq_scores[(dataset_name, contig_name)] = parsed_craq[contig_name]
    return qv_scores, craq_scores


def load_telomere_rules(server_dir: Path) -> list[dict[str, object]]:
    rules_path = server_dir / "tel" / "rules.tsv"
    rules: list[dict[str, object]] = []
    if rules_path.is_file():
        rows = read_tsv(rules_path, ["rule_id", "motif", "min_repeat", "reverse_complement"])
        for row in rows:
            motif = row["motif"].upper()
            rules.append(
                {
                    "rule_id": row["rule_id"],
                    "motif": motif,
                    "chromosome_min_repeat": int(row["min_repeat"]),
                    "donor_min_repeat": int(row["min_repeat"]),
                    "source": "user",
                }
            )
            if row["reverse_complement"].lower() == "true":
                rules.append(
                    {
                        "rule_id": f"{row['rule_id']}-rc",
                        "motif": reverse_complement(motif),
                        "chromosome_min_repeat": int(row["min_repeat"]),
                        "donor_min_repeat": int(row["min_repeat"]),
                        "source": "user_reverse_complement",
                    }
                )
    else:
        for index, motif in enumerate(("TTTAGGG", "CCCTAAA", "TTAGGG", "CCCTAA"), start=1):
            rules.append(
                {
                    "rule_id": f"grt-default-{index}",
                    "motif": motif,
                    "chromosome_min_repeat": 5,
                    "donor_min_repeat": 20,
                    "source": "grt_default",
                }
            )
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, int, int]] = set()
    for rule in rules:
        key = (
            str(rule["motif"]),
            int(rule["chromosome_min_repeat"]),
            int(rule["donor_min_repeat"]),
        )
        if key not in seen:
            seen.add(key)
            unique.append(rule)
    return unique


def has_telomere_signal(sequence: str, rules: list[dict[str, object]]) -> bool:
    for rule in rules:
        motif = str(rule["motif"])
        minimum = int(rule["donor_min_repeat"])
        for match in re.finditer(f"(?:{re.escape(motif)}){{{minimum},}}", sequence):
            if match.end() - match.start() >= MIN_TELOMERE_BP:
                return True
    return False


def parse_paf(path: Path, known_contigs: set[str], known_chromosomes: set[str]) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                fail(f"invalid PAF row at {path}:{line_number}")
            try:
                query_length = int(fields[1])
                query_start = int(fields[2]) + 1
                query_end = int(fields[3])
                target_start = int(fields[7]) + 1
                target_end = int(fields[8])
                matches = int(fields[9])
                block_length = int(fields[10])
                mapq = int(fields[11])
            except ValueError as exc:
                fail(f"invalid numeric PAF field at {path}:{line_number}: {exc}")
            if fields[0] not in known_contigs or fields[5] not in known_chromosomes:
                continue
            if fields[4] not in {"+", "-"} or query_start < 1 or query_end < query_start:
                fail(f"invalid PAF coordinates/strand at {path}:{line_number}")
            if block_length < 1_000 and (block_length * 100.0) / max(query_length, 1) < 25.0:
                continue
            hits.append(
                {
                    "query": fields[0],
                    "query_length": query_length,
                    "query_start": query_start,
                    "query_end": query_end,
                    "strand": fields[4],
                    "target": fields[5],
                    "target_start": target_start,
                    "target_end": target_end,
                    "matches": matches,
                    "block_length": block_length,
                    "mapq": mapq,
                }
            )
    return hits


def quality_rank(
    key: tuple[str, str],
    sequence: str,
    qv_scores: dict[tuple[str, str], float],
    craq_scores: dict[tuple[str, str], float],
    source_rank: dict[tuple[str, str], tuple[int, int]],
    reads_qc_enabled: bool,
) -> tuple[object, ...]:
    n_fraction = sequence.count("N") / max(len(sequence), 1)
    stable = source_rank[key]
    if reads_qc_enabled:
        return (-qv_scores[key], -craq_scores[key], n_fraction, -len(sequence), *stable)
    return (-len(sequence), n_fraction, *stable)


def assignment_preset(options: dict[str, str]) -> str:
    engine = options.get("alignment_engine", "minimap2")
    if engine == "minimap2":
        return options.get("minimap_preset", "asm10")
    if engine == "winnowmap":
        return options.get("winnowmap_preset", "asm20")
    return options.get("blastn_task", "blastn")


def commit_prepared_outputs(stage_grt: Path, stage_metadata: Path, server_dir: Path) -> None:
    """Replace GRT outputs as one rollback-safe filesystem transaction."""
    target_grt = server_dir / "grt"
    target_metadata = server_dir / "metadata"
    backup_root = stage_grt.parent / "previous"
    backup_metadata = backup_root / "metadata"
    backup_metadata.mkdir(parents=True)
    backup_grt = backup_root / "grt"
    moved_metadata: list[str] = []
    installed_metadata: list[str] = []
    moved_grt = False
    installed_grt = False
    try:
        if target_grt.exists():
            os.replace(target_grt, backup_grt)
            moved_grt = True
        for existing in sorted(target_metadata.glob("grt_*")):
            if not existing.is_file():
                continue
            os.replace(existing, backup_metadata / existing.name)
            moved_metadata.append(existing.name)

        os.replace(stage_grt, target_grt)
        installed_grt = True
        for staged in sorted(stage_metadata.iterdir()):
            os.replace(staged, target_metadata / staged.name)
            installed_metadata.append(staged.name)
    except BaseException:
        if installed_grt and target_grt.exists():
            shutil.rmtree(target_grt)
        for name in installed_metadata:
            installed = target_metadata / name
            if installed.exists():
                installed.unlink()
        if moved_grt and backup_grt.exists():
            os.replace(backup_grt, target_grt)
        for name in moved_metadata:
            backup = backup_metadata / name
            if backup.exists():
                os.replace(backup, target_metadata / name)
        raise


def prepare(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    metadata_dir = server_dir / "metadata"
    if not server_dir.is_dir():
        fail(f"server directory does not exist: {server_dir}")

    package_rows = read_tsv(
        metadata_dir / "package.tsv",
        [
            "workflow",
            "schema_version",
            "package_mode",
            "sequence_layout",
            "preassigned_chr",
            "self_alignment_scope",
            "cross_alignment_scope",
            "chr_assignment_min_coverage_percent",
            "grt_precompute_enabled",
            "recipe_locked",
            "final_path_schema_version",
            "reads_qc_enabled",
        ],
    )
    if len(package_rows) != 1:
        fail("package.tsv must contain exactly one row")
    package = package_rows[0]
    if (
        package["workflow"] != WORKFLOW
        or package["schema_version"] != SCHEMA_VERSION
        or package["final_path_schema_version"] != SCHEMA_VERSION
    ):
        fail(
            f"unsupported package workflow/schema: "
            f"{package['workflow']} schema={package['schema_version']} "
            f"final_path={package['final_path_schema_version']}"
        )
    if package["grt_precompute_enabled"] != "true" or package["recipe_locked"] != "true":
        fail("package must enable locked GRT precompute")

    datasets = read_tsv(
        metadata_dir / "datasets.tsv",
        [
            "dataset_name",
            "assembler",
            "assembler_version",
            "fasta_relpath",
            "fai_relpath",
            "self_alignment_available",
        ],
    )
    if not datasets:
        fail("at least one initial dataset is required")
    reference_rows = read_tsv(
        metadata_dir / "reference.tsv",
        ["reference_name", "species_name", "assembly_label", "fasta_relpath", "fai_relpath"],
    )
    if len(reference_rows) != 1:
        fail("reference.tsv must contain exactly one row")
    reference = reference_rows[0]
    options = read_key_values(metadata_dir / "prepare_options.tsv")
    assignments = read_tsv(
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
    )
    member_orders = read_tsv(
        metadata_dir / "track_member_orders.tsv",
        ["target_track", "target_chr", "member_dataset", "member_ctg", "member_order"],
    )
    source_locators = read_tsv(
        metadata_dir / "source_seq_locator.tsv",
        ["dataset_name", "seq_name", "fasta_relpath"],
    )

    dataset_order = [row["dataset_name"] for row in datasets]
    primary_dataset = dataset_order[0]
    support_datasets = dataset_order[1:]
    sequences: dict[tuple[str, str], str] = {}
    source_rank: dict[tuple[str, str], tuple[int, int]] = {}
    dataset_hashes: dict[str, str] = {}
    for dataset_index, dataset in enumerate(datasets):
        fasta_path = server_dir / dataset["fasta_relpath"]
        dataset_hashes[dataset["dataset_name"]] = sha256_file(fasta_path)
        for contig_index, (contig_name, sequence) in enumerate(read_fasta(fasta_path)):
            key = (dataset["dataset_name"], contig_name)
            if key in sequences:
                fail(f"duplicate source identity: {key[0]}:{key[1]}")
            sequences[key] = sequence
            source_rank[key] = (dataset_index, contig_index)

    locator_keys: set[tuple[str, str]] = set()
    locator_fasta_cache: dict[str, dict[str, str]] = {}
    for row in source_locators:
        key = (row["dataset_name"], row["seq_name"])
        if key in locator_keys or key not in sequences:
            fail(f"duplicate or unknown source locator: {key[0]}:{key[1]}")
        locator_keys.add(key)
        relpath = row["fasta_relpath"]
        if relpath not in locator_fasta_cache:
            locator_fasta_cache[relpath] = dict(read_fasta(server_dir / relpath))
        if locator_fasta_cache[relpath].get(key[1]) != sequences[key]:
            fail(f"source locator sequence differs from dataset FASTA: {key[0]}:{key[1]}")
    if locator_keys != set(sequences):
        missing = sorted(set(sequences) - locator_keys)
        fail(f"source locators do not cover every initial source: {missing}")

    reference_fasta = server_dir / reference["fasta_relpath"]
    reference_records = read_fasta(reference_fasta)
    chromosome_order = [name for name, _sequence in reference_records]
    known_chromosomes = set(chromosome_order)
    reads = [path.resolve() for path in args.reads]
    for path in reads:
        if not path.is_file() or not os.access(path, os.R_OK):
            fail(f"reads file is unavailable: {path}")
    reads_qc_enabled = bool(reads)
    if package["reads_qc_enabled"] != str(reads_qc_enabled).lower():
        fail(
            "package.tsv reads_qc_enabled disagrees with generated GRT prepare command: "
            f"package={package['reads_qc_enabled']}, command={str(reads_qc_enabled).lower()}"
        )
    tools: dict[str, dict[str, str]] = {}
    if reads_qc_enabled:
        tools = {
            "meryl": executable_identity(args.meryl),
            "merqury": executable_identity(args.merqury),
            "craq": executable_identity(args.craq),
        }

    paf_rows: dict[str, list[dict[str, object]]] = {}
    paf_paths: dict[str, Path] = {}
    alignment_versions: dict[str, str] = {}
    for dataset in datasets:
        dataset_name = dataset["dataset_name"]
        paf_path = server_dir / "runs" / f"{dataset_name}_vs_ref" / "result.paf"
        version_path = paf_path.parent / "tool_version.txt"
        if not paf_path.is_file():
            fail(f"global ds-vs-ref PAF is missing: {paf_path}")
        if not version_path.is_file() or not version_path.read_text(encoding="utf-8").strip():
            fail(f"global ds-vs-ref tool version is missing: {version_path}")
        paf_paths[dataset_name] = paf_path
        alignment_versions[dataset_name] = version_path.read_text(encoding="utf-8").strip().splitlines()[0]
        paf_rows[dataset_name] = parse_paf(
            paf_path,
            {contig for dataset_key, contig in sequences if dataset_key == dataset_name},
            known_chromosomes,
        )

    input_files = [
        metadata_dir / "package.tsv",
        metadata_dir / "datasets.tsv",
        metadata_dir / "reference.tsv",
        metadata_dir / "prepare_options.tsv",
        metadata_dir / "chr_assignments.tsv",
        metadata_dir / "track_member_orders.tsv",
        metadata_dir / "source_seq_locator.tsv",
        reference_fasta,
        *[server_dir / row["fasta_relpath"] for row in datasets],
        *[server_dir / relpath for relpath in locator_fasta_cache],
        *paf_paths.values(),
        *[path.parent / "tool_version.txt" for path in paf_paths.values()],
        *reads,
    ]
    if (server_dir / "tel" / "rules.tsv").is_file():
        input_files.append(server_dir / "tel" / "rules.tsv")
    input_identity = []
    for path in input_files:
        label = path.relative_to(server_dir).as_posix() if path.is_relative_to(server_dir) else str(path)
        input_identity.append({"path": label, "sha256": sha256_file(path)})
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "builder_version": 1,
        "inputs": input_identity,
        "reads_qc_enabled": reads_qc_enabled,
        "tools": tools,
        "threads": args.threads,
        "memory_gb": args.memory_gb,
        "kmer_size": args.kmer_size,
        "min_qv": MIN_QV,
        "min_qc_length": MIN_QC_LENGTH,
        "min_donor_length": MIN_DONOR_LENGTH,
        "q_gap_length": Q_GAP_LENGTH,
    }
    fingerprint = sha256_bytes(canonical_json(fingerprint_payload).encode("utf-8"))
    checkpoint_path = server_dir / "grt" / "checkpoints" / "donor_freeze.json"
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            output_hashes = checkpoint.get("output_hashes", {})
            required_directories = checkpoint.get("required_directories", [])
            stage_rows = read_tsv(
                metadata_dir / "grt_stage_status.tsv",
                [
                    "stage",
                    "q_input_version",
                    "q_input_sha256",
                    "q_output_version",
                    "q_output_sha256",
                    "donor_set_id",
                    "status",
                    "checkpoint_relpath",
                    "checkpoint_sha256",
                ],
            )
            stage_checkpoint_matches = (
                len(stage_rows) >= 1
                and stage_rows[0]["stage"] == "donor_freeze"
                and stage_rows[0]["q_input_version"] == "q0"
                and stage_rows[0]["q_input_sha256"] == checkpoint.get("q0_sha256")
                and stage_rows[0]["q_output_version"] == "q0"
                and stage_rows[0]["q_output_sha256"] == checkpoint.get("q0_sha256")
                and stage_rows[0]["donor_set_id"] == checkpoint.get("donor_set_id")
                and stage_rows[0]["status"] == "success"
                and stage_rows[0]["checkpoint_relpath"] == "grt/checkpoints/donor_freeze.json"
                and stage_rows[0]["checkpoint_sha256"] == sha256_file(checkpoint_path)
            )
            if checkpoint.get("input_fingerprint") == fingerprint and output_hashes and stage_checkpoint_matches and all(
                isinstance(relpath, str) and (server_dir / relpath).is_dir()
                for relpath in required_directories
            ) and all(
                (server_dir / relpath).is_file()
                and sha256_file(server_dir / relpath) == expected_hash
                for relpath, expected_hash in output_hashes.items()
            ):
                print(f"GRT prepare inputs are current: {checkpoint_path}")
                return
        except (OSError, ValueError, TypeError, SystemExit):
            pass

    stage_root = Path(tempfile.mkdtemp(prefix=".grt_prepare.", dir=server_dir.parent))
    try:
        stage_grt = stage_root / "grt"
        stage_metadata = stage_root / "metadata"
        stage_metadata.mkdir(parents=True)
        qv_scores: dict[tuple[str, str], float] = {}
        craq_scores: dict[tuple[str, str], float] = {}
        if reads_qc_enabled:
            qv_scores, craq_scores = run_reads_qc(
                stage_grt,
                server_dir,
                datasets,
                sequences,
                reads,
                tools,
                args.threads,
                args.memory_gb,
                args.kmer_size,
            )

        telomere_rules = load_telomere_rules(server_dir)
        assignment_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in assignments:
            key = (row["dataset_name"], row["seq_name"])
            if key in sequences:
                assignment_by_key[key].append(row)
        order_by_key: dict[tuple[str, str, str, str], int] = {}
        for row in member_orders:
            order_key = (
                row["target_track"],
                row["target_chr"],
                row["member_dataset"],
                row["member_ctg"],
            )
            if order_key in order_by_key:
                fail(f"duplicate track member order: {order_key}")
            order_value = int(row["member_order"])
            if order_value < 1:
                fail(f"invalid track member order for {order_key}: {order_value}")
            order_by_key[order_key] = order_value

        qc_pass: dict[tuple[str, str], bool] = {}
        valid_sequence: dict[tuple[str, str], bool] = {}
        tel_signal: dict[tuple[str, str], bool] = {}
        for key, sequence in sequences.items():
            valid_sequence[key] = bool(sequence) and not (set(sequence) - DNA_ALPHABET)
            qc_pass[key] = (
                not reads_qc_enabled
                or len(sequence) >= MIN_QC_LENGTH
                or qv_scores[key] >= MIN_QV
            )
            tel_signal[key] = valid_sequence[key] and has_telomere_signal(sequence, telomere_rules)

        primary_assignments: dict[tuple[str, str], dict[str, str]] = {}
        primary_hits: dict[tuple[str, str], list[dict[str, object]]] = {}
        chromosome_index = {name: index for index, name in enumerate(chromosome_order)}
        for key, rows in assignment_by_key.items():
            if key[0] != primary_dataset:
                continue
            selected = min(
                rows,
                key=lambda row: (
                    -int(row["support_bp"]),
                    -float(row["support_percent"]),
                    chromosome_index.get(row["assigned_chr_name"], len(chromosome_index)),
                ),
            )
            primary_assignments[key] = selected
            hits = [
                hit
                for hit in paf_rows[primary_dataset]
                if hit["query"] == key[1] and hit["target"] == selected["assigned_chr_name"]
            ]
            if not hits:
                fail(f"selected primary assignment has no qualified PAF evidence: {key[0]}:{key[1]}")
            primary_hits[key] = hits

        candidate_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
        for key, assignment in primary_assignments.items():
            sequence = sequences[key]
            if not valid_sequence[key] or not qc_pass[key]:
                continue
            hits = primary_hits[key]
            footprint = merged_intervals(
                (int(hit["target_start"]), int(hit["target_end"])) for hit in hits
            )
            strand_weight = defaultdict(int)
            for hit in hits:
                strand_weight[str(hit["strand"])] += int(hit["block_length"])
            orientation = min(("+", "-"), key=lambda strand: (-strand_weight[strand], strand))
            candidate_by_chr[assignment["assigned_chr_name"]].append(
                {
                    "key": key,
                    "sequence": sequence,
                    "assignment": assignment,
                    "hits": hits,
                    "footprint": footprint,
                    "orientation": orientation,
                    "quality_rank": quality_rank(
                        key, sequence, qv_scores, craq_scores, source_rank, reads_qc_enabled
                    ),
                }
            )

        retained_keys: set[tuple[str, str]] = set()
        redundant_reason: dict[tuple[str, str], str] = {}
        for chromosome, candidates in candidate_by_chr.items():
            for candidate in candidates:
                key = candidate["key"]
                assert isinstance(key, tuple)
                redundant_to: tuple[str, str] | None = None
                for other in candidates:
                    if other is candidate or not intervals_cover(other["footprint"], candidate["footprint"]):
                        continue
                    mutually_covered = intervals_cover(candidate["footprint"], other["footprint"])
                    if mutually_covered and not other["quality_rank"] < candidate["quality_rank"]:
                        continue
                    other_key = other["key"]
                    assert isinstance(other_key, tuple)
                    if redundant_to is None or source_rank[other_key] < source_rank[redundant_to]:
                        redundant_to = other_key
                if redundant_to is None:
                    retained_keys.add(key)
                else:
                    redundant_reason[key] = f"ref_footprint_covered_by:{redundant_to[0]}:{redundant_to[1]}"

        assignment_engine = options.get("alignment_engine", "minimap2")
        ref_hash = sha256_file(reference_fasta)
        q_rows: list[dict[str, object]] = []
        evidence_rows: list[dict[str, object]] = []
        q_records: list[tuple[str, str]] = []
        q_used_keys: set[tuple[str, str]] = set()
        for chromosome in chromosome_order:
            candidates = [
                candidate
                for candidate in candidate_by_chr.get(chromosome, [])
                if candidate["key"] in retained_keys
            ]
            for candidate in candidates:
                member_order_key = (
                    primary_dataset,
                    chromosome,
                    primary_dataset,
                    candidate["key"][1],
                )
                if member_order_key not in order_by_key:
                    fail(f"q0 source has no authoritative track member order: {member_order_key}")
            candidates.sort(
                key=lambda candidate: (
                    order_by_key[
                        (primary_dataset, chromosome, primary_dataset, candidate["key"][1])
                    ],
                    int(candidate["assignment"]["anchor_start"]),
                    source_rank[candidate["key"]],
                )
            )
            if not candidates:
                continue
            q_parts: list[str] = []
            q_position = 1
            for index, candidate in enumerate(candidates, start=1):
                key = candidate["key"]
                assert isinstance(key, tuple)
                if index > 1:
                    gap_id = stable_id("q0-gap", [chromosome, index - 1, index], 16)
                    q_rows.append(
                        {
                            "q_version": "q0",
                            "chr": chromosome,
                            "segment_id": gap_id,
                            "segment_kind": "gap",
                            "q_start": q_position,
                            "q_end": q_position + Q_GAP_LENGTH - 1,
                            "dataset_name": "",
                            "contig_name": "",
                            "source_start": "",
                            "source_end": "",
                            "orientation": "",
                            "source_card_key": "",
                            "evidence_ids_json": "[]",
                        }
                    )
                    q_parts.append("N" * Q_GAP_LENGTH)
                    q_position += Q_GAP_LENGTH
                sequence = str(candidate["sequence"])
                orientation = str(candidate["orientation"])
                oriented = sequence if orientation == "+" else reverse_complement(sequence)
                evidence_id = stable_id("ev-assignment", [*key, chromosome], 20)
                segment_id = stable_id("q0-source", [*key, chromosome], 20)
                source_card_key = f"{key[0]}:{key[1]}:{chromosome}:normal"
                q_rows.append(
                    {
                        "q_version": "q0",
                        "chr": chromosome,
                        "segment_id": segment_id,
                        "segment_kind": "source",
                        "q_start": q_position,
                        "q_end": q_position + len(sequence) - 1,
                        "dataset_name": key[0],
                        "contig_name": key[1],
                        "source_start": 1,
                        "source_end": len(sequence),
                        "orientation": orientation,
                        "source_card_key": source_card_key,
                        "evidence_ids_json": canonical_json([evidence_id]),
                    }
                )
                q_parts.append(oriented)
                q_position += len(sequence)
                q_used_keys.add(key)
                hits = candidate["hits"]
                target_intervals = merged_intervals(
                    (int(hit["target_start"]), int(hit["target_end"])) for hit in hits
                )
                dataset_fasta_rel = next(
                    row["fasta_relpath"] for row in datasets if row["dataset_name"] == key[0]
                )
                paf_rel = paf_paths[key[0]].relative_to(server_dir).as_posix()
                evidence_rows.append(
                    {
                        "evidence_id": evidence_id,
                        "stage": "assignment",
                        "evidence_type": "ref_alignment",
                        "status": "background",
                        "q_version": "",
                        "q_source_sha256": "",
                        "query_artifact_relpath": dataset_fasta_rel,
                        "query_sha256": dataset_hashes[key[0]],
                        "donor_set_id": "",
                        "target_artifact_relpath": reference["fasta_relpath"],
                        "target_sha256": ref_hash,
                        "source_dataset": key[0],
                        "source_contig": key[1],
                        "source_start": 1,
                        "source_end": len(sequence),
                        "orientation": orientation,
                        "target_chr": chromosome,
                        "target_start": min(start for start, _end in target_intervals),
                        "target_end": max(end for _start, end in target_intervals),
                        "tool": assignment_engine,
                        "tool_version": alignment_versions[key[0]],
                        "preset": assignment_preset(options),
                        "parameters_json": canonical_json(
                            {
                                "alignment_engine": assignment_engine,
                                "blastn_dust": options.get("blastn_dust", "no"),
                                "blastn_evalue": options.get("blastn_evalue", "1e-10"),
                                "blastn_task": options.get("blastn_task", "blastn"),
                                "chr_assignment_min_coverage_percent": options.get("chr_assignment_min_coverage_percent", "60"),
                                "minimap_preset": options.get("minimap_preset", "asm10"),
                                "source": "existing_global_ds_vs_ref_paf",
                                "threads": options.get("threads", "10"),
                                "winnowmap_kmer": options.get("winnowmap_kmer", "19"),
                                "winnowmap_preset": options.get("winnowmap_preset", "asm20"),
                                "winnowmap_repeat_fraction": options.get("winnowmap_repeat_fraction", "0.9998"),
                            }
                        ),
                        "raw_artifact_relpath": paf_rel,
                        "raw_artifact_sha256": sha256_file(paf_paths[key[0]]),
                        "coordinate_system": "paf_0_based_half_open",
                        "projection_status": "projected",
                    }
                )
            q_records.append((chromosome, "".join(q_parts)))
        if not q_records:
            fail("primary dataset produced no q-eligible chromosome records")
        q0_path = stage_grt / "q" / "q0.fa"
        write_fasta(q0_path, q_records)

        role_rows: list[dict[str, object]] = []
        quality_rows: list[dict[str, object]] = []
        ordinary_keys: list[tuple[str, str]] = []
        telomere_keys: list[tuple[str, str]] = []
        for key in sorted(sequences, key=lambda value: source_rank[value]):
            sequence = sequences[key]
            if key[0] != primary_dataset:
                q_rejection = "not_primary_dataset"
            elif not valid_sequence[key]:
                q_rejection = "invalid_sequence"
            elif not qc_pass[key]:
                q_rejection = "failed_reads_qc"
            elif key not in primary_assignments:
                q_rejection = "unassigned"
            elif key in redundant_reason:
                q_rejection = redundant_reason[key]
            elif key not in retained_keys:
                q_rejection = "not_selected"
            else:
                q_rejection = ""
            q_eligible = key in q_used_keys

            if not valid_sequence[key]:
                donor_rejection = "invalid_sequence"
            elif len(sequence) < MIN_DONOR_LENGTH:
                donor_rejection = "length_lt_1000"
            elif not qc_pass[key]:
                donor_rejection = "failed_reads_qc"
            elif key in q_used_keys:
                donor_rejection = "same_source_interval_used_by_q0"
            else:
                donor_rejection = ""
            donor_eligible = not donor_rejection
            if donor_eligible:
                ordinary_keys.append(key)

            if not valid_sequence[key]:
                tel_rejection = "invalid_sequence"
            elif not tel_signal[key]:
                tel_rejection = "no_reliable_telomere_repeat"
            else:
                tel_rejection = ""
            tel_eligible = not tel_rejection
            if tel_eligible:
                telomere_keys.append(key)
            role_rows.append(
                {
                    "dataset_name": key[0],
                    "contig_name": key[1],
                    "q_eligible": str(q_eligible).lower(),
                    "donor_eligible": str(donor_eligible).lower(),
                    "tel_donor_eligible": str(tel_eligible).lower(),
                    "q_rejection_reason": q_rejection,
                    "donor_rejection_reason": donor_rejection,
                    "tel_rejection_reason": tel_rejection,
                }
            )
            quality_rows.append(
                {
                    "dataset_name": key[0],
                    "contig_name": key[1],
                    "length_bp": len(sequence),
                    "n_fraction": f"{sequence.count('N') / max(len(sequence), 1):.9f}",
                    "qv": "" if not reads_qc_enabled else f"{qv_scores[key]:.6f}",
                    "craq": "" if not reads_qc_enabled else f"{craq_scores[key]:.6f}",
                    "reads_qc_pass": "not_run" if not reads_qc_enabled else str(qc_pass[key]).lower(),
                }
            )

        ordinary_keys.sort(
            key=lambda key: quality_rank(
                key, sequences[key], qv_scores, craq_scores, source_rank, reads_qc_enabled
            )
        )
        telomere_keys.sort(key=lambda key: source_rank[key])

        def build_donor_set(kind: str, keys: list[tuple[str, str]]) -> tuple[dict[str, object], list[dict[str, object]]]:
            identity = [
                {
                    "dataset": key[0],
                    "contig": key[1],
                    "start": 1,
                    "end": len(sequences[key]),
                    "orientation": "+",
                    "sequence_sha256": sha256_bytes(sequences[key].encode("ascii")),
                }
                for key in keys
            ]
            prefix = "d0" if kind == "ordinary" else "dtel"
            donor_set_id = stable_id(prefix, {"kind": kind, "members": identity})
            member_rows: list[dict[str, object]] = []
            fasta_records: list[tuple[str, str]] = []
            for entry, key in zip(identity, keys):
                member_id = stable_id("member", entry, 20)
                fasta_record = f"grt_{member_id}"
                member_rows.append(
                    {
                        "donor_set_id": donor_set_id,
                        "member_id": member_id,
                        "dataset_name": key[0],
                        "contig_name": key[1],
                        "source_start": 1,
                        "source_end": len(sequences[key]),
                        "orientation": "+",
                        "fasta_record_name": fasta_record,
                        "sequence_sha256": entry["sequence_sha256"],
                    }
                )
                fasta_records.append((fasta_record, sequences[key]))
            fasta_relpath = f"grt/donors/{donor_set_id}.fa"
            manifest_relpath = f"grt/donors/{donor_set_id}.manifest.tsv"
            fasta_path = stage_root / fasta_relpath
            manifest_path = stage_root / manifest_relpath
            write_fasta(fasta_path, fasta_records)
            write_tsv(manifest_path, DONOR_MEMBER_FIELDS, member_rows)
            return (
                {
                    "donor_set_id": donor_set_id,
                    "donor_kind": kind,
                    "manifest_relpath": manifest_relpath,
                    "fasta_relpath": fasta_relpath,
                    "fasta_sha256": sha256_file(fasta_path),
                    "member_count": len(member_rows),
                },
                member_rows,
            )

        ordinary_set, ordinary_members = build_donor_set("ordinary", ordinary_keys)
        telomere_set, telomere_members = build_donor_set("telomere", telomere_keys)
        donor_sets = [ordinary_set, telomere_set]
        donor_members = ordinary_members + telomere_members

        q0_hash = sha256_file(q0_path)
        recipe_id = stable_id(
            "recipe",
            {
                "primary": primary_dataset,
                "support": support_datasets,
                "dataset_hashes": dataset_hashes,
                "reads_qc_enabled": reads_qc_enabled,
                "donor_set_id": ordinary_set["donor_set_id"],
                "tel_donor_set_id": telomere_set["donor_set_id"],
                "q0_sha256": q0_hash,
            },
        )

        metadata_outputs: list[Path] = []
        write_tsv(
            stage_metadata / "grt_recipe.tsv",
            [
                "recipe_id",
                "primary_dataset",
                "support_datasets_json",
                "reads_qc_enabled",
                "donor_set_id",
                "tel_donor_set_id",
                "q0_relpath",
                "final_q_relpath",
            ],
            [
                {
                    "recipe_id": recipe_id,
                    "primary_dataset": primary_dataset,
                    "support_datasets_json": canonical_json(support_datasets),
                    "reads_qc_enabled": str(reads_qc_enabled).lower(),
                    "donor_set_id": ordinary_set["donor_set_id"],
                    "tel_donor_set_id": telomere_set["donor_set_id"],
                    "q0_relpath": "grt/q/q0.fa",
                    "final_q_relpath": "grt/q/q4.fa",
                }
            ],
        )
        write_tsv(
            stage_metadata / "grt_contig_roles.tsv",
            [
                "dataset_name",
                "contig_name",
                "q_eligible",
                "donor_eligible",
                "tel_donor_eligible",
                "q_rejection_reason",
                "donor_rejection_reason",
                "tel_rejection_reason",
            ],
            role_rows,
        )
        write_tsv(stage_metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(
            stage_metadata / "grt_donor_sets.tsv",
            [
                "donor_set_id",
                "donor_kind",
                "manifest_relpath",
                "fasta_relpath",
                "fasta_sha256",
                "member_count",
            ],
            donor_sets,
        )
        write_tsv(stage_metadata / "grt_donor_members.tsv", DONOR_MEMBER_FIELDS, donor_members)
        write_tsv(stage_metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(
            stage_metadata / "grt_contig_quality.tsv",
            ["dataset_name", "contig_name", "length_bp", "n_fraction", "qv", "craq", "reads_qc_pass"],
            quality_rows,
        )
        write_tsv(
            stage_metadata / "grt_telomere_rules.tsv",
            [
                "rule_id",
                "motif",
                "chromosome_min_repeat",
                "donor_min_repeat",
                "min_telomere_bp",
                "source",
            ],
            [
                {
                    **rule,
                    "min_telomere_bp": MIN_TELOMERE_BP,
                }
                for rule in telomere_rules
            ],
        )
        tool_rows = [
            {
                "tool": "grt_prepare_inputs",
                "version": "1",
                "executable": ".prepare_lib/tools/grt_prepare_inputs.py",
            },
            {
                "tool": assignment_engine,
                "version": alignment_versions[primary_dataset],
                "executable": assignment_engine,
            },
        ]
        for name, identity in tools.items():
            tool_rows.append(
                {"tool": name, "version": identity["version"], "executable": identity["resolved"]}
            )
        write_tsv(
            stage_metadata / "grt_tool_versions.tsv",
            ["tool", "version", "executable"],
            tool_rows,
        )
        mutable_stage_metadata = {
            "grt_q_segments.tsv",
            "grt_evidence_registry.tsv",
            "grt_stage_status.tsv",
            "grt_tool_versions.tsv",
        }
        metadata_outputs.extend(
            path
            for path in stage_metadata.iterdir()
            if path.name not in mutable_stage_metadata
        )

        output_files = [
            q0_path,
            *[stage_root / row["fasta_relpath"] for row in donor_sets],
            *[stage_root / row["manifest_relpath"] for row in donor_sets],
            *metadata_outputs,
            *[path for path in stage_grt.rglob("*") if path.is_file()],
        ]
        output_hashes = path_hashes(output_files, stage_root)
        required_directories = [
            path.relative_to(stage_root).as_posix()
            for path in sorted(stage_grt.rglob("*"), key=lambda value: value.as_posix())
            if path.is_dir()
        ]
        checkpoint = {
            "workflow": WORKFLOW,
            "stage": "donor_freeze",
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "recipe_id": recipe_id,
            "donor_set_id": ordinary_set["donor_set_id"],
            "tel_donor_set_id": telomere_set["donor_set_id"],
            "q0_sha256": q0_hash,
            "output_hashes": output_hashes,
            "required_directories": required_directories,
        }
        stage_checkpoint = stage_grt / "checkpoints" / "donor_freeze.json"
        stage_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        stage_checkpoint.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        write_tsv(
            stage_metadata / "grt_stage_status.tsv",
            [
                "stage",
                "q_input_version",
                "q_input_sha256",
                "q_output_version",
                "q_output_sha256",
                "donor_set_id",
                "status",
                "checkpoint_relpath",
                "checkpoint_sha256",
            ],
            [
                {
                    "stage": "donor_freeze",
                    "q_input_version": "q0",
                    "q_input_sha256": q0_hash,
                    "q_output_version": "q0",
                    "q_output_sha256": q0_hash,
                    "donor_set_id": ordinary_set["donor_set_id"],
                    "status": "success",
                    "checkpoint_relpath": "grt/checkpoints/donor_freeze.json",
                    "checkpoint_sha256": sha256_file(stage_checkpoint),
                }
            ],
        )

        commit_prepared_outputs(stage_grt, stage_metadata, server_dir)
        print(
            f"Prepared GRT q0/D0/Dtel: recipe={recipe_id}, "
            f"q_chromosomes={len(q_records)}, D0={len(ordinary_members)}, Dtel={len(telomere_members)}"
        )
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--reads", action="append", default=[], type=Path)
    parser.add_argument("--meryl", default="meryl")
    parser.add_argument("--merqury", default="merqury.sh")
    parser.add_argument("--craq", default="craq")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--memory-gb", type=int, default=80)
    parser.add_argument("--kmer-size", type=int, default=21)
    args = parser.parse_args()
    if args.threads < 1 or args.memory_gb < 1 or args.kmer_size < 1:
        fail("threads, memory-gb, and kmer-size must be positive integers")
    prepare(args)


if __name__ == "__main__":
    main()
