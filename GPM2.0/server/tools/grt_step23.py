#!/usr/bin/env python3

"""Run traceable GRT PatchRepair and CorrectRefill against one frozen D0.

This module intentionally retains the cohesive Step2/Step3 repair algorithm.
Checkpoint fingerprints hash this exact runtime entrypoint, so moving algorithm
blocks behind imported files would silently weaken the current engine identity.
A later split must first version the checkpoint contract to hash the entrypoint
and its imported algorithm modules as one engine closure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

try:
    from grt_core import *
    from grt_core.common import *
    from grt_core.mummer import command_identity, mummer_parameters, parse_mummer_coords, run_logged
except ModuleNotFoundError:  # Imported as server.tools.grt_step23.
    from .grt_core import *
    from .grt_core.common import *
    from .grt_core.mummer import command_identity, mummer_parameters, parse_mummer_coords, run_logged


ENGINE_VERSION = 9
MUMMER_MIN_CLUSTER = 1_000
MUMMER_MIN_MATCH = 100
MUMMER_MIN_ALIGNMENT = 10_000
MUMMER_LARGE_TARGET_BP = 1_000_000
MUMMER_SMALL_CHUNK_BP = 10_000_000
PATCH_FLANK = 10_000
PATCH_MAX_ANCHOR_DISTANCE = 1_000_000
PATCH_SEARCH_RANGE = 500_000
PATCH_MIN_SCORE = 0.70
PATCH_MIN_MATCH = 100
PATCH_MIN_MAPQ = 20
REFILL_MIN_ALIGNMENT = 1_000
REFILL_MIN_IDENTITY = 0.40
REFILL_MAX_LENGTH = 1_000_000
CORRECTION_SEARCH_RANGE = 500_000
CORRECTION_MARGIN = 100
CORRECTION_LARGE_EDIT_BP = 100_000
CORRECTION_MAX_OVERLAP_EDIT_RATIO = 5.0
PRIMARY_OVERLAP_MIN_BP = 10_000
PRIMARY_OVERLAP_MAX_BP = CORRECTION_SEARCH_RANGE
PRIMARY_OVERLAP_MAX_LEFT_TRIM = CORRECTION_MARGIN
PRIMARY_OVERLAP_POLICY = "keep_left_trim_right"
DOMINATED_COMPONENT_POLICY = "drop_dominated_terminal_component"
NORMALIZED_GAP_LENGTH = 100
MINIMAP_PRESET = "asm5"
REPAIR_MODES = {"conservative", "aggressive"}
DEFAULT_REPAIR_MODE = "aggressive"
ENGINE_SHA256 = sha256_file(Path(__file__).resolve())

MUMMER_ALIGNMENT_FIELDS = [
    "stage",
    "chr",
    "line_number",
    "member_id",
    "source_dataset",
    "source_contig",
    "ref_record",
    "ref_start",
    "ref_end",
    "query_start",
    "query_end",
    "orientation",
    "identity",
    "ref_length",
    "query_length",
    "raw_line",
]

CANDIDATE_FIELDS = [
    "candidate_id",
    "stage",
    "chr",
    "object_id",
    "action",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "target_start",
    "target_end",
    "input_start",
    "input_end",
    "trim_left",
    "trim_right",
    "fill_length",
    "identity",
    "aligned_length",
    "mapq",
    "left_line",
    "right_line",
    "validation_passed",
    "outcome",
    "reason",
    "event_id",
    "final_path_segment_id",
    "error_type",
    "error_subtype",
    "error_features_json",
    "confidence",
    "confidence_score",
    "gap_in_error_region",
    "repair_mode",
    "repair_reason",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
]

REJECTION_FIELDS = [
    "stage",
    "chr",
    "object_id",
    "candidate_id",
    "left_line",
    "right_line",
    "reason",
]
STRATEGY_FIELDS = [
    "chr",
    "strategy",
    "strategy_applied",
    "gap_count",
    "patch_candidate_count",
    "validated_patch_count",
    "accepted_patch_count",
    "fallback_candidate_count",
    "accepted_fallback_count",
    "reason",
]
CLASSIFICATION_FIELDS = [
    "chr",
    "object_id",
    "candidate_id",
    "error_type",
    "error_subtype",
    "error_features_json",
    "confidence",
    "confidence_score",
    "gap_in_error_region",
    "repair_mode",
    "repair_reason",
    "outcome",
    "event_id",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
]








def grt_mummer_parameters(threads: int) -> dict[str, object]:
    """Return the effective MUMmer contract used by upstream GRT.

    Upstream's observed ``delta-filter -i -r -l 10000`` invocation consumes
    ``-r`` as the value of ``-i`` and therefore does not apply reference-best
    filtering. Express the resulting semantics unambiguously instead of
    copying that malformed command line.
    """
    parameters = mummer_parameters(threads)
    parameters["delta_filter"]["reference_best"] = False
    return parameters


def partition_mummer_targets(
    records: dict[str, str],
) -> list[list[tuple[str, str]]]:
    """Mirror upstream GRT's target partitions before alignment filtering.

    Upstream aligns every >=1 Mb record independently and packs smaller
    records into <=10 Mb chunks.  It then retains every alignment of at least
    10 kb; notably, its effective command does not apply reference-best
    filtering.  Both the partition boundary and the retained repeat hits are
    therefore part of the observed repair semantics.
    """
    large = [
        [(name, sequence)]
        for name, sequence in records.items()
        if len(sequence) >= MUMMER_LARGE_TARGET_BP
    ]
    small = sorted(
        (
            (name, sequence)
            for name, sequence in records.items()
            if len(sequence) < MUMMER_LARGE_TARGET_BP
        ),
        key=lambda row: -len(row[1]),
    )
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_size = 0
    for record in small:
        record_size = len(record[1])
        if current and current_size + record_size > MUMMER_SMALL_CHUNK_BP:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(record)
        current_size += record_size
    if current:
        chunks.append(current)
    return [*large, *chunks]


def cached_mummer_chromosome(
    server_dir: Path,
    stage: str,
    chromosome: str,
    q_source_sha256: str,
    q_sequence: str,
    q_segment_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    threads: int,
    should_align: bool,
    target_kind: str = "ordinary_donor",
) -> tuple[Path, bool, str]:
    query_payload = fasta_bytes([(chromosome, q_sequence)])
    parameters = grt_mummer_parameters(threads)
    target_records = dict(
        read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"])
    )
    target_partitions = partition_mummer_targets(target_records)
    partition_manifest = [
        {
            "partition": index,
            "records": [
                {
                    "name": name,
                    "length": len(sequence),
                    "sha256": sha256_bytes(sequence.encode("ascii")),
                }
                for name, sequence in partition
            ],
        }
        for index, partition in enumerate(target_partitions, start=1)
    ]
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": stage,
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "q_segments_sha256": json_hash(q_segment_rows),
        "query_artifact_sha256": sha256_bytes(query_payload),
        "target_kind": target_kind,
        "target_id": donor_set["donor_set_id"],
        "target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": (
            sha256_file(server_dir / "metadata/grt_donor_fragments.tsv")
            if target_kind == "ordinary_donor"
            else ""
        ),
        "tools": {name: command_identity(value) for name, value in tools.items()},
        "parameters": parameters,
        "target_partitioning": {
            "large_record_min_bp": MUMMER_LARGE_TARGET_BP,
            "small_chunk_max_bp": MUMMER_SMALL_CHUNK_BP,
            "partitions": partition_manifest,
        },
        "should_align": should_align,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/step23/{stage}/mummer/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    output_names = [
        "query.fa",
        "result.coords",
        "target_partitions.json",
        "nucmer.command.txt",
        "nucmer.stdout.log",
        "nucmer.stderr.log",
        "delta_filter.command.txt",
        "delta_filter.stdout.log",
        "delta_filter.stderr.log",
        "show_coords.command.txt",
        "show_coords.stdout.log",
        "show_coords.stderr.log",
    ]
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("status") == "success"
                and checkpoint.get("input_fingerprint") == fingerprint
                and set(hashes) == set(output_names)
                and all(
                    (cache_dir / name).is_file()
                    and sha256_file(cache_dir / name) == expected
                    for name, expected in hashes.items()
                )
            ):
                parse_mummer_coords(
                    cache_dir / "result.coords",
                    stage,
                    chromosome,
                    len(q_sequence),
                    members_by_record,
                    donor_lengths,
                )
                return cache_dir, True, chromosome_key
        except (OSError, TypeError, ValueError, json.JSONDecodeError, SystemExit):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        (temporary / "query.fa").write_bytes(query_payload)
        coords = temporary / "result.coords"
        (temporary / "target_partitions.json").write_text(
            json.dumps(partition_manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
            newline="",
        )
        if should_align:
            aggregate: dict[str, list[bytes]] = {
                f"{tool_name}.{suffix}": []
                for tool_name in ("nucmer", "delta_filter", "show_coords")
                for suffix in ("command.txt", "stdout.log", "stderr.log")
            }
            coordinate_parts: list[bytes] = []
            for index, partition in enumerate(target_partitions, start=1):
                label = f"part-{index:04d}"
                target_path = temporary / f".{label}.target.fa"
                target_path.write_bytes(fasta_bytes(partition))
                if target_kind == "ordinary_donor":
                    write_tsv(
                        target_path.with_suffix(".manifest.tsv"),
                        DONOR_MEMBER_FIELDS,
                        [members_by_record[name] for name, _sequence in partition],
                    )
                prefix = temporary / f".{label}"
                delta = temporary / f".{label}.delta"
                filtered = temporary / f".{label}.filtered.delta"
                part_coords = temporary / f".{label}.coords"
                nucmer_command = [
                    tools["nucmer"]["resolved"],
                    "-c",
                    str(MUMMER_MIN_CLUSTER),
                    "-l",
                    str(MUMMER_MIN_MATCH),
                    "--batch=500000000",
                    "-t",
                    str(max(1, min(threads, 4))),
                    "-p",
                    str(prefix),
                    str(target_path),
                    str(temporary / "query.fa"),
                ]
                filter_command = [
                    tools["delta-filter"]["resolved"],
                    "-l",
                    str(MUMMER_MIN_ALIGNMENT),
                    str(delta),
                ]
                coords_command = [
                    tools["show-coords"]["resolved"],
                    "-r",
                    "-l",
                    str(filtered),
                ]
                for tool_name, command, output in (
                    ("nucmer", nucmer_command, None),
                    ("delta_filter", filter_command, filtered),
                    ("show_coords", coords_command, part_coords),
                ):
                    command_path = temporary / f".{label}.{tool_name}.command.txt"
                    stdout_path = temporary / f".{label}.{tool_name}.stdout.log"
                    stderr_path = temporary / f".{label}.{tool_name}.stderr.log"
                    run_logged(
                        command,
                        temporary,
                        command_path,
                        stdout_path,
                        stderr_path,
                        output,
                    )
                    marker = f"# {label}\n".encode("utf-8")
                    aggregate[f"{tool_name}.command.txt"].extend(
                        [marker, command_path.read_bytes()]
                    )
                    aggregate[f"{tool_name}.stdout.log"].extend(
                        [marker, stdout_path.read_bytes()]
                    )
                    aggregate[f"{tool_name}.stderr.log"].extend(
                        [marker, stderr_path.read_bytes()]
                    )
                if not delta.is_file() or delta.stat().st_size == 0:
                    fail(
                        "nucmer did not create a non-empty delta for "
                        f"{stage}:{chromosome}:{label}"
                    )
                if not filtered.is_file() or not part_coords.is_file():
                    fail(
                        "partitioned MUMmer did not create filtered coordinates for "
                        f"{stage}:{chromosome}:{label}"
                    )
                coordinate_parts.append(part_coords.read_bytes())
                for path in temporary.glob(f".{label}*"):
                    path.unlink()
            coords.write_bytes(b"".join(coordinate_parts))
            for name, parts in aggregate.items():
                (temporary / name).write_bytes(b"".join(parts))
        else:
            coords.write_bytes(b"")
            for prefix in ("nucmer", "delta_filter", "show_coords"):
                (temporary / f"{prefix}.command.txt").write_text(
                    f"skipped: no remaining gap or {target_kind} target is empty\n",
                    encoding="utf-8",
                    newline="",
                )
                (temporary / f"{prefix}.stdout.log").write_text("", encoding="utf-8")
                (temporary / f"{prefix}.stderr.log").write_text("", encoding="utf-8")
        parse_mummer_coords(
            coords,
            stage,
            chromosome,
            len(q_sequence),
            members_by_record,
            donor_lengths,
        )
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": stage,
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {name: sha256_file(temporary / name) for name in output_names},
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        return cache_dir, False, chromosome_key
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-mummer-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def collect_mummer(
    server_dir: Path,
    temporary: Path,
    artifact_relpath: str,
    stage: str,
    q_source_sha256: str,
    chromosome_order: list[str],
    records: dict[str, str],
    q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    tools: dict[str, dict[str, str]],
    threads: int,
    *,
    target_set: dict[str, str] | None = None,
    target_members: list[dict[str, str]] | None = None,
    target_kind: str = "ordinary_donor",
) -> tuple[list[dict[str, object]], dict[str, dict[str, str]], list[dict[str, object]]]:
    active_set = donor_set if target_set is None else target_set
    active_members = donor_members if target_members is None else target_members
    members_by_record = {row["fasta_record_name"]: row for row in active_members}
    donor_records = dict(read_fasta_allow_empty(server_dir / active_set["fasta_relpath"]))
    if set(members_by_record) != set(donor_records):
        fail(f"{target_kind} FASTA records differ from its alignment target manifest")
    donor_lengths = {name: len(sequence) for name, sequence in donor_records.items()}
    alignments: list[dict[str, object]] = []
    identities: dict[str, dict[str, str]] = {}
    tasks: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        chromosome_rows = [row for row in q_rows if row["chr"] == chromosome]
        should_align = bool(donor_records) and bool(gap_objects(chromosome, stage, records[chromosome]))
        cache_dir, cache_hit, chromosome_key = cached_mummer_chromosome(
            server_dir,
            stage,
            chromosome,
            q_source_sha256,
            records[chromosome],
            chromosome_rows,
            active_set,
            members_by_record,
            donor_lengths,
            tools,
            threads,
            should_align,
            target_kind,
        )
        print(f"GRT {stage} MUMmer {chromosome}: {'cache hit' if cache_hit else 'computed'}")
        destination = temporary / "mummer" / "by_chr" / chromosome_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cache_dir, destination)
        chromosome_alignments = parse_mummer_coords(
            destination / "result.coords",
            stage,
            chromosome,
            len(records[chromosome]),
            members_by_record,
            donor_lengths,
        )
        alignments.extend(chromosome_alignments)
        query_relpath = f"{artifact_relpath}/mummer/by_chr/{chromosome_key}/query.fa"
        coords_relpath = f"{artifact_relpath}/mummer/by_chr/{chromosome_key}/result.coords"
        identities[chromosome] = {
            "query_relpath": query_relpath,
            "query_sha256": sha256_file(destination / "query.fa"),
            "coords_relpath": coords_relpath,
            "coords_sha256": sha256_file(destination / "result.coords"),
        }
        tasks.append(
            {
                "chr": chromosome,
                "chromosome_key": chromosome_key,
                "cache_key": cache_dir.name,
                **identities[chromosome],
            }
        )
    write_tsv(
        temporary / "mummer" / "chromosome_tasks.tsv",
        [
            "chr",
            "chromosome_key",
            "cache_key",
            "query_relpath",
            "query_sha256",
            "coords_relpath",
            "coords_sha256",
        ],
        tasks,
    )
    write_tsv(
        temporary / "mummer" / "alignments.tsv",
        MUMMER_ALIGNMENT_FIELDS,
        [
            {
                **{field: row.get(field, "") for field in MUMMER_ALIGNMENT_FIELDS},
                "identity": f"{float(row['identity']):.9f}",
            }
            for row in alignments
        ],
    )
    return alignments, identities, tasks


def build_step2_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    donor_records: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for alignment in alignments:
        grouped[(str(alignment["chr"]), str(alignment["ref_record"]))].append(alignment)
    candidates: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    for gap in gaps:
        chromosome = str(gap["chr"])
        gap_position = int(gap["start0"]) + 1
        for (candidate_chr, ref_record), member_alignments in sorted(grouped.items()):
            if candidate_chr != chromosome:
                continue
            left_rows = [row for row in member_alignments if int(row["query_max"]) <= gap_position + 10]
            right_rows = [row for row in member_alignments if int(row["query_min"]) >= gap_position - 10]
            for left in sorted(left_rows, key=lambda row: (-int(row["query_max"]), -float(row["identity"])))[:2]:
                for right in sorted(right_rows, key=lambda row: (int(row["query_min"]), -float(row["identity"])))[:2]:
                    base = {
                        "stage": "step2",
                        "chr": chromosome,
                        "object_id": gap["object_id"],
                        "left_line": left["line_number"],
                        "right_line": right["line_number"],
                    }
                    reason = ""
                    if left["orientation"] != right["orientation"]:
                        reason = "mummer_anchor_orientation_conflict"
                    elif int(right["query_min"]) - int(left["query_max"]) > PATCH_MAX_ANCHOR_DISTANCE:
                        reason = "mummer_anchor_distance_gt_1000000"
                    orientation = str(left["orientation"])
                    if orientation == "+":
                        donor_left = int(left["ref_max"])
                        donor_right = int(right["ref_min"])
                    else:
                        donor_left = int(right["ref_max"])
                        donor_right = int(left["ref_min"])
                    if not reason and donor_left >= donor_right:
                        reason = "mummer_anchor_order_or_overlap_invalid"
                    patch_start = max(1, donor_left - PATCH_FLANK + 1)
                    patch_end = min(len(donor_records[ref_record]), donor_right + PATCH_FLANK - 1)
                    if patch_start >= patch_end:
                        if not reason:
                            reason = "empty_patch_interval"
                        # Rejected pairs remain in the evidence registry. Give
                        # them the increasing donor-local span covered by both
                        # raw anchors instead of serializing the non-executable
                        # reversed patch interval into the public contract.
                        patch_start = min(int(left["ref_min"]), int(right["ref_min"]))
                        patch_end = max(int(left["ref_max"]), int(right["ref_max"]))
                    member = members_by_record[ref_record]
                    source_start, source_end = member_source_interval(member, patch_start, patch_end)
                    payload = {
                        "stage": "step2",
                        "object_id": gap["object_id"],
                        "member_id": member["member_id"],
                        "patch_start": patch_start,
                        "patch_end": patch_end,
                        "orientation": orientation,
                        "left_line": left["line_number"],
                        "right_line": right["line_number"],
                    }
                    candidate_id = stable_id("step2-candidate", payload, 24)
                    candidate = {
                        "candidate_id": candidate_id,
                        **base,
                        "action": "patch",
                        "member_id": member["member_id"],
                        "ref_record": ref_record,
                        "source_dataset": member["dataset_name"],
                        "source_contig": member["contig_name"],
                        "source_start": source_start,
                        "source_end": source_end,
                        "orientation": orientation,
                        "target_start": int(gap["start0"]) + 1,
                        "target_end": int(gap["end0"]),
                        "input_start": int(gap["start0"]) + 1,
                        "input_end": int(gap["end0"]),
                        "trim_left": 0,
                        "trim_right": 0,
                        "fill_length": patch_end - patch_start + 1,
                        "identity": (float(left["identity"]) + float(right["identity"])) / 2,
                        "aligned_length": int(left["query_aligned"]) + int(right["query_aligned"]),
                        "mapq": 0,
                        "patch_start": patch_start,
                        "patch_end": patch_end,
                        "patch_orientation": orientation,
                        "direct_patch_anchor_pair": True,
                        "left_alignment": left,
                        "right_alignment": right,
                        "validation_passed": False,
                        "outcome": "rejected" if reason else "candidate",
                        "reason": reason,
                        "event_id": "",
                        "final_path_segment_id": "",
                    }
                    candidates.append(candidate)
                    if reason:
                        rejections.append({**base, "candidate_id": candidate_id, "reason": reason})
    return candidates, rejections


def patch_sequence(candidate: dict[str, object], donor_records: dict[str, str]) -> str:
    sequence = donor_records[str(candidate["ref_record"])][
        int(candidate["patch_start"]) - 1 : int(candidate["patch_end"])
    ]
    return sequence if candidate["patch_orientation"] == "+" else reverse_complement(sequence)


def build_validation_queries(
    candidates: list[dict[str, object]],
    donor_records: dict[str, str],
) -> tuple[list[tuple[str, str]], dict[str, tuple[dict[str, object], str]]]:
    records: list[tuple[str, str]] = []
    query_map: dict[str, tuple[dict[str, object], str]] = {}
    for candidate in candidates:
        if candidate["reason"]:
            continue
        sequence = patch_sequence(candidate, donor_records)
        flank_length = PATCH_FLANK
        if len(sequence) > 1_000_000:
            flank_length = min(int(len(sequence) * 0.05), 200_000)
        flank_length = max(flank_length, 5_000)
        if len(sequence) <= 2 * flank_length:
            flank_length = len(sequence) // 4
        if flank_length < 100:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "patch_too_short_for_validation"
            continue
        candidate["patch_sequence"] = sequence
        candidate["validation_flank_length"] = flank_length
        for side, flank in (("L", sequence[:flank_length]), ("R", sequence[-flank_length:])):
            name = f"validate__{candidate['candidate_id']}__{side}"
            records.append((name, flank))
            query_map[name] = (candidate, side)
    return records, query_map


def parse_validation_paf(
    path: Path,
    query_map: dict[str, tuple[dict[str, object], str]],
    chromosome: str,
    chromosome_length: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 12 or not any(value.startswith("cg:Z:") for value in fields[12:]):
                fail(f"invalid candidate-validation PAF at {path}:{line_number}")
            query, strand, target = fields[0], fields[4], fields[5]
            if query not in query_map or target != chromosome or strand not in {"+", "-"}:
                fail(f"candidate-validation PAF has unknown identity at {path}:{line_number}")
            try:
                qlen, qstart, qend = map(int, fields[1:4])
                tlen, tstart, tend = map(int, fields[6:9])
                matches, block_length, mapq = map(int, fields[9:12])
            except ValueError:
                fail(f"candidate-validation PAF has non-integer fields at {path}:{line_number}")
            if not (
                0 <= qstart < qend <= qlen
                and 0 <= tstart < tend <= tlen == chromosome_length
                and 0 <= matches <= block_length
                and block_length > 0
            ):
                fail(f"candidate-validation PAF has invalid coordinates at {path}:{line_number}")
            candidate, side = query_map[query]
            rows.append(
                {
                    "line_number": line_number,
                    "raw": line,
                    "query": query,
                    "candidate_id": candidate["candidate_id"],
                    "side": side,
                    "qlen": qlen,
                    "qstart": qstart,
                    "qend": qend,
                    "strand": strand,
                    "target": target,
                    "tstart": tstart,
                    "tend": tend,
                    "matches": matches,
                    "block_length": block_length,
                    "mapq": mapq,
                    "identity": matches / block_length,
                }
            )
    return rows


def cached_validation_alignment(
    server_dir: Path,
    chromosome: str,
    q_source_sha256: str,
    q_sequence: str,
    query_records: list[tuple[str, str]],
    query_map: dict[str, tuple[dict[str, object], str]],
    donor_set: dict[str, str],
    minimap: dict[str, str],
    threads: int,
) -> tuple[Path, bool, str]:
    query_payload = fasta_bytes(query_records)
    target_payload = fasta_bytes([(chromosome, q_sequence)])
    parameters = {
        "preset": MINIMAP_PRESET,
        "cigar": True,
        "round_bandwidth": 100,
        "secondary": 5,
        "threads": threads,
        "min_score": PATCH_MIN_SCORE,
        "min_match": PATCH_MIN_MATCH,
        "min_mapq": PATCH_MIN_MAPQ,
        "search_range": PATCH_SEARCH_RANGE,
    }
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": "step2_candidate_validation",
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "query_sha256": sha256_bytes(query_payload),
        "target_sha256": sha256_bytes(target_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "tool": command_identity(minimap),
        "parameters": parameters,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/step23/step2/validation/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    output_names = ["queries.fa", "target.fa", "result.paf", "command.txt", "stdout.log", "stderr.log"]
    if checkpoint_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            hashes = checkpoint.get("output_hashes", {})
            if (
                checkpoint.get("status") == "success"
                and checkpoint.get("input_fingerprint") == fingerprint
                and set(hashes) == set(output_names)
                and all(
                    (cache_dir / name).is_file() and sha256_file(cache_dir / name) == expected
                    for name, expected in hashes.items()
                )
            ):
                parse_validation_paf(cache_dir / "result.paf", query_map, chromosome, len(q_sequence))
                return cache_dir, True, chromosome_key
        except (OSError, TypeError, ValueError, json.JSONDecodeError, SystemExit):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        (temporary / "queries.fa").write_bytes(query_payload)
        (temporary / "target.fa").write_bytes(target_payload)
        paf_path = temporary / "result.paf"
        if query_records:
            command = [
                minimap["resolved"],
                "-x",
                MINIMAP_PRESET,
                "-t",
                str(threads),
                "-c",
                "-r",
                "100",
                "-N",
                "5",
                "-o",
                str(paf_path),
                str(temporary / "target.fa"),
                str(temporary / "queries.fa"),
            ]
            run_logged(
                command,
                temporary,
                temporary / "command.txt",
                temporary / "stdout.log",
                temporary / "stderr.log",
            )
            if not paf_path.is_file():
                fail(f"minimap2 did not create candidate-validation PAF for {chromosome}")
        else:
            paf_path.write_bytes(b"")
            (temporary / "command.txt").write_text("skipped: no MUMmer patch candidate\n", encoding="utf-8")
            (temporary / "stdout.log").write_text("", encoding="utf-8")
            (temporary / "stderr.log").write_text("", encoding="utf-8")
        parse_validation_paf(paf_path, query_map, chromosome, len(q_sequence))
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": "step2_candidate_validation",
            "chr": chromosome,
            "status": "success",
            "input_fingerprint": fingerprint,
            "fingerprint_payload": fingerprint_payload,
            "output_hashes": {name: sha256_file(temporary / name) for name in output_names},
        }
        (temporary / "cache.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        os.replace(temporary, cache_dir)
        return cache_dir, False, chromosome_key
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step2-validation-{chromosome_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def best_validation_alignment(
    rows: list[dict[str, object]],
    candidate: dict[str, object],
    side: str,
) -> dict[str, object] | None:
    gap_start0 = int(candidate["target_start"]) - 1
    eligible = [
        row
        for row in rows
        if row["candidate_id"] == candidate["candidate_id"]
        and row["side"] == side
        and int(row["mapq"]) >= PATCH_MIN_MAPQ
        and float(row["identity"]) >= PATCH_MIN_SCORE
        and int(row["qend"]) - int(row["qstart"]) >= PATCH_MIN_MATCH
        and abs(int(row["tstart"]) - gap_start0) <= PATCH_SEARCH_RANGE
    ]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda row: (
            -float(row["identity"]),
            -(int(row["qend"]) - int(row["qstart"])),
            -int(row["mapq"]),
            int(row["line_number"]),
        ),
    )[0]


def validate_step2_candidates(
    candidates: list[dict[str, object]],
    validation_rows: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    rejections: list[dict[str, object]],
) -> None:
    for candidate in candidates:
        if candidate["reason"]:
            continue
        left = best_validation_alignment(validation_rows, candidate, "L")
        right = best_validation_alignment(validation_rows, candidate, "R")
        reason = ""
        if left is None or right is None:
            reason = "candidate_validation_missing_flank"
        elif left["strand"] != "+" or right["strand"] != "+":
            reason = "candidate_validation_orientation_conflict"
        elif int(left["tend"]) > int(right["tstart"]):
            reason = "candidate_validation_crossed_cut_points"
        elif int(left["tend"]) > int(candidate["target_start"]) - 1:
            reason = "candidate_validation_left_cut_does_not_cover_gap"
        elif int(right["tstart"]) < int(candidate["target_end"]):
            reason = "candidate_validation_right_cut_does_not_cover_gap"
        if reason:
            candidate["outcome"] = "rejected"
            candidate["reason"] = reason
            rejections.append(
                {
                    "stage": "step2",
                    "chr": candidate["chr"],
                    "object_id": candidate["object_id"],
                    "candidate_id": candidate["candidate_id"],
                    "left_line": "" if left is None else left["line_number"],
                    "right_line": "" if right is None else right["line_number"],
                    "reason": reason,
                }
            )
            continue
        sequence = str(candidate["patch_sequence"])
        flank_length = int(candidate["validation_flank_length"])
        insert_start0 = int(left["qend"])
        insert_end0 = len(sequence) - flank_length + int(right["qstart"])
        if insert_start0 >= insert_end0:
            insert_start0 = flank_length
            insert_end0 = len(sequence) - flank_length
        if insert_start0 >= insert_end0 or insert_end0 - insert_start0 > REFILL_MAX_LENGTH:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "candidate_validation_invalid_insert_interval"
            continue
        if candidate["patch_orientation"] == "+":
            local_start = int(candidate["patch_start"]) + insert_start0
            local_end = int(candidate["patch_start"]) + insert_end0 - 1
        else:
            local_start = int(candidate["patch_end"]) - insert_end0 + 1
            local_end = int(candidate["patch_end"]) - insert_start0
        member = members_by_record[str(candidate["ref_record"])]
        source_start, source_end = member_source_interval(member, local_start, local_end)
        fill_sequence = sequence[insert_start0:insert_end0]
        if re.search(r"N{100,}", fill_sequence):
            candidate["outcome"] = "rejected"
            candidate["reason"] = "validated_patch_crosses_unresolved_gap"
            continue
        left_cut = int(left["tend"])
        right_cut = int(right["tstart"])
        candidate.update(
            {
                "source_start": source_start,
                "source_end": source_end,
                "trim_left": int(candidate["target_start"]) - 1 - left_cut,
                "trim_right": right_cut - int(candidate["target_end"]),
                "input_start": left_cut + 1,
                "input_end": right_cut,
                "fill_length": len(fill_sequence),
                "fill_sequence": fill_sequence,
                "identity": (
                    float(candidate["identity"])
                    + float(left["identity"])
                    + float(right["identity"])
                )
                / 3,
                "aligned_length": int(candidate["aligned_length"])
                + int(left["block_length"])
                + int(right["block_length"]),
                "mapq": min(int(left["mapq"]), int(right["mapq"])),
                "validation_left_line": left["line_number"],
                "validation_right_line": right["line_number"],
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "",
            }
        )




def reject_candidates_spanning_other_gaps(
    candidates: list[dict[str, object]],
    gaps: list[dict[str, object]],
    rejections: list[dict[str, object]] | None = None,
) -> None:
    """Keep one accepted edit tied to exactly one auditable gap object."""
    gaps_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for gap in gaps:
        gaps_by_chr[str(gap["chr"])].append(gap)
    for candidate in candidates:
        if candidate.get("outcome") != "candidate":
            continue
        other_gap = next(
            (
                gap
                for gap in gaps_by_chr[str(candidate["chr"])]
                if str(gap["object_id"]) != str(candidate["object_id"])
                and intervals_overlap(
                    int(candidate["input_start"]),
                    int(candidate["input_end"]),
                    int(gap["start0"]) + 1,
                    int(gap["end0"]),
                )
            ),
            None,
        )
        if other_gap is None:
            continue
        candidate["outcome"] = "rejected"
        candidate["reason"] = f"target_interval_spans_other_gap:{other_gap['object_id']}"
        if rejections is not None:
            rejections.append(
                {
                    "stage": candidate["stage"],
                    "chr": candidate["chr"],
                    "object_id": candidate["object_id"],
                    "candidate_id": candidate["candidate_id"],
                    "left_line": candidate.get("left_line", ""),
                    "right_line": candidate.get("right_line", ""),
                    "reason": candidate["reason"],
                }
            )


def reference_overlap_score(candidate: dict[str, object]) -> int:
    """Return the largest Type5 reference-overlap feature in base pairs."""
    overlaps = []
    for feature in candidate.get("error_features", []):
        match = re.fullmatch(r"ref_overlap_(\d+)", str(feature))
        if match:
            overlaps.append(int(match.group(1)))
    return max(overlaps, default=0)


def arbitrate(
    candidates: list[dict[str, object]],
    consumed: list[dict[str, object]],
) -> list[dict[str, object]]:
    valid = [row for row in candidates if row.get("outcome") == "candidate"]
    ordered = sorted(
        valid,
        key=lambda row: (
            -int(bool(row.get("validation_passed", False))),
            -reference_overlap_score(row),
            (
                int(row["input_end"]) - int(row["input_start"]) + 1
                if row.get("direct_patch_anchor_pair")
                else 0
            ),
            -float(row["identity"]),
            -int(row["aligned_length"]),
            -int(row.get("mapq", 0)),
            str(row["source_dataset"]),
            str(row["source_contig"]),
            int(row["source_start"]),
            int(row["source_end"]),
            str(row["chr"]),
            int(row["input_start"]),
            str(row["candidate_id"]),
        ),
    )
    occupied_sources = [dict(row) for row in consumed]
    occupied_targets: list[dict[str, object]] = []
    accepted_objects: set[str] = set()
    for candidate in ordered:
        object_id = str(candidate["object_id"])
        if object_id in accepted_objects:
            candidate["outcome"] = "rejected"
            candidate["reason"] = "lower_ranked_candidate_for_object"
            continue
        source_consumable = bool(candidate.get("source_consumable", True))
        source_collision = next(
            (
                row
                for row in occupied_sources
                if source_consumable
                if (row["source_dataset"], row["source_contig"])
                == (candidate["source_dataset"], candidate["source_contig"])
                and intervals_overlap(
                    int(row["source_start"]),
                    int(row["source_end"]),
                    int(candidate["source_start"]),
                    int(candidate["source_end"]),
                )
            ),
            None,
        )
        source_collision_same_object = (
            source_collision is not None
            and source_collision.get("object_id")
            and str(source_collision.get("object_id")) == object_id
        )
        source_collision_orientation_conflict = (
            source_collision is not None
            and source_collision.get("orientation")
            and str(source_collision.get("orientation")) != str(candidate.get("orientation"))
        )
        if source_collision is not None and (
            source_collision_same_object or source_collision_orientation_conflict
        ):
            candidate["outcome"] = "conflicted"
            blocker = source_collision.get("candidate_id") or source_collision.get("usage_id") or "prior_usage"
            candidate["reason"] = (
                "source_interval_reuse_orientation_conflict"
                if source_collision_orientation_conflict
                else f"source_interval_consumed_by:{blocker}"
            )
            continue
        target_collision = next(
            (
                row
                for row in occupied_targets
                if row["chr"] == candidate["chr"]
                and intervals_overlap(
                    int(row["input_start"]),
                    int(row["input_end"]),
                    int(candidate["input_start"]),
                    int(candidate["input_end"]),
                )
            ),
            None,
        )
        if target_collision is not None:
            candidate["outcome"] = "conflicted"
            candidate["reason"] = f"target_interval_overlaps:{target_collision['candidate_id']}"
            continue
        candidate["outcome"] = "accepted"
        candidate["reason"] = (
            f"accepted_with_donor_reuse_of:{source_collision.get('candidate_id', '')}"
            if source_collision is not None
            else "accepted_by_global_interval_arbitration"
        )
        if source_collision is not None:
            candidate["donor_reuse"] = True
            candidate["donor_reuse_of"] = source_collision.get("candidate_id", "")
        accepted_objects.add(object_id)
        if source_consumable:
            occupied_sources.append(candidate)
        occupied_targets.append(candidate)
    return sorted(
        candidates,
        key=lambda row: (
            str(row["chr"]),
            int(row["target_start"]),
            str(row["candidate_id"]),
        ),
    )


def arbitrate_structural_candidates(
    candidates: list[dict[str, object]],
    gaps: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Choose deterministic fixer edits in chromosome/gap order.

    Upstream merges overlapping repair regions.  Server mode represents that
    safely as one accepted edit whose normalized gap carries every absorbed
    origin object.  No donor sequence is consumed by these boundary edits.
    """
    by_object: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        by_object[str(candidate["object_id"])].append(candidate)
    accepted_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    ordered_gaps = sorted(
        gaps,
        key=lambda row: (str(row["chr"]), int(row["start0"]), str(row["object_id"])),
    )
    for gap in ordered_gaps:
        chromosome = str(gap["chr"])
        object_id = str(gap["object_id"])
        gap_start = int(gap["start0"]) + 1
        gap_end = int(gap["end0"])
        covering = next(
            (
                row
                for row in accepted_by_chr[chromosome]
                if int(row["input_start"]) <= gap_start
                and int(row["input_end"]) >= gap_end
            ),
            None,
        )
        rows = by_object.get(object_id, [])
        if covering is not None:
            covered = covering.setdefault(
                "covered_object_ids", [str(covering["object_id"])]
            )
            if object_id not in covered:
                covered.append(object_id)
            for row in rows:
                if row.get("outcome") == "candidate":
                    row["outcome"] = "conflicted"
                    row["reason"] = (
                        "absorbed_by_structural_candidate:"
                        f"{covering['candidate_id']}"
                    )
            continue
        eligible = sorted(
            (row for row in rows if row.get("outcome") == "candidate"),
            key=lambda row: (
                -reference_overlap_score(row),
                -float(row["identity"]),
                -int(row["aligned_length"]),
                int(row["input_start"]),
                int(row["input_end"]),
                str(row["candidate_id"]),
            ),
        )
        selected = next(
            (
                row
                for row in eligible
                if not any(
                    intervals_overlap(
                        int(row["input_start"]),
                        int(row["input_end"]),
                        int(occupied["input_start"]),
                        int(occupied["input_end"]),
                    )
                    for occupied in accepted_by_chr[chromosome]
                )
            ),
            None,
        )
        for row in eligible:
            if row is selected:
                row["outcome"] = "accepted"
                row["reason"] = "accepted_by_structural_gap_order"
                row["source_consumable"] = False
                row["covered_object_ids"] = [object_id]
                accepted_by_chr[chromosome].append(row)
            else:
                row["outcome"] = "conflicted" if selected is None else "rejected"
                row["reason"] = (
                    "target_interval_overlaps_prior_structural_edit"
                    if selected is None
                    else "lower_ranked_structural_candidate_for_object"
                )
    return sorted(
        candidates,
        key=lambda row: (
            str(row["chr"]),
            int(row["target_start"]),
            str(row["candidate_id"]),
        ),
    )


def candidate_table_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        row = {field: candidate.get(field, "") for field in CANDIDATE_FIELDS}
        row["identity"] = f"{float(candidate['identity']):.9f}"
        row["validation_passed"] = str(bool(candidate.get("validation_passed", False))).lower()
        rows.append(row)
    return rows


def consumed_intervals(
    usage_rows: list[dict[str, str]],
    event_rows: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    events_by_id = {
        str(row["event_id"]): row
        for row in (event_rows or [])
        if row.get("event_id")
    }
    return [
        {
            "candidate_id": row.get("event_id") or row["usage_id"],
            "usage_id": row["usage_id"],
            "source_dataset": row["source_dataset"],
            "source_contig": row["source_contig"],
            "source_start": int(row["source_start"]),
            "source_end": int(row["source_end"]),
            "stage": row["stage"],
            "object_id": str(events_by_id.get(str(row.get("event_id")), {}).get("object_id", "")),
            "chr": str(events_by_id.get(str(row.get("event_id")), {}).get("chr", "")),
            "orientation": str(events_by_id.get(str(row.get("event_id")), {}).get("source", {}).get("orientation", "")),
        }
        for row in usage_rows
        if row["status"] in {"consumed", "accepted", "superseded"}
    ]


def annotate_candidate_fragments(
    candidates: list[dict[str, object]],
    donor_members: list[dict[str, str]],
    fragment_rows: list[dict[str, str]],
) -> None:
    members_by_id = {row["member_id"]: row for row in donor_members}
    fragments_by_member: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in fragment_rows:
        fragments_by_member[row["member_id"]].append(row)
    for candidate in candidates:
        member = members_by_id.get(str(candidate.get("member_id", "")))
        if member is None:
            continue
        source_start = int(candidate["source_start"])
        source_end = int(candidate["source_end"])
        fragment = None
        for row in fragments_by_member.get(member["member_id"], []):
            fragment_start, fragment_end = member_source_interval(
                member,
                int(row["fragment_start"]),
                int(row["fragment_end"]),
            )
            if fragment_start <= source_start and source_end <= fragment_end:
                fragment = row
                break
        if fragment is None:
            if candidate.get("outcome") == "candidate":
                candidate["outcome"] = "rejected"
                candidate["reason"] = "donor_interval_not_within_fragment"
            candidate["fragment_id"] = ""
        else:
            candidate["fragment_id"] = fragment["fragment_id"]


def evidence_row(
    *,
    evidence_id: str,
    stage: str,
    evidence_type: str,
    status: str,
    q_version: str,
    q_source_sha256: str,
    query_relpath: str,
    query_sha256: str,
    donor_set_id: str,
    target_relpath: str,
    target_sha256: str,
    candidate: dict[str, object],
    tool: str,
    tool_version: str,
    preset: str,
    parameters: dict[str, object],
    raw_relpath: str,
    raw_sha256: str,
    coordinate_system: str,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "stage": stage,
        "evidence_type": evidence_type,
        "status": status,
        "q_version": q_version,
        "q_source_sha256": q_source_sha256,
        "query_artifact_relpath": query_relpath,
        "query_sha256": query_sha256,
        "donor_set_id": donor_set_id,
        "target_artifact_relpath": target_relpath,
        "target_sha256": target_sha256,
        "source_dataset": candidate["source_dataset"],
        "source_contig": candidate["source_contig"],
        "source_start": candidate["source_start"],
        "source_end": candidate["source_end"],
        "orientation": candidate["orientation"],
        "target_chr": candidate["chr"],
        "target_start": candidate["target_start"],
        "target_end": candidate["target_end"],
        "tool": tool,
        "tool_version": tool_version,
        "preset": preset,
        "parameters_json": canonical_json(parameters),
        "raw_artifact_relpath": raw_relpath,
        "raw_artifact_sha256": raw_sha256,
        "coordinate_system": coordinate_system,
        "projection_status": "projected",
    }


def step2_strategy(gap_count: int, patch_candidate_count: int, accepted_patch_count: int) -> str:
    """Return the GRT controller branch for one chromosome."""
    if gap_count == 0:
        return "no_gaps"
    if patch_candidate_count == 0:
        return "no_patch_fixer"
    if accepted_patch_count == 0:
        return "full_fixer_reuse_patches"
    return "partial_success_no_fixer"


def step2_strategy_applied(strategy: str) -> str:
    """Map the controller branch to the contract's execution vocabulary."""
    if strategy in {"no_gaps", "partial_success_no_fixer"}:
        return "patcher_result"
    # The upstream PatchRepair fallback runs the whole-chromosome structural
    # fixer.  Its accepted candidates are boundary edits rather than source
    # patches, so this is accurately represented as fixer_only even when the
    # fixer applies one or more edits.
    return "fixer_only"


def run_step2(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    consumed: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
    threads: int,
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> tuple[dict[str, object], bool]:
    stage = "step2"
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step2 repair mode: {repair_mode}")
    q_input_sha256 = sha256_file(server_dir / "grt/q/q1.fa")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": stage,
        "q_version": "q1",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        "mummer_parameters": grt_mummer_parameters(threads),
        "validation_parameters": {
            "preset": MINIMAP_PRESET,
            "flank": PATCH_FLANK,
            "min_score": PATCH_MIN_SCORE,
            "min_match": PATCH_MIN_MATCH,
            "min_mapq": PATCH_MIN_MAPQ,
            "search_range": PATCH_SEARCH_RANGE,
        },
        "fallback_parameters": {
            "repair_mode": repair_mode,
            "controller": "server_native_correctrefill_source_retry",
            "strategies": [
                "no_patch_fixer",
                "full_fixer_reuse_patches",
                "partial_success_no_fixer",
            ],
        },
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT step2 cache hit: {fingerprint}")
        return cached, True
    invalidate_step23_from(server_dir, stage)
    artifact_relpath = "grt/evidence/step2"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".step2.", dir=artifact_dir.parent))
    q_output_temporary = server_dir / f"grt/q/.q2.fa.tmp.{os.getpid()}"
    try:
        alignments, mummer_identities, _tasks = collect_mummer(
            server_dir,
            temporary,
            artifact_relpath,
            stage,
            q_input_sha256,
            chromosome_order,
            input_records,
            input_q_rows,
            donor_set,
            donor_members,
            tools,
            threads,
        )
        members_by_record = {row["fasta_record_name"]: row for row in donor_members}
        donor_records = dict(read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"]))
        fragment_rows = [
            row
            for row in read_tsv(
                server_dir / "metadata/grt_donor_fragments.tsv",
                DONOR_FRAGMENT_FIELDS,
            )
            if row["donor_set_id"] == donor_set["donor_set_id"]
        ]
        gaps = [gap for chromosome in chromosome_order for gap in gap_objects(chromosome, "q1", input_records[chromosome])]
        candidates, rejections = build_step2_candidates(gaps, alignments, members_by_record, donor_records)
        patch_candidate_counts = {
            chromosome: sum(1 for row in candidates if str(row["chr"]) == chromosome)
            for chromosome in chromosome_order
        }
        validation_identities: dict[str, dict[str, str]] = {}
        validation_rows: list[dict[str, object]] = []
        for chromosome in chromosome_order:
            chromosome_candidates = [row for row in candidates if row["chr"] == chromosome]
            query_records, query_map = build_validation_queries(chromosome_candidates, donor_records)
            cache_dir, cache_hit, chromosome_key = cached_validation_alignment(
                server_dir,
                chromosome,
                q_input_sha256,
                input_records[chromosome],
                query_records,
                query_map,
                donor_set,
                minimap,
                threads,
            )
            print(f"GRT step2 validation {chromosome}: {'cache hit' if cache_hit else 'computed'}")
            destination = temporary / "validation" / "by_chr" / chromosome_key
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_dir, destination)
            validation_rows.extend(
                parse_validation_paf(
                    destination / "result.paf",
                    query_map,
                    chromosome,
                    len(input_records[chromosome]),
                )
            )
            validation_identities[chromosome] = {
                "query_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/queries.fa",
                "query_sha256": sha256_file(destination / "queries.fa"),
                "target_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/target.fa",
                "target_sha256": sha256_file(destination / "target.fa"),
                "raw_relpath": f"{artifact_relpath}/validation/by_chr/{chromosome_key}/result.paf",
                "raw_sha256": sha256_file(destination / "result.paf"),
            }
        validate_step2_candidates(candidates, validation_rows, members_by_record, rejections)
        reject_candidates_spanning_other_gaps(candidates, gaps, rejections)
        annotate_candidate_fragments(candidates, donor_members, fragment_rows)
        patch_candidates = arbitrate(candidates, consumed)
        validated_patch_counts = {
            chromosome: sum(
                1 for row in patch_candidates
                if str(row["chr"]) == chromosome and row.get("validation_passed")
            )
            for chromosome in chromosome_order
        }
        strategy_rows: list[dict[str, object]] = []
        fallback_candidates: list[dict[str, object]] = []
        fallback_chromosomes: set[str] = set()
        for chromosome in chromosome_order:
            chromosome_gaps = sorted(
                (gap for gap in gaps if str(gap["chr"]) == chromosome),
                key=lambda gap: int(gap["start0"]),
            )
            gap_count = len(chromosome_gaps)
            patch_count = patch_candidate_counts[chromosome]
            first_object_id = (
                str(chromosome_gaps[0]["object_id"]) if chromosome_gaps else ""
            )
            accepted_first_count = sum(
                1
                for row in patch_candidates
                if str(row["chr"]) == chromosome
                and str(row["object_id"]) == first_object_id
                and row.get("outcome") == "accepted"
            )
            strategy = step2_strategy(
                gap_count, patch_count, accepted_first_count
            )
            if strategy in {"no_patch_fixer", "full_fixer_reuse_patches"}:
                fallback_chromosomes.add(chromosome)
                for row in patch_candidates:
                    if (
                        str(row["chr"]) == chromosome
                        and row.get("outcome") == "accepted"
                    ):
                        row["outcome"] = "rejected"
                        row["reason"] = "chromosome_fallback_to_structural_fixer"
                chromosome_alignments = [row for row in alignments if str(row["chr"]) == chromosome]
                fallback_candidates.extend(
                    build_step2_structural_fallback_candidates(
                        chromosome_gaps,
                        chromosome_alignments,
                        members_by_record,
                        repair_mode=repair_mode,
                    )
                )
            accepted_count = sum(
                1
                for row in patch_candidates
                if str(row["chr"]) == chromosome
                and row.get("outcome") == "accepted"
            )
            strategy_rows.append(
                {
                    "chr": chromosome,
                    "strategy": strategy,
                    "strategy_applied": "pending",
                    "gap_count": gap_count,
                    "patch_candidate_count": patch_count,
                    "validated_patch_count": validated_patch_counts[chromosome],
                    "accepted_patch_count": accepted_count,
                    "fallback_candidate_count": 0,
                    "accepted_fallback_count": 0,
                    "reason": "",
                }
            )
        candidates = [*patch_candidates, *fallback_candidates]
        fallback_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in fallback_candidates:
            fallback_by_chr[str(row["chr"])].append(row)
        for strategy_row in strategy_rows:
            rows = fallback_by_chr.get(strategy_row["chr"], [])
            strategy_row["fallback_candidate_count"] = len(rows)
            strategy_row["accepted_fallback_count"] = sum(
                1 for row in rows if row.get("outcome") == "accepted"
            )
            strategy_row["strategy_applied"] = step2_strategy_applied(
                str(strategy_row["strategy"])
            )
            if strategy_row["strategy"] == "no_gaps":
                strategy_row["reason"] = "chromosome_has_no_gap_objects"
            elif strategy_row["strategy"] == "partial_success_no_fixer":
                strategy_row["reason"] = "at_least_one_validated_patch_accepted"
            elif strategy_row["accepted_fallback_count"]:
                strategy_row["reason"] = "patchrepair_structural_fixer_accepted"
            else:
                strategy_row["reason"] = "no_safe_structural_fixer_edit"
        evidence_rows: list[dict[str, object]] = []
        for candidate in candidates:
            mummer_evidence_id = stable_id("ev-step2-mummer", candidate["candidate_id"], 22)
            validation_evidence_id = stable_id("ev-step2-validation", candidate["candidate_id"], 22)
            candidate["evidence_id"] = validation_evidence_id
            candidate["evidence_ids"] = [mummer_evidence_id, validation_evidence_id]
            mummer_identity = mummer_identities[str(candidate["chr"])]
            evidence_rows.append(
                evidence_row(
                    evidence_id=mummer_evidence_id,
                    stage="step2",
                    evidence_type="mummer_gap_anchor_pair",
                    status=str(candidate["outcome"]),
                    q_version="q1",
                    q_source_sha256=q_input_sha256,
                    query_relpath=mummer_identity["query_relpath"],
                    query_sha256=mummer_identity["query_sha256"],
                    donor_set_id=donor_set["donor_set_id"],
                    target_relpath=donor_set["fasta_relpath"],
                    target_sha256=donor_set["fasta_sha256"],
                    candidate=candidate,
                    tool="nucmer/delta-filter/show-coords",
                    tool_version=" | ".join(tools[name]["version"] for name in ("nucmer", "delta-filter", "show-coords")),
                    preset="nucmer-c1000-l100;delta-filter-l10000;show-coords-r-l",
                    parameters=grt_mummer_parameters(threads),
                    raw_relpath=mummer_identity["coords_relpath"],
                    raw_sha256=mummer_identity["coords_sha256"],
                    coordinate_system="mummer_1_based_closed",
                )
            )
            validation_identity = validation_identities[str(candidate["chr"])]
            if candidate.get("fallback"):
                evidence_rows.append(
                    evidence_row(
                        evidence_id=validation_evidence_id,
                        stage="step2",
                        evidence_type=(
                            "patchrepair_structural_fixer"
                            if candidate.get("structural_fallback")
                            else "correctrefill_fallback"
                        ),
                        status=str(candidate["outcome"]),
                        q_version="q1",
                        q_source_sha256=q_input_sha256,
                        query_relpath=mummer_identity["query_relpath"],
                        query_sha256=mummer_identity["query_sha256"],
                        donor_set_id=donor_set["donor_set_id"],
                        target_relpath=donor_set["fasta_relpath"],
                        target_sha256=donor_set["fasta_sha256"],
                        candidate=candidate,
                        tool="grt_step3_structural_adapter",
                        tool_version=str(ENGINE_VERSION),
                        preset=(
                            "grt-type1-type6-structural-fixer"
                            if candidate.get("structural_fallback")
                            else "grt-type1-type6-source-retry"
                        ),
                        parameters={
                            "repair_mode": repair_mode,
                            "fallback_strategy": candidate.get("fallback_strategy", ""),
                            "parent_candidate_id": candidate.get("fallback_parent_candidate_id", ""),
                        },
                        raw_relpath=mummer_identity["coords_relpath"],
                        raw_sha256=mummer_identity["coords_sha256"],
                        coordinate_system="mummer_1_based_closed",
                    )
                )
            else:
                evidence_rows.append(
                    evidence_row(
                        evidence_id=validation_evidence_id,
                        stage="candidate_validation",
                        evidence_type="patch_flank_revalidation",
                        status=str(candidate["outcome"]),
                        q_version="q1",
                        q_source_sha256=q_input_sha256,
                        query_relpath=validation_identity["query_relpath"],
                        query_sha256=validation_identity["query_sha256"],
                        donor_set_id="",
                        target_relpath=validation_identity["target_relpath"],
                        target_sha256=validation_identity["target_sha256"],
                        candidate=candidate,
                        tool="minimap2",
                        tool_version=minimap["version"],
                        preset=MINIMAP_PRESET,
                        parameters=fingerprint_payload["validation_parameters"],
                        raw_relpath=validation_identity["raw_relpath"],
                        raw_sha256=validation_identity["raw_sha256"],
                        coordinate_system="paf_0_based_half_open",
                    )
                )
        direct_gaps = [
            gap for gap in gaps if str(gap["chr"]) not in fallback_chromosomes
        ]
        direct_candidates = [
            row
            for row in patch_candidates
            if str(row["chr"]) not in fallback_chromosomes
        ]
        (
            patch_paths,
            patch_records,
            patch_events,
            usage_rows,
            patch_attempts,
        ) = apply_round(
            run_id,
            stage,
            "q1",
            "q2",
            chromosome_order,
            input_paths,
            input_records,
            direct_gaps,
            direct_candidates,
            assignments,
            q_input_sha256,
            sources,
            action="patch",
        )
        fallback_gaps = [
            gap for gap in gaps if str(gap["chr"]) in fallback_chromosomes
        ]
        (
            output_paths,
            output_records,
            structural_prototypes,
            structural_gap_origins,
        ) = apply_corrections(
            chromosome_order,
            patch_paths,
            patch_records,
            fallback_gaps,
            fallback_candidates,
            sources,
        )
        write_fasta(
            q_output_temporary,
            [
                (chromosome, output_records[chromosome])
                for chromosome in chromosome_order
            ],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        for event in patch_events:
            event["q_after"]["sha256"] = q_output_sha256
        structural_events, structural_attempts = build_step2_structural_events(
            run_id,
            q_input_sha256,
            q_output_sha256,
            fallback_gaps,
            fallback_candidates,
            structural_prototypes,
            structural_gap_origins,
        )
        events = [*patch_events, *structural_events]
        attempts = [*patch_attempts, *structural_attempts]
        candidate_by_event = {
            str(candidate.get("event_id")): candidate
            for candidate in direct_candidates
            if candidate.get("event_id")
        }
        for event in events:
            candidate = candidate_by_event.get(str(event["event_id"]))
            if candidate is None:
                continue
            event["strategy"] = next(
                (
                    row["strategy"]
                    for row in strategy_rows
                    if row["chr"] == event["chr"]
                ),
                "partial_success_no_fixer",
            )
        for event in structural_events:
            event["strategy"] = next(
                row["strategy"]
                for row in strategy_rows
                if row["chr"] == event["chr"]
            )
        for row in usage_rows:
            row["donor_set_id"] = donor_set["donor_set_id"]
        q_rows = q_rows_for_paths("q2", chromosome_order, output_paths)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail("internal step2 q output hash disagreement")
        write_tsv(temporary / "candidates.tsv", CANDIDATE_FIELDS, candidate_table_rows(candidates))
        write_tsv(temporary / "rejections.tsv", REJECTION_FIELDS, rejections)
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_tsv(temporary / "strategy.tsv", STRATEGY_FIELDS, strategy_rows)
        write_jsonl(temporary / "events.jsonl", events)
        accepted_intervals = [
            {
                "candidate_id": row["candidate_id"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "stage": stage,
            }
            for row in candidates
            if row["outcome"] == "accepted" and row.get("source_consumable", True)
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": "q1",
            "q_input_sha256": q_input_sha256,
            "q_output_version": "q2",
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "target_sha256": donor_set["fasta_sha256"],
            "q_rows": q_rows,
            "evidence_rows": evidence_rows,
            "usage_rows": usage_rows,
            "events": events,
            "attempts": attempts,
            "strategies": strategy_rows,
            "fallback_candidate_count": len(fallback_candidates),
            "accepted_intervals": accepted_intervals,
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q_output_temporary, server_dir / "grt/q/q2.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix() for path in artifact_dir.rglob("*") if path.is_file()
        ] + ["grt/q/q2.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            f"GRT step2 complete: gaps={len(gaps)}, candidates={len(candidates)}, "
            f"accepted={len(accepted_intervals)}"
        )
        return result, False
    except BaseException:
        q_output_temporary.unlink(missing_ok=True)
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step2-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def _step3_alignment_features(
    gap_pos: int,
    left: dict[str, object],
    right: dict[str, object] | None,
) -> dict[str, object]:
    """Return the alignment feature vector used by GRT's gap analyzer.

    MUMmer rows are already normalized to 1-based closed coordinates by
    :func:`parse_mummer_coords`.  Keeping this adapter on those rows avoids
    importing the standalone GRT package (which would lose GPM provenance).
    """
    if right is None:
        return {
            "crossing_alignment": True,
            "query_overlap": True,
            "query_overlap_length": int(left["query_max"]) - int(left["query_min"]) + 1,
            "query_overlap_region": (int(left["query_min"]), int(left["query_max"])),
            "ref_overlap": False,
            "ref_overlap_length": 0,
            "ref_overlap_region": (0, 0),
            "ref_overlap_ratio": 0.0,
            "direction_match": True,
            "ref_contig_match": True,
            "left_distance": 0,
            "right_distance": 0,
            "left_anchor_quality": int(left["query_aligned"]) * float(left["identity"]),
            "right_anchor_quality": 0.0,
            "left_anchor_length": int(left["query_aligned"]),
            "right_anchor_length": 0,
            "total_gap_size": 0,
            "ref_record": str(left["ref_record"]),
        }

    left_q_min, left_q_max = int(left["query_min"]), int(left["query_max"])
    right_q_min, right_q_max = int(right["query_min"]), int(right["query_max"])
    query_overlap_start = max(left_q_min, right_q_min)
    query_overlap_end = min(left_q_max, right_q_max)
    query_overlap = query_overlap_start <= query_overlap_end
    same_ref = str(left["ref_record"]) == str(right["ref_record"])
    ref_overlap_start = max(int(left["ref_min"]), int(right["ref_min"]))
    ref_overlap_end = min(int(left["ref_max"]), int(right["ref_max"]))
    ref_overlap = same_ref and ref_overlap_start <= ref_overlap_end
    ref_overlap_length = ref_overlap_end - ref_overlap_start + 1 if ref_overlap else 0
    min_anchor = min(
        int(left["ref_max"]) - int(left["ref_min"]) + 1,
        int(right["ref_max"]) - int(right["ref_min"]) + 1,
    )
    return {
        "crossing_alignment": False,
        "query_overlap": query_overlap,
        "query_overlap_length": query_overlap_length if query_overlap else 0,
        "query_overlap_region": (
            (query_overlap_start, query_overlap_end) if query_overlap else (0, 0)
        ),
        "ref_overlap": ref_overlap,
        "ref_overlap_length": ref_overlap_length,
        "ref_overlap_region": (
            (ref_overlap_start, ref_overlap_end) if ref_overlap else (0, 0)
        ),
        "ref_overlap_ratio": ref_overlap_length / min_anchor if ref_overlap and min_anchor else 0.0,
        "direction_match": left["orientation"] == right["orientation"],
        "ref_contig_match": same_ref,
        "left_distance": gap_pos - left_q_max,
        "right_distance": right_q_min - gap_pos,
        "left_anchor_quality": int(left["query_aligned"]) * float(left["identity"]),
        "right_anchor_quality": int(right["query_aligned"]) * float(right["identity"]),
        "left_anchor_length": int(left["query_aligned"]),
        "right_anchor_length": int(right["query_aligned"]),
        "total_gap_size": (gap_pos - left_q_max) + (right_q_min - gap_pos),
        "ref_record": str(left["ref_record"]),
    }


def _step3_classify_features(features: dict[str, object]) -> tuple[str, str, list[str], float]:
    """Classify one anchor pair using GRT Type1--Type6 precedence."""
    if features.get("crossing_alignment"):
        return "type1", "crossing_alignment", ["crossing_alignment"], 0.90

    if features["ref_overlap"]:
        overlap = int(features["ref_overlap_length"])
        subtype = "small_ref_overlap" if overlap < 10_000 else (
            "medium_ref_overlap" if overlap < 50_000 else "large_ref_overlap"
        )
        return (
            "type5",
            subtype,
            [f"ref_overlap_{overlap}"],
            min(0.9 + overlap / 1_000_000.0, 0.99),
        )

    feature_names: list[str] = []
    if features["query_overlap"]:
        feature_names.append(f"query_overlap_{features['query_overlap_length']}")
    if not features["direction_match"]:
        feature_names.append("direction_conflict")
    if not features["ref_contig_match"]:
        feature_names.append("ref_contig_conflict")
    if int(features["left_distance"]) > 100_000:
        feature_names.append(f"large_left_gap_{features['left_distance']}")
    if int(features["right_distance"]) > 100_000:
        feature_names.append(f"large_right_gap_{features['right_distance']}")
    gap_size = int(features["total_gap_size"])
    feature_names.append(
        "small_gap" if gap_size < 1_000 else "medium_gap" if gap_size < 50_000 else "large_gap"
    )

    conflicts = sum(
        [
            not bool(features["direction_match"]),
            not bool(features["ref_contig_match"]),
            bool(features["query_overlap"]) and bool(features["ref_overlap"]),
        ]
    )
    if conflicts >= 2:
        error_type, subtype = "type6", "complex_conflict"
    elif not features["direction_match"]:
        error_type, subtype = "type2", "direction_conflict"
    elif not features["ref_contig_match"]:
        error_type, subtype = "type3", "simple_translocation"
    elif features["query_overlap"]:
        error_type, subtype = "type4", "query_overlap"
    else:
        error_type = "type1"
        subtype = "small_gap" if gap_size < 1_000 else (
            "medium_gap" if gap_size < 50_000 else "large_gap"
        )

    anchor_quality = float(features["left_anchor_quality"]) + float(features["right_anchor_quality"])
    quality_factor = min(anchor_quality / 1_000_000.0, 1.0)
    distance_factor = 1.0 if max(int(features["left_distance"]), int(features["right_distance"])) <= 10_000 else (
        0.9 if max(int(features["left_distance"]), int(features["right_distance"])) <= 100_000 else 0.5
    )
    base = {"type1": 0.55, "type2": 0.75, "type3": 0.70, "type4": 0.70, "type5": 0.85, "type6": 0.80}[error_type]
    confidence_score = min(1.0, 0.45 * base + 0.35 * quality_factor + 0.20 * distance_factor)
    if error_type in {"type2", "type3", "type5", "type6"}:
        confidence_score = max(confidence_score, 0.60)
    return error_type, subtype, sorted(set(feature_names)), confidence_score


def _step3_edit_scope_decision(
    error_type: str,
    features: dict[str, object],
    start: int,
    end: int,
) -> tuple[bool, str]:
    """Reject overlap-driven automatic edits that greatly exceed their evidence."""
    edit_length = max(1, end - start + 1)
    if error_type not in {"type4", "type5"} or edit_length <= CORRECTION_LARGE_EDIT_BP:
        return True, ""
    overlap_length = max(
        int(features.get("query_overlap_length", 0)),
        int(features.get("ref_overlap_length", 0)),
    )
    if overlap_length > 0 and edit_length > overlap_length * CORRECTION_MAX_OVERLAP_EDIT_RATIO:
        return False, "automatic_edit_exceeds_overlap_evidence"
    return True, ""


def _exact_suffix_prefix_by_left_trim(
    left_sequence: str,
    right_sequence: str,
    max_overlap: int,
    max_left_trim: int,
) -> list[int]:
    """Return exact terminal overlaps for every left trim in one O(n) scan."""
    maximum_trim = min(max_left_trim, max(0, len(left_sequence) - 1))
    results = [0] * (maximum_trim + 1)
    limit = min(max_overlap, len(left_sequence), len(right_sequence))
    if limit <= 0:
        return results
    pattern = right_sequence[:limit].upper()
    prefix = [0] * len(pattern)
    for index in range(1, len(pattern)):
        matched = prefix[index - 1]
        while matched and pattern[index] != pattern[matched]:
            matched = prefix[matched - 1]
        if pattern[index] == pattern[matched]:
            matched += 1
        prefix[index] = matched

    scan_start = max(0, len(left_sequence) - max_overlap - maximum_trim)
    boundaries = {
        len(left_sequence) - left_trim: left_trim
        for left_trim in range(maximum_trim + 1)
    }
    matched = 0
    for absolute_index, base in enumerate(
        left_sequence[scan_start:].upper(), start=scan_start
    ):
        while matched and base != pattern[matched]:
            matched = prefix[matched - 1]
        if base == pattern[matched]:
            matched += 1
        boundary = absolute_index + 1
        left_trim = boundaries.get(boundary)
        if left_trim is not None:
            results[left_trim] = matched
        if matched == len(pattern):
            matched = prefix[matched - 1]
    return results


def _longest_exact_suffix_prefix(
    left_sequence: str,
    right_sequence: str,
    max_overlap: int,
) -> int:
    """Return the longest exact left-suffix/right-prefix overlap in O(n)."""
    return _exact_suffix_prefix_by_left_trim(
        left_sequence, right_sequence, max_overlap, 0
    )[0]


def _adjacent_primary_segments(
    path: list[dict[str, object]],
    gap: dict[str, object],
    primary_dataset: str,
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Resolve the exact source-gap-source triplet around one q gap."""
    gap_start0 = int(gap["start0"])
    gap_end0 = int(gap["end0"])
    cursor = 0
    left: dict[str, object] | None = None
    right: dict[str, object] | None = None
    exact_gap = False
    for segment in path:
        segment_end = cursor + int(segment["length"])
        if segment_end == gap_start0 and segment["segment_kind"] == "source":
            left = segment
        if (
            cursor == gap_start0
            and segment_end == gap_end0
            and segment["segment_kind"] == "gap"
        ):
            exact_gap = True
        if cursor == gap_end0 and segment["segment_kind"] == "source":
            right = segment
        cursor = segment_end
    if not exact_gap or left is None or right is None:
        return None
    if (
        str(left["dataset_name"]) != primary_dataset
        or str(right["dataset_name"]) != primary_dataset
        or str(left["contig_name"]) == str(right["contig_name"])
    ):
        return None
    return left, right


def promote_direct_primary_overlap_merges(
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    input_paths: dict[str, list[dict[str, object]]],
    sources: dict[tuple[str, str], str],
    primary_dataset: str,
    *,
    min_overlap: int = PRIMARY_OVERLAP_MIN_BP,
    max_overlap: int = PRIMARY_OVERLAP_MAX_BP,
    max_left_trim: int = PRIMARY_OVERLAP_MAX_LEFT_TRIM,
) -> None:
    """Promote safe Type5 gaps to primary-only direct overlap deletions.

    A flush suffix-prefix match always wins.  Trimming a short unsupported
    left tail is considered only when no flush overlap reaches ``min_overlap``.
    """
    gaps_by_key = {(str(row["chr"]), str(row["object_id"])): row for row in gaps}
    overlap_by_gap: dict[tuple[str, str], dict[str, object] | None] = {}
    for candidate in candidates:
        if candidate.get("outcome") != "candidate" or candidate.get("error_type") != "type5":
            continue
        key = (str(candidate["chr"]), str(candidate["object_id"]))
        if key not in overlap_by_gap:
            gap = gaps_by_key[key]
            adjacent = _adjacent_primary_segments(
                input_paths[str(candidate["chr"])], gap, primary_dataset
            )
            resolution: dict[str, object] | None = None
            if adjacent is not None:
                left, right = adjacent
                left_length = int(left["length"])
                right_length = int(right["length"])
                left_sequence = path_sequence(
                    slice_path(
                        [left],
                        max(0, left_length - max_overlap - max_left_trim),
                        left_length,
                    ),
                    sources,
                )
                right_sequence = path_sequence(
                    slice_path([right], 0, min(right_length, max_overlap)),
                    sources,
                )
                maximum_trim = min(max_left_trim, max(0, left_length - 1))
                overlaps = _exact_suffix_prefix_by_left_trim(
                    left_sequence,
                    right_sequence,
                    max_overlap,
                    maximum_trim,
                )
                selected: tuple[int, int] | None = None
                if overlaps[0] >= right_length:
                    # Do not manufacture a one-base right remainder by shifting
                    # the left boundary when the flush overlap consumes it all.
                    selected = None
                elif min_overlap <= overlaps[0]:
                    selected = (0, overlaps[0])
                else:
                    shifted = [
                        (overlap, -left_trim, left_trim)
                        for left_trim, overlap in enumerate(overlaps[1:], start=1)
                        if min_overlap <= overlap < right_length
                    ]
                    if shifted:
                        overlap, _negative_trim, left_trim = max(shifted)
                        selected = (left_trim, overlap)
                if selected is not None:
                    left_trim, right_trim = selected
                    resolution = {
                        "left": left,
                        "right": right,
                        "left_trim": left_trim,
                        "right_trim": right_trim,
                    }
            overlap_by_gap[key] = resolution

        resolution = overlap_by_gap[key]
        if resolution is None:
            continue
        gap = gaps_by_key[key]
        left = resolution["left"]
        right = resolution["right"]
        left_trim = int(resolution["left_trim"])
        right_trim = int(resolution["right_trim"])
        feature_names = list(candidate.get("error_features", []))
        feature_names.extend(
            [
                f"direct_primary_overlap_{right_trim}",
                f"junction_policy_{PRIMARY_OVERLAP_POLICY}",
                f"left_trim_{left_trim}",
                f"right_trim_{right_trim}",
            ]
        )
        candidate.update(
            {
                "input_start": int(gap["start0"]) + 1 - left_trim,
                "input_end": int(gap["end0"]) + right_trim,
                "trim_left": left_trim,
                "trim_right": right_trim,
                "fill_length": 0,
                "reason": "direct_primary_overlap_keep_left_trim_right",
                "classification_reason": "direct_primary_overlap_keep_left_trim_right",
                "error_features": sorted(set(feature_names)),
                "error_features_json": canonical_json(sorted(set(feature_names))),
                "direct_primary_overlap": True,
                "direct_overlap_bp": right_trim,
                "junction_policy": PRIMARY_OVERLAP_POLICY,
                "primary_left_dataset": left["dataset_name"],
                "primary_left_contig": left["contig_name"],
                "primary_left_orientation": left["orientation"],
                "primary_right_dataset": right["dataset_name"],
                "primary_right_contig": right["contig_name"],
                "primary_right_orientation": right["orientation"],
            }
        )


def _step3_project_ref_interval(row: dict[str, object], ref_start: int, ref_end: int) -> tuple[int, int]:
    ref_min, ref_max = int(row["ref_min"]), int(row["ref_max"])
    query_min, query_max = int(row["query_min"]), int(row["query_max"])
    ref_span = max(1, ref_max - ref_min)
    query_span = max(1, query_max - query_min)
    if row["orientation"] == "+":
        start = query_min + int((ref_start - ref_min) * query_span / ref_span)
        end = query_min + int((ref_end - ref_min) * query_span / ref_span)
    else:
        start = query_max - int((ref_end - ref_min) * query_span / ref_span)
        end = query_max - int((ref_start - ref_min) * query_span / ref_span)
    return min(start, end), max(start, end)


def _step3_replace_region(
    gap_pos: int,
    gap_end: int,
    left: dict[str, object],
    right: dict[str, object] | None,
    error_type: str,
) -> tuple[int, int, str]:
    if right is None:
        return int(left["query_min"]), int(left["query_max"]), "crossing_alignment_error_region"
    if error_type in {"type1", "type6"}:
        return int(left["query_max"]) + 1, int(right["query_min"]) - 1, (
            "complex_conflict" if error_type == "type6" else "simple_gap"
        )
    if error_type == "type2":
        reverse_anchor = left if left["orientation"] == "-" else right
        return int(reverse_anchor["query_min"]), int(reverse_anchor["query_max"]), "direction_conflict"
    if error_type in {"type3", "type4"}:
        shorter = left if int(left["query_aligned"]) <= int(right["query_aligned"]) else right
        return int(shorter["query_min"]), int(shorter["query_max"]), (
            "reference_contig_conflict" if error_type == "type3" else "reference_overlap"
        )
    if error_type == "type5":
        overlap_start = max(int(left["ref_min"]), int(right["ref_min"]))
        overlap_end = min(int(left["ref_max"]), int(right["ref_max"]))
        overlap_row = right
        query_start, query_end = _step3_project_ref_interval(overlap_row, overlap_start, overlap_end)
        if overlap_row["orientation"] == "+":
            return query_start, query_end + CORRECTION_MARGIN, "reference_overlap_with_margin"
        return query_start, query_end + CORRECTION_MARGIN, "reference_overlap_with_margin"
    return gap_pos, gap_end, "unclassified_structural_error"


def _step3_repair_decision(
    error_type: str,
    confidence_score: float,
    left: dict[str, object],
    right: dict[str, object] | None,
    start: int,
    end: int,
    repair_mode: str,
) -> tuple[bool, str]:
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    if right is None:
        return True, "crossing alignment is an error-region anchor"
    anchor_distance = int(right["query_min"]) - int(left["query_max"])
    large_distance = anchor_distance > CORRECTION_SEARCH_RANGE
    if not large_distance and confidence_score >= 0.40:
        return True, "conservative_conditions_met"
    if repair_mode == "aggressive":
        anchor_length = int(left["query_aligned"]) + int(right["query_aligned"])
        replacement_length = max(1, end - start + 1)
        if anchor_length > replacement_length:
            return True, "aggressive_sufficient_anchors"
    return False, "repair_mode_conditions_not_met"


def _step3_anchor_pairs(
    gap_pos: int,
    chromosome_alignments: list[dict[str, object]],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    lefts: list[dict[str, object]] = []
    rights: list[dict[str, object]] = []
    for window in range(100_000, CORRECTION_SEARCH_RANGE + 100_000, 100_000):
        lefts = [
            row
            for row in chromosome_alignments
            if int(row["query_max"]) < gap_pos
            and (
                abs(int(row["query_min"]) - gap_pos) <= window
                or abs(int(row["query_max"]) - gap_pos) <= window
            )
        ]
        rights = [
            row
            for row in chromosome_alignments
            if int(row["query_min"]) > gap_pos
            and (
                abs(int(row["query_min"]) - gap_pos) <= window
                or abs(int(row["query_max"]) - gap_pos) <= window
            )
        ]
        if lefts and rights:
            break
    if not lefts or not rights:
        return []
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    grouped_left: dict[str, list[dict[str, object]]] = defaultdict(list)
    grouped_right: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in lefts:
        grouped_left[str(row["ref_record"])].append(row)
    for row in rights:
        grouped_right[str(row["ref_record"])].append(row)
    # Dict insertion order follows the merged coords stream, matching the
    # upstream analyzer's first-supporting-record boundary choice.
    for ref_record in grouped_left:
        if ref_record not in grouped_right:
            continue
        left = max(grouped_left[ref_record], key=lambda row: int(row["query_max"]))
        right = min(grouped_right[ref_record], key=lambda row: int(row["query_min"]))
        pairs.append((left, right))
    return pairs


def build_correction_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    repair_mode: str = DEFAULT_REPAIR_MODE,
    *,
    structural_target: str = "ordinary_donor",
) -> list[dict[str, object]]:
    """Build Server-native Type1--Type6 CorrectRefill candidates.

    The standalone GRT analyzer operates on implicit files.  This adapter uses
    the already parsed, hash-bound MUMmer rows so source cards and donor-set
    coordinates remain owned by GPM.
    """
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for alignment in alignments:
        by_chr[str(alignment["chr"])].append(alignment)
    candidates: list[dict[str, object]] = []
    for gap in gaps:
        chromosome = str(gap["chr"])
        gap_pos = (int(gap["start0"]) + int(gap["end0"]) + 1) // 2
        chromosome_alignments = by_chr.get(chromosome, [])
        crossing = [
            row for row in chromosome_alignments
            if int(row["query_min"]) <= gap_pos <= int(row["query_max"])
        ]
        prototypes: list[tuple[dict[str, object], dict[str, object] | None]] = []
        if crossing:
            prototypes.append((sorted(
                crossing,
                key=lambda row: (-float(row["identity"]), -int(row["query_aligned"]), int(row["line_number"])),
            )[0], None))
        else:
            prototypes.extend(_step3_anchor_pairs(gap_pos, chromosome_alignments))
        for left, right in prototypes:
            features = _step3_alignment_features(gap_pos, left, right)
            error_type, subtype, feature_names, confidence_score = _step3_classify_features(features)
            start, end, reason = _step3_replace_region(
                gap_pos, int(gap["end0"]), left, right, error_type
            )
            # Upstream reasons from the gap midpoint and normalizes the
            # surviving N run afterward. GPM records an equivalent replayable
            # edit that explicitly covers the complete origin gap.
            start = min(start, int(gap["start0"]) + 1)
            end = max(end, int(gap["end0"]))
            query_length = int(left["query_length"])
            start = max(1, min(start, query_length))
            end = max(start, min(end, query_length))
            eligible, repair_reason = _step3_repair_decision(
                error_type, confidence_score, left, right, start, end, repair_mode
            )
            anchor_pair_executable = right is None or (
                bool(features["ref_contig_match"])
                and bool(features["direction_match"])
            )
            edit_scope_safe, edit_scope_reason = _step3_edit_scope_decision(
                error_type, features, start, end
            )
            if not edit_scope_safe:
                eligible = False
                repair_reason = edit_scope_reason
            if not anchor_pair_executable:
                eligible = False
                repair_reason = "anchor_pair_source_or_orientation_conflict"
            ref_start = int(left["ref_min"])
            ref_end = int(left["ref_max"])
            if right is not None and str(left["ref_record"]) == str(right["ref_record"]):
                ref_start = min(ref_start, int(right["ref_min"]))
                ref_end = max(ref_end, int(right["ref_max"]))
            member = members_by_record[str(left["ref_record"])]
            source_start, source_end = member_source_interval(member, ref_start, ref_end)
            payload = {
                "stage": "step3",
                "object_id": gap["object_id"],
                "action": "replace" if error_type in {"type1", "type3"} else (
                    "delete" if error_type in {"type4", "type5"} else "correct_boundary"
                ),
                "member_id": member["member_id"],
                "source_start": source_start,
                "source_end": source_end,
                "input_start": start,
                "input_end": end,
                "error_type": error_type,
                "error_subtype": subtype,
                "repair_mode": repair_mode,
            }
            action = str(payload["action"])
            candidates.append(
                {
                    "candidate_id": stable_id("step3-correction", payload, 24),
                    "stage": "step3",
                    "chr": chromosome,
                    "object_id": gap["object_id"],
                    "action": action,
                    "member_id": member["member_id"],
                    "ref_record": left["ref_record"],
                    "source_dataset": member["dataset_name"],
                    "source_contig": member["contig_name"],
                    "source_start": source_start,
                    "source_end": source_end,
                    "orientation": left["orientation"],
                    "target_start": int(gap["start0"]) + 1,
                    "target_end": int(gap["end0"]),
                    "input_start": start,
                    "input_end": end,
                    "trim_left": int(gap["start0"]) - (start - 1),
                    "trim_right": end - int(gap["end0"]),
                    "fill_length": NORMALIZED_GAP_LENGTH,
                    "identity": (
                        float(left["identity"])
                        if right is None
                        else (float(left["identity"]) + float(right["identity"])) / 2
                    ),
                    "aligned_length": int(left["query_aligned"])
                    + (0 if right is None else int(right["query_aligned"])),
                    "mapq": 0,
                    "left_line": left["line_number"],
                    "right_line": "" if right is None else right["line_number"],
                    "validation_passed": anchor_pair_executable,
                    "outcome": "candidate" if eligible else "rejected",
                    "reason": reason if eligible else repair_reason,
                    "classification_reason": reason,
                    "error_type": error_type,
                    "error_subtype": subtype,
                    "error_features": feature_names,
                    "error_features_json": canonical_json(feature_names),
                    "confidence": "high" if confidence_score >= 0.70 else "medium" if confidence_score >= 0.40 else "low",
                    "confidence_score": confidence_score,
                    "gap_in_error_region": True,
                    "repair_mode": repair_mode,
                    "repair_reason": repair_reason,
                    "eligible": eligible,
                    "structural_target": structural_target,
                    # Structural correction uses the alignment only as
                    # evidence; it inserts a normalized gap, not donor bases.
                    "source_consumable": False,
                    "event_id": "",
                    "final_path_segment_id": "",
                }
            )
    return candidates


def reject_ambiguous_reference_anchors(
    candidates: list[dict[str, object]],
    alignments: list[dict[str, object]],
    *,
    minimum_query_overlap_ratio: float = 0.50,
    minimum_span_ratio: float = 0.80,
    maximum_identity_drop: float = 0.01,
) -> None:
    """Reject structural edits whose selected reference anchor is non-unique.

    Upstream exposes all Type1--Type6 proposals, but a repeat-supported anchor
    must not authorize a destructive edit.  An anchor is ambiguous when a
    comparable alignment covers the same query interval on another reference
    record, or on a disjoint locus of the same record.
    """
    rows_by_chr_line = {
        (str(row["chr"]), int(row["line_number"])): row for row in alignments
    }
    rows_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in alignments:
        rows_by_chr[str(row["chr"])].append(row)
    for candidate in candidates:
        if (
            candidate.get("outcome") != "candidate"
            or candidate.get("structural_target") != "reference"
        ):
            continue
        selected = [
            rows_by_chr_line.get((str(candidate["chr"]), int(line_number)))
            for line_number in (candidate.get("left_line"), candidate.get("right_line"))
            if str(line_number).strip()
        ]
        ambiguity: dict[str, object] | None = None
        for anchor in (row for row in selected if row is not None):
            anchor_start = int(anchor["query_min"])
            anchor_end = int(anchor["query_max"])
            anchor_span = max(1, anchor_end - anchor_start + 1)
            for alternative in rows_by_chr[str(candidate["chr"])]:
                if int(alternative["line_number"]) == int(anchor["line_number"]):
                    continue
                overlap = max(
                    0,
                    min(anchor_end, int(alternative["query_max"]))
                    - max(anchor_start, int(alternative["query_min"]))
                    + 1,
                )
                if overlap / anchor_span < minimum_query_overlap_ratio:
                    continue
                if int(alternative["query_aligned"]) < anchor_span * minimum_span_ratio:
                    continue
                if float(alternative["identity"]) < float(anchor["identity"]) - maximum_identity_drop:
                    continue
                different_record = str(alternative["ref_record"]) != str(anchor["ref_record"])
                disjoint_locus = not intervals_overlap(
                    int(anchor["ref_min"]),
                    int(anchor["ref_max"]),
                    int(alternative["ref_min"]),
                    int(alternative["ref_max"]),
                )
                if different_record or disjoint_locus:
                    ambiguity = alternative
                    break
            if ambiguity is not None:
                break
        if ambiguity is None:
            continue
        candidate["outcome"] = "rejected"
        candidate["eligible"] = False
        candidate["validation_passed"] = False
        candidate["reason"] = (
            "non_unique_reference_anchor:"
            f"{ambiguity['ref_record']}:{ambiguity['line_number']}"
        )
        candidate["repair_reason"] = candidate["reason"]
        features = sorted(
            set([*candidate.get("error_features", []), "non_unique_reference_anchor"])
        )
        candidate["error_features"] = features
        candidate["error_features_json"] = canonical_json(features)


def _covered_length(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    total = 0
    current_start, current_end = sorted(intervals)[0]
    for start, end in sorted(intervals)[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start + 1
        current_start, current_end = start, end
    return total + current_end - current_start + 1


def build_dominated_terminal_component_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    reference_lengths: dict[str, int],
    input_records: dict[str, str],
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> list[dict[str, object]]:
    """Build safe component drops backed by a near-complete reference backbone.

    This handles the case where a terminal repeat-bearing prefix/suffix is
    attached to an independently near-complete chromosome component.  The
    ambiguous repeat is evidence that the small terminal component is not a
    trustworthy extension; it is never used as a boundary anchor into the
    full backbone.
    """
    rows_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    gaps_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in alignments:
        if float(row["identity"]) >= 0.90 and int(row["query_aligned"]) >= MUMMER_MIN_ALIGNMENT:
            rows_by_chr[str(row["chr"])].append(row)
    for gap in gaps:
        gaps_by_chr[str(gap["chr"])].append(gap)

    candidates: list[dict[str, object]] = []
    for chromosome, chromosome_gaps in gaps_by_chr.items():
        reference_length = reference_lengths.get(chromosome)
        if not reference_length:
            continue
        ordered_gaps = sorted(chromosome_gaps, key=lambda row: int(row["start0"]))
        sequence_length = len(input_records[chromosome])
        components: list[tuple[int, int]] = []
        cursor = 0
        for gap in ordered_gaps:
            components.append((cursor, int(gap["start0"])))
            cursor = int(gap["end0"])
        components.append((cursor, sequence_length))

        def metrics(component: tuple[int, int]) -> dict[str, object]:
            start0, end0 = component
            component_length = max(1, end0 - start0)
            target_rows = []
            cross_rows = []
            query_intervals: list[tuple[int, int]] = []
            reference_intervals: list[tuple[int, int]] = []
            for row in rows_by_chr.get(chromosome, []):
                query_start = max(start0 + 1, int(row["query_min"]))
                query_end = min(end0, int(row["query_max"]))
                if query_end < query_start:
                    continue
                overlap = query_end - query_start + 1
                if overlap < MUMMER_MIN_ALIGNMENT:
                    continue
                if str(row["ref_record"]) == chromosome:
                    target_rows.append(row)
                    query_intervals.append((query_start, query_end))
                    reference_intervals.append((int(row["ref_min"]), int(row["ref_max"])))
                else:
                    cross_rows.append(row)
            best = max(
                target_rows,
                key=lambda row: (
                    int(row["query_aligned"]),
                    float(row["identity"]),
                    -int(row["line_number"]),
                ),
                default=None,
            )
            return {
                "length": component_length,
                "query_coverage": _covered_length(query_intervals) / component_length,
                "reference_coverage": _covered_length(reference_intervals) / reference_length,
                "target_rows": target_rows,
                "cross_rows": cross_rows,
                "best": best,
                "ref_min": min((int(row["ref_min"]) for row in target_rows), default=0),
                "ref_max": max((int(row["ref_max"]) for row in target_rows), default=0),
            }

        component_metrics = [metrics(component) for component in components]
        for gap_index, gap in enumerate(ordered_gaps):
            possibilities = []
            if gap_index == 0:
                possibilities.append(("left", components[0], component_metrics[0], component_metrics[1]))
            if gap_index == len(ordered_gaps) - 1:
                possibilities.append(
                    (
                        "right",
                        components[-1],
                        component_metrics[-1],
                        component_metrics[-2],
                    )
                )
            for side, dominated_component, dominated, backbone in possibilities:
                dominated_best = dominated["best"]
                backbone_best = backbone["best"]
                if dominated_best is None or backbone_best is None:
                    continue
                if (
                    int(backbone["length"]) < 0.70 * reference_length
                    or float(backbone["query_coverage"]) < 0.75
                    or float(backbone["reference_coverage"]) < 0.75
                    or int(dominated["length"]) > 0.25 * reference_length
                    or not dominated["cross_rows"]
                ):
                    continue
                containment_tolerance = max(100_000, int(0.01 * reference_length))
                if (
                    int(dominated["ref_min"]) < int(backbone["ref_min"]) - containment_tolerance
                    or int(dominated["ref_max"]) > int(backbone["ref_max"]) + containment_tolerance
                ):
                    continue
                if side == "left":
                    input_start, input_end = 1, int(gap["end0"])
                    trim_left, trim_right = int(gap["start0"]), 0
                else:
                    input_start, input_end = int(gap["start0"]) + 1, sequence_length
                    trim_left, trim_right = 0, sequence_length - int(gap["end0"])
                payload = {
                    "stage": "step3",
                    "object_id": gap["object_id"],
                    "policy": DOMINATED_COMPONENT_POLICY,
                    "side": side,
                    "input_start": input_start,
                    "input_end": input_end,
                    "backbone_line": backbone_best["line_number"],
                }
                features = [
                    "ambiguous_terminal_component",
                    "near_complete_reference_backbone",
                    f"dominated_{side}_component",
                    f"junction_policy_{DOMINATED_COMPONENT_POLICY}",
                ]
                candidates.append(
                    {
                        "candidate_id": stable_id("step3-dominated-component", payload, 24),
                        "stage": "step3",
                        "chr": chromosome,
                        "object_id": gap["object_id"],
                        "action": "delete",
                        "member_id": f"reference:{chromosome}",
                        "ref_record": chromosome,
                        "source_dataset": "__reference__",
                        "source_contig": chromosome,
                        "source_start": int(dominated["ref_min"]),
                        "source_end": int(dominated["ref_max"]),
                        "orientation": dominated_best["orientation"],
                        "target_start": int(gap["start0"]) + 1,
                        "target_end": int(gap["end0"]),
                        "input_start": input_start,
                        "input_end": input_end,
                        "trim_left": trim_left,
                        "trim_right": trim_right,
                        "fill_length": 0,
                        "identity": min(
                            float(dominated_best["identity"]),
                            float(backbone_best["identity"]),
                        ),
                        "aligned_length": int(dominated_best["query_aligned"])
                        + int(backbone_best["query_aligned"]),
                        "mapq": 0,
                        "left_line": dominated_best["line_number"],
                        "right_line": backbone_best["line_number"],
                        "validation_passed": True,
                        "outcome": "candidate",
                        "reason": "reference_dominated_terminal_component",
                        "classification_reason": "reference_dominated_terminal_component",
                        "error_type": "type5",
                        "error_subtype": "dominated_terminal_component",
                        "error_features": features,
                        "error_features_json": canonical_json(features),
                        "confidence": "high",
                        "confidence_score": 0.95,
                        "gap_in_error_region": True,
                        "repair_mode": repair_mode,
                        "repair_reason": "near_complete_backbone_with_ambiguous_terminal_repeat",
                        "eligible": True,
                        "structural_target": "reference",
                        "source_consumable": False,
                        "junction_policy": DOMINATED_COMPONENT_POLICY,
                        "dominated_side": side,
                        "event_id": "",
                        "final_path_segment_id": "",
                    }
                )
    return candidates


def build_step2_fallback_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    sources: dict[tuple[str, str], str],
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> list[dict[str, object]]:
    """Turn CorrectRefill structural evidence into an auditable Step2 retry.

    The original GRT controller runs a fixer and then re-runs the patcher.  In
    Server mode only an executable Type1 replacement may reuse its explicit
    donor interval as that retry.  Type4/Type5 overlap evidence belongs to the
    Step3 structural-correction path, while conflicting Type2/Type3/Type6
    anchor pairs remain diagnostic-only evidence.
    """
    structural = build_correction_candidates(
        gaps, alignments, members_by_record, repair_mode=repair_mode
    )
    fallback: list[dict[str, object]] = []
    for correction in structural:
        if not correction.get("eligible", True):
            continue
        if (
            correction.get("validation_passed") is not True
            or correction.get("error_type") != "type1"
            or correction.get("action") != "replace"
        ):
            continue
        source_key = (str(correction["source_dataset"]), str(correction["source_contig"]))
        source_sequence = sources.get(source_key, "")
        source_start = int(correction["source_start"])
        source_end = int(correction["source_end"])
        if source_start < 1 or source_end < source_start or source_end > len(source_sequence):
            continue
        fill_sequence = source_sequence[source_start - 1 : source_end]
        if correction["orientation"] == "-":
            fill_sequence = reverse_complement(fill_sequence)
        if not fill_sequence or len(fill_sequence) > REFILL_MAX_LENGTH or re.search(r"N{100,}", fill_sequence):
            continue
        payload = {
            "stage": "step2",
            "fallback": True,
            "parent_candidate_id": correction["candidate_id"],
            "object_id": correction["object_id"],
            "source_dataset": correction["source_dataset"],
            "source_contig": correction["source_contig"],
            "source_start": source_start,
            "source_end": source_end,
            "input_start": correction["input_start"],
            "input_end": correction["input_end"],
            "error_type": correction.get("error_type", "unknown"),
            "error_subtype": correction.get("error_subtype", "unspecified"),
        }
        candidate = dict(correction)
        candidate.update(
            {
                "candidate_id": stable_id("step2-fallback", payload, 24),
                "stage": "step2",
                "action": "patch",
                "fill_sequence": fill_sequence,
                "fill_length": len(fill_sequence),
                "trim_left": int(correction["target_start"]) - int(correction["input_start"]),
                "trim_right": int(correction["input_end"]) - int(correction["target_end"]),
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "fallback_source_interval_candidate",
                "fallback": True,
                "fallback_parent_candidate_id": correction["candidate_id"],
                "fallback_strategy": "correctrefill_source_retry",
                "repair_reason": correction.get("repair_reason", ""),
                "event_id": "",
                "final_path_segment_id": "",
            }
        )
        fallback.append(candidate)
    return fallback


def build_step2_structural_fallback_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> list[dict[str, object]]:
    """Build the upstream PatchRepair fixer branch without inserting D0 bases."""
    candidates = build_correction_candidates(
        gaps,
        alignments,
        members_by_record,
        repair_mode=repair_mode,
        structural_target="ordinary_donor",
    )
    for candidate in candidates:
        candidate.update(
            {
                "stage": "step2",
                "structural_fallback": True,
                "fallback": True,
                "fallback_parent_candidate_id": candidate["candidate_id"],
                "fallback_strategy": "patchrepair_structural_fixer",
                "source_consumable": False,
                "event_id": "",
                "final_path_segment_id": "",
            }
        )
    return arbitrate_structural_candidates(candidates, gaps)


def build_step2_structural_events(
    run_id: str,
    q1_sha256: str,
    q2_sha256: str,
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    prototypes: list[dict[str, object]],
    gap_origins: dict[tuple[str, int, int], dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Serialize structural fixer edits and coalesced gap origins for Step2."""
    candidates_by_object: dict[str, list[dict[str, object]]] = defaultdict(list)
    accepted_by_object: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        candidates_by_object[str(candidate["object_id"])].append(candidate)
        if candidate.get("outcome") == "accepted":
            for object_id in candidate.get(
                "covered_object_ids", [str(candidate["object_id"])]
            ):
                accepted_by_object[str(object_id)] = candidate
    prototype_by_candidate = {
        str(row["candidate"]["candidate_id"]): row for row in prototypes
    }
    output_interval_by_object: dict[str, tuple[int, int]] = {}
    for (_chromosome, start0, end0), origin in gap_origins.items():
        for object_id in [
            str(origin["object_id"]),
            *[str(value) for value in origin.get("coalesced_object_ids", [])],
        ]:
            output_interval_by_object[object_id] = (start0 + 1, end0)
    events: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    primary_events: dict[str, dict[str, object]] = {}
    for gap in gaps:
        object_id = str(gap["object_id"])
        accepted = accepted_by_object.get(object_id)
        related = candidates_by_object.get(object_id, [])
        event_id = stable_id(
            "event", [run_id, "step2", object_id, "structural"], 24
        )
        q_after_start, q_after_end = output_interval_by_object[object_id]
        if accepted is None:
            conflict = any(row.get("outcome") == "conflicted" for row in related)
            status = "conflicted" if conflict else "unresolved"
            reason = (
                "all_structural_candidates_conflicted"
                if conflict
                else "structural_candidates_rejected"
                if related
                else "no_structural_error_detected"
            )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": "correct_boundary",
                "status": status,
                "reason": reason,
                "q_before": {
                    "version": "q1",
                    "start": int(gap["start0"]) + 1,
                    "end": int(gap["end0"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": sorted(
                    {
                        str(evidence_id)
                        for row in related
                        for evidence_id in row.get("evidence_ids", [])
                    }
                ),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
            }
        elif str(accepted["object_id"]) != object_id:
            primary_event_id = stable_id(
                "event",
                [run_id, "step2", str(accepted["object_id"]), "structural"],
                24,
            )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": "correct_boundary",
                "status": "superseded",
                "reason": f"absorbed_by_structural_event:{primary_event_id}",
                "q_before": {
                    "version": "q1",
                    "start": int(gap["start0"]) + 1,
                    "end": int(gap["end0"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": list(accepted.get("evidence_ids", [])),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "superseded_by_event_id": primary_event_id,
            }
        else:
            prototype = prototype_by_candidate[str(accepted["candidate_id"])]
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step2",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": accepted["action"],
                "status": "accepted",
                "reason": accepted["classification_reason"],
                "q_before": {
                    "version": "q1",
                    "start": int(accepted["input_start"]),
                    "end": int(accepted["input_end"]),
                    "sha256": q1_sha256,
                },
                "q_after": {
                    "version": "q2",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q2_sha256,
                },
                "source": None,
                "evidence_ids": list(accepted.get("evidence_ids", [])),
                "usage_ids": [],
                "source_card_key": "",
                "final_path_segment_id": "",
                "edit": {
                    "operation": "replace_interval",
                    "replacement_kind": "gap",
                    "input_coordinate_space": "q1_1_based_closed",
                    "input_start": int(accepted["input_start"]),
                    "input_end": int(accepted["input_end"]),
                    "intermediate_output_start": prototype["intermediate_start"],
                    "intermediate_output_end": prototype["intermediate_end"],
                    "replacement_length": NORMALIZED_GAP_LENGTH,
                    "replacement_sequence_sha256": sha256_bytes(
                        ("N" * NORMALIZED_GAP_LENGTH).encode("ascii")
                    ),
                },
            }
            primary_events[object_id] = event
        classification = accepted or (related[0] if related else None)
        if classification is not None:
            event["classification"] = {
                "error_type": classification.get("error_type", "unknown"),
                "error_subtype": classification.get(
                    "error_subtype", "unspecified"
                ),
                "features": classification.get("error_features", []),
                "confidence": classification.get("confidence", "low"),
                "confidence_score": classification.get("confidence_score", 0.0),
                "gap_in_error_region": bool(
                    classification.get("gap_in_error_region", False)
                ),
            }
            event["repair_mode"] = classification.get(
                "repair_mode", DEFAULT_REPAIR_MODE
            )
            event["repair_reason"] = classification.get("repair_reason", "")
        events.append(event)
        attempts.append(
            {
                "attempt_id": stable_id(
                    "attempt", [run_id, "step2", object_id, "structural"], 22
                ),
                "chr": gap["chr"],
                "object_id": object_id,
                "stage": "step2",
                "status": event["status"],
                "reason": event["reason"],
                "candidate_count": len(related),
                "accepted_event_id": (
                    event_id
                    if event["status"] in {"accepted", "superseded"}
                    else ""
                ),
            }
        )
    for event in events:
        replacement_id = event.get("superseded_by_event_id")
        if replacement_id:
            replacement = next(
                row for row in events if row["event_id"] == replacement_id
            )
            replacement.setdefault("superseded_event_ids", []).append(
                event["event_id"]
            )
    return events, attempts


def correction_usage_rows(
    run_id: str,
    donor_set_id: str,
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        event_id = stable_id("event", [run_id, "step3", candidate["object_id"], "correction"], 24)
        candidate["event_id"] = event_id
        if not candidate.get("source_consumable", True):
            candidate["usage_ids"] = []
            continue
        candidate_usage_id = stable_id("usage-candidate", ["step3", candidate["candidate_id"]], 22)
        outcome_usage_id = stable_id("usage-outcome", ["step3", candidate["candidate_id"]], 22)
        rows.extend(
            [
                {
                    "usage_id": candidate_usage_id,
                    "donor_set_id": donor_set_id,
                    "member_id": candidate["member_id"],
                    "source_dataset": candidate["source_dataset"],
                    "source_contig": candidate["source_contig"],
                    "source_start": candidate["source_start"],
                    "source_end": candidate["source_end"],
                    "stage": "step3",
                    "status": "candidate",
                    "event_id": event_id,
                    "final_path_segment_id": "",
                    "reason": "mummer_structural_candidate",
                },
                {
                    "usage_id": outcome_usage_id,
                    "donor_set_id": donor_set_id,
                    "member_id": candidate["member_id"],
                    "source_dataset": candidate["source_dataset"],
                    "source_contig": candidate["source_contig"],
                    "source_start": candidate["source_start"],
                    "source_end": candidate["source_end"],
                    "stage": "step3",
                    "status": "accepted" if candidate["outcome"] == "accepted" else candidate["outcome"],
                    "event_id": event_id,
                    "final_path_segment_id": "",
                    "reason": candidate["reason"],
                },
            ]
        )
        candidate["usage_ids"] = [candidate_usage_id, outcome_usage_id]
    return rows


def apply_corrections(
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, str],
    list[dict[str, object]],
    dict[tuple[str, int, int], dict[str, object]],
]:
    accepted_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["outcome"] == "accepted":
            accepted_by_chr[str(candidate["chr"])].append(candidate)
    output_paths: dict[str, list[dict[str, object]]] = {}
    output_records: dict[str, str] = {}
    prototypes: list[dict[str, object]] = []
    gap_origin_by_output: dict[tuple[str, int, int], dict[str, object]] = {}
    for chromosome in chromosome_order:
        sequence = input_records[chromosome]
        path = input_paths[chromosome]
        accepted = sorted(accepted_by_chr.get(chromosome, []), key=lambda row: int(row["input_start"]))
        chromosome_gaps = [gap for gap in gaps if gap["chr"] == chromosome]
        gaps_by_object = {str(gap["object_id"]): gap for gap in chromosome_gaps}
        cursor = 0
        output_cursor = 0
        result_path: list[dict[str, object]] = []
        accepted_by_object = {
            str(object_id): row
            for row in accepted
            for object_id in row.get(
                "covered_object_ids", [str(row["object_id"])]
            )
        }
        for candidate in accepted:
            start0 = int(candidate["input_start"]) - 1
            end0 = int(candidate["input_end"])
            covered_object_ids = [
                str(value)
                for value in candidate.get(
                    "covered_object_ids", [str(candidate["object_id"])]
                )
            ]
            associated_gap = gaps_by_object.get(str(candidate["object_id"]))
            if associated_gap is None:
                fail(f"Step3 correction references an unknown q2 gap: {candidate['candidate_id']}")
            if start0 > int(associated_gap["start0"]) or end0 < int(associated_gap["end0"]):
                fail(
                    "Step3 correction edit does not cover associated q2 gap: "
                    f"{candidate['candidate_id']}"
                )
            if start0 < cursor or end0 < start0 or end0 > len(sequence):
                fail(f"overlapping or invalid Step3 correction edit: {candidate['candidate_id']}")
            result_path.extend(slice_path(path, cursor, start0))
            output_cursor += start0 - cursor
            gapless_junction = candidate.get("junction_policy") in {
                PRIMARY_OVERLAP_POLICY,
                DOMINATED_COMPONENT_POLICY,
            }
            replacement_length = 0 if gapless_junction else NORMALIZED_GAP_LENGTH
            output_start = output_cursor + 1
            if gapless_junction:
                # q_after identifies the first retained right-side base.  The
                # edit itself inserts no sequence and creates no corrected gap.
                output_end = output_start
            else:
                gap_segment = {
                    "segment_kind": "gap",
                    "length": NORMALIZED_GAP_LENGTH,
                    "dataset_name": "",
                    "contig_name": "",
                    "source_start": None,
                    "source_end": None,
                    "orientation": "",
                    "source_card_key": "",
                    # Gap path segments are sequence placeholders, not evidence
                    # carriers.  The correction event owns the supporting
                    # evidence and keeps the audit link without violating the
                    # q-segment contract.
                    "evidence_ids": [],
                    "origin_object_ids": covered_object_ids,
                }
                result_path.append(gap_segment)
                output_end = output_start + NORMALIZED_GAP_LENGTH - 1
                output_cursor = output_end
            cursor = end0
            prototype = {
                "candidate": candidate,
                "chr": chromosome,
                "object_id": candidate["object_id"],
                "input_start": int(candidate["input_start"]),
                "input_end": int(candidate["input_end"]),
                "intermediate_start": output_start,
                "intermediate_end": output_end,
                "replacement_length": replacement_length,
            }
            prototypes.append(prototype)
            if not gapless_junction:
                gap_origin_by_output[(chromosome, output_start - 1, output_end)] = {
                    "object_id": candidate["object_id"],
                    "q2_start": int(candidate["input_start"]),
                    "q2_end": int(candidate["input_end"]),
                    "correction_candidate_id": candidate["candidate_id"],
                    "coalesced_object_ids": covered_object_ids[1:],
                }
        result_path.extend(slice_path(path, cursor, len(sequence)))
        output_paths[chromosome] = result_path
        output_records[chromosome] = path_sequence(result_path, sources)
        for gap in chromosome_gaps:
            if str(gap["object_id"]) in accepted_by_object:
                continue
            shift = 0
            for candidate in accepted:
                if int(candidate["input_end"]) < int(gap["start0"]) + 1:
                    shift += int(candidate.get("fill_length", NORMALIZED_GAP_LENGTH)) - (
                        int(candidate["input_end"]) - int(candidate["input_start"]) + 1
                    )
            output_start0 = int(gap["start0"]) + shift
            output_end0 = int(gap["end0"]) + shift
            gap_origin_by_output[(chromosome, output_start0, output_end0)] = {
                "object_id": gap["object_id"],
                "q2_start": int(gap["start0"]) + 1,
                "q2_end": int(gap["end0"]),
                "correction_candidate_id": "",
            }
    return output_paths, output_records, prototypes, gap_origin_by_output


def attach_gap_origins(
    gaps: list[dict[str, object]],
    origins: dict[tuple[str, int, int], dict[str, object]],
) -> None:
    for gap in gaps:
        key = (str(gap["chr"]), int(gap["start0"]), int(gap["end0"]))
        origin = origins.get(key)
        if origin is None:
            fail(f"cannot map corrected Step3 gap back to q2: {key}")
        gap["origin"] = origin


def annotate_gap_path_origins(
    paths: dict[str, list[dict[str, object]]],
    gaps: list[dict[str, object]],
) -> None:
    gaps_by_chr_interval = {
        (str(gap["chr"]), int(gap["start0"]), int(gap["end0"])): gap
        for gap in gaps
    }
    for chromosome, path in paths.items():
        cursor = 0
        for segment in path:
            segment_end = cursor + int(segment["length"])
            if segment["segment_kind"] == "gap":
                gap = gaps_by_chr_interval.get((chromosome, cursor, segment_end))
                if gap is not None and gap.get("origin"):
                    segment["origin_object_ids"] = [
                        str(gap["origin"]["object_id"])
                    ]
            cursor = segment_end


def attach_gap_origins_from_paths(
    paths: dict[str, list[dict[str, object]]],
    gaps: list[dict[str, object]],
    original_gaps: list[dict[str, object]],
) -> None:
    originals = {str(gap["object_id"]): gap for gap in original_gaps}
    path_origins: dict[tuple[str, int, int], list[str]] = {}
    for chromosome, path in paths.items():
        cursor = 0
        for segment in path:
            segment_end = cursor + int(segment["length"])
            if segment["segment_kind"] == "gap":
                path_origins[(chromosome, cursor, segment_end)] = [
                    str(value) for value in segment.get("origin_object_ids", [])
                ]
            cursor = segment_end
    for gap in gaps:
        key = (str(gap["chr"]), int(gap["start0"]), int(gap["end0"]))
        origin_ids = path_origins.get(key, [])
        if not origin_ids:
            fail(f"cannot map filtered Step3 gap back to q2: {key}")
        primary = originals[origin_ids[0]]
        gap["origin"] = {
            "object_id": origin_ids[0],
            "q2_start": int(primary["start0"]) + 1,
            "q2_end": int(primary["end0"]),
            "correction_candidate_id": "",
            "coalesced_object_ids": origin_ids[1:],
        }


def final_gap_coordinates(
    paths: dict[str, list[dict[str, object]]],
) -> dict[str, tuple[int, int]]:
    coordinates: dict[str, tuple[int, int]] = {}
    for path in paths.values():
        cursor = 0
        for segment in path:
            segment_end = cursor + int(segment["length"])
            if segment["segment_kind"] == "gap":
                for object_id in segment.get("origin_object_ids", []):
                    coordinates[str(object_id)] = (cursor + 1, segment_end)
            cursor = segment_end
    return coordinates


def run_refill_alignment(
    server_dir: Path,
    temporary: Path,
    artifact_relpath: str,
    q_source_sha256: str,
    chromosome_order: list[str],
    records: dict[str, str],
    internal_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    minimap: dict[str, str],
    threads: int,
    *,
    round_name: str = "round1",
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, dict[str, str]],
    list[dict[str, object]],
]:
    working_q_version = f"q2_corrected_{round_name}"
    flank_records, gaps, query_map = build_flanks(
        working_q_version, chromosome_order, records
    )
    donor_records = dict(read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"]))
    members_by_record = {row["fasta_record_name"]: row for row in donor_members}
    target_lengths = {name: len(sequence) for name, sequence in donor_records.items()}
    parameters = {
        "preset": MINIMAP_PRESET,
        "cigar": True,
        "threads": threads,
        "flank_length": PATCH_FLANK,
        "min_gap_length": NORMALIZED_GAP_LENGTH,
        "min_alignment_length": REFILL_MIN_ALIGNMENT,
        "min_identity": REFILL_MIN_IDENTITY,
        "max_fill_length": REFILL_MAX_LENGTH,
        "q_source": working_q_version,
    }
    artifact_identities: dict[str, dict[str, str]] = {}
    paf_rows: list[dict[str, object]] = []
    paf_parts: list[bytes] = []
    for chromosome in chromosome_order:
        chromosome_flanks = [
            (name, sequence)
            for name, sequence in flank_records
            if query_map[name][0]["chr"] == chromosome
        ]
        chromosome_query_map = {name: query_map[name] for name, _sequence in chromosome_flanks}
        chromosome_rows = [row for row in internal_q_rows if row["chr"] == chromosome]
        cache_dir, cache_hit, chromosome_key = cached_chromosome_alignment(
            server_dir,
            f"step3_refill_{round_name}",
            chromosome,
            q_source_sha256,
            sha256_bytes(records[chromosome].encode("ascii")),
            chromosome_rows,
            chromosome_flanks,
            chromosome_query_map,
            donor_set,
            bool(donor_records),
            target_lengths,
            minimap,
            parameters,
            threads,
            cache_scope="step23",
        )
        print(
            f"GRT step3 refill {round_name} {chromosome}: "
            f"{'cache hit' if cache_hit else 'computed'}"
        )
        destination = temporary / "refill" / round_name / "by_chr" / chromosome_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cache_dir, destination)
        paf = destination / "result.paf"
        paf_parts.append(paf.read_bytes())
        paf_rows.extend(parse_paf(paf, chromosome_query_map, target_lengths))
        artifact_identities[chromosome] = {
            "query_relpath": (
                f"{artifact_relpath}/refill/{round_name}/by_chr/"
                f"{chromosome_key}/flanks.fa"
            ),
            "query_sha256": sha256_file(destination / "flanks.fa"),
            "raw_relpath": (
                f"{artifact_relpath}/refill/{round_name}/by_chr/"
                f"{chromosome_key}/result.paf"
            ),
            "raw_sha256": sha256_file(paf),
        }
    (temporary / "refill" / round_name / "flanks.fa").write_bytes(
        fasta_bytes(flank_records)
    )
    (temporary / "refill" / round_name / "result.paf").write_bytes(
        b"".join(paf_parts)
    )
    candidates, rejections = build_candidates("step3", paf_rows, gaps, members_by_record, donor_records)
    for candidate in candidates:
        candidate.update(
            {
                "action": "refill",
                "input_start": int(candidate["target_start"]) - int(candidate["trim_left"]),
                "input_end": int(candidate["target_end"]) + int(candidate["trim_right"]),
                "left_line": candidate["left_paf_line"],
                "right_line": candidate["right_paf_line"],
                "validation_passed": True,
                "outcome": "candidate",
                "reason": "",
                "event_id": "",
                "final_path_segment_id": "",
            }
        )
    normalized_rejections = [
        {
            "stage": row["stage"],
            "chr": row["chr"],
            "object_id": row["object_id"],
            "candidate_id": "",
            "left_line": row["left_paf_line"],
            "right_line": row["right_paf_line"],
            "reason": row["reason"],
        }
        for row in rejections
    ]
    return gaps, candidates, artifact_identities, normalized_rejections


def finalize_refill_origins(
    refill_events: list[dict[str, object]],
    gaps: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    origins = {str(gap["object_id"]): gap["origin"] for gap in gaps}
    by_origin_object: dict[str, dict[str, object]] = {}
    for event in refill_events:
        corrected_object_id = str(event["object_id"])
        origin = origins[corrected_object_id]
        event["q_before"]["start"] = origin["q2_start"]
        event["q_before"]["end"] = origin["q2_end"]
        event["corrected_object_id"] = corrected_object_id
        event["object_id"] = origin["object_id"]
        event["edit_coordinate_space"] = "step3_corrected_1_based_closed"
        event["origin_q2_object_id"] = origin["object_id"]
        if "edit" in event:
            event["edit"]["input_coordinate_space"] = "step3_corrected_1_based_closed"
        by_origin_object[str(origin["object_id"])] = event
    return by_origin_object


def project_interval_after_refills(
    chromosome: str,
    start: int,
    end: int,
    refill_events: list[dict[str, object]],
) -> tuple[int, int]:
    """Project a corrected-q2 interval through accepted refill edits into q3."""
    shift = 0
    for event in sorted(
        (
            row
            for row in refill_events
            if row["status"] == "accepted" and row["chr"] == chromosome
        ),
        key=lambda row: int(row["edit"]["input_start"]),
    ):
        edit_start = int(event["edit"]["input_start"])
        edit_end = int(event["edit"]["input_end"])
        if edit_end < start:
            replacement_length = int(event["q_after"]["end"]) - int(event["q_after"]["start"]) + 1
            shift += replacement_length - (edit_end - edit_start + 1)
            continue
        if edit_start > end:
            break
        fail(
            "cannot project a Step3 correction interval through an overlapping refill: "
            f"{chromosome}:{start}-{end} vs {event['event_id']}:{edit_start}-{edit_end}"
        )
    return start + shift, end + shift


def build_correction_events(
    run_id: str,
    q2_sha256: str,
    q3_sha256: str,
    gaps: list[dict[str, object]],
    corrected_gaps: list[dict[str, object]],
    candidates: list[dict[str, object]],
    prototypes: list[dict[str, object]],
    refill_events: list[dict[str, object]],
    refill_by_origin: dict[str, dict[str, object]],
    assignments: dict[tuple[str, str], str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidates_by_object: dict[str, list[dict[str, object]]] = defaultdict(list)
    accepted = {}
    for candidate in candidates:
        candidates_by_object[str(candidate["object_id"])].append(candidate)
        if candidate["outcome"] == "accepted":
            accepted[str(candidate["object_id"])] = candidate
    prototype_by_object = {str(row["object_id"]): row for row in prototypes}
    corrected_gap_by_origin = {
        str(row["origin"]["object_id"]): row for row in corrected_gaps
    }
    events: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    for gap in gaps:
        object_id = str(gap["object_id"])
        candidate = accepted.get(object_id)
        related = candidates_by_object.get(object_id, [])
        refill_event = refill_by_origin.get(object_id)
        event_id = stable_id("event", [run_id, "step3", object_id, "correction"], 24)
        if candidate is None:
            conflict = any(row["outcome"] == "conflicted" for row in related)
            status = "conflicted" if conflict else "unresolved"
            reason = "all_structural_candidates_conflicted" if conflict else (
                "structural_candidates_rejected" if related else "no_structural_error_detected"
            )
            action = "correct_boundary"
            source = None
            evidence_ids = sorted(
                evidence_id for row in related for evidence_id in row.get("evidence_ids", [])
            )
            usage_ids = sorted(usage_id for row in related for usage_id in row.get("usage_ids", []))
            source_card_key = ""
            if refill_event is not None and refill_event["status"] == "accepted":
                q_after_start = int(refill_event["q_after"]["start"])
                q_after_end = int(refill_event["q_after"]["end"])
            else:
                corrected_gap = corrected_gap_by_origin[object_id]
                q_after_start, q_after_end = project_interval_after_refills(
                    str(gap["chr"]),
                    int(corrected_gap["start0"]) + 1,
                    int(corrected_gap["end0"]),
                    refill_events,
                )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step3",
                "chr": gap["chr"],
                "object_id": object_id,
                "action": action,
                "status": status,
                "reason": reason,
                "q_before": {
                    "version": "q2",
                    "start": int(gap["start0"]) + 1,
                    "end": int(gap["end0"]),
                    "sha256": q2_sha256,
                },
                "q_after": {
                    "version": "q3",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q3_sha256,
                },
                "source": source,
                "evidence_ids": evidence_ids,
                "usage_ids": usage_ids,
                "source_card_key": source_card_key,
                "final_path_segment_id": "",
            }
        else:
            prototype = prototype_by_object[object_id]
            source_card_key = ""
            source = None
            if candidate.get("source_consumable", True):
                original_assignment, _placement_mode, _source_card_key = source_assignment(assignments, candidate)
                source = {
                    "dataset": candidate["source_dataset"],
                    "contig": candidate["source_contig"],
                    "start": int(candidate["source_start"]),
                    "end": int(candidate["source_end"]),
                    "orientation": candidate["orientation"],
                    "original_assignment": original_assignment,
                }
            superseded = refill_event is not None and refill_event["status"] == "accepted"
            status = "superseded" if superseded else "accepted"
            if refill_event is not None and refill_event["status"] == "accepted":
                q_after_start = int(refill_event["q_after"]["start"])
                q_after_end = int(refill_event["q_after"]["end"])
            else:
                q_after_start, q_after_end = project_interval_after_refills(
                    str(candidate["chr"]),
                    int(prototype["intermediate_start"]),
                    int(prototype["intermediate_end"]),
                    refill_events,
                )
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step3",
                "chr": candidate["chr"],
                "object_id": object_id,
                "action": candidate["action"],
                "status": status,
                "reason": (
                    f"corrected_then_refilled_by:{refill_event['event_id']}"
                    if superseded
                    else candidate["classification_reason"]
                ),
                "q_before": {
                    "version": "q2",
                    "start": int(candidate["input_start"]),
                    "end": int(candidate["input_end"]),
                    "sha256": q2_sha256,
                },
                "q_after": {
                    "version": "q3",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q3_sha256,
                },
                "source": source,
                "evidence_ids": list(candidate["evidence_ids"]),
                "usage_ids": list(candidate["usage_ids"]),
                "source_card_key": source_card_key,
                "final_path_segment_id": "",
                "edit": {
                    "operation": "replace_interval",
                    "replacement_kind": (
                        "none"
                        if candidate.get("junction_policy")
                        in {PRIMARY_OVERLAP_POLICY, DOMINATED_COMPONENT_POLICY}
                        else "gap"
                    ),
                    "input_coordinate_space": "q2_1_based_closed",
                    "input_start": int(candidate["input_start"]),
                    "input_end": int(candidate["input_end"]),
                    "intermediate_output_start": prototype["intermediate_start"],
                    "intermediate_output_end": prototype["intermediate_end"],
                    "replacement_length": int(prototype["replacement_length"]),
                    "replacement_sequence_sha256": sha256_bytes(
                        ("N" * int(prototype["replacement_length"])).encode("ascii")
                    ),
                },
            }
            if candidate.get("junction_policy") == PRIMARY_OVERLAP_POLICY:
                event["junction"] = {
                    "policy": PRIMARY_OVERLAP_POLICY,
                    "left_trim": int(candidate["trim_left"]),
                    "right_trim": int(candidate["trim_right"]),
                    "direct_overlap_bp": int(candidate["direct_overlap_bp"]),
                    "left_source": {
                        "dataset": candidate["primary_left_dataset"],
                        "contig": candidate["primary_left_contig"],
                        "orientation": candidate["primary_left_orientation"],
                    },
                    "right_source": {
                        "dataset": candidate["primary_right_dataset"],
                        "contig": candidate["primary_right_contig"],
                        "orientation": candidate["primary_right_orientation"],
                    },
                    "support_sequence_inserted": False,
                }
            elif candidate.get("junction_policy") == DOMINATED_COMPONENT_POLICY:
                event["junction"] = {
                    "policy": DOMINATED_COMPONENT_POLICY,
                    "dominated_side": candidate["dominated_side"],
                    "support_sequence_inserted": False,
                }
            if superseded:
                event["superseded_by_event_id"] = refill_event["event_id"]
                refill_event.setdefault("superseded_event_ids", []).append(event_id)
        classification = candidate or (related[0] if related else None)
        if classification is not None:
            event["classification"] = {
                "error_type": classification.get("error_type", "unknown"),
                "error_subtype": classification.get("error_subtype", "unspecified"),
                "features": classification.get("error_features", []),
                "confidence": classification.get("confidence", "low"),
                "confidence_score": classification.get("confidence_score", 0.0),
                "gap_in_error_region": bool(classification.get("gap_in_error_region", False)),
            }
            event["repair_mode"] = classification.get("repair_mode", DEFAULT_REPAIR_MODE)
            event["repair_reason"] = classification.get("repair_reason", "")
            event["fragment_id"] = classification.get("fragment_id", "")
            if classification.get("donor_reuse"):
                event["donor_reuse"] = {
                    "reused": True,
                    "reused_from_candidate_id": classification.get("donor_reuse_of", ""),
                    "policy": "same_orientation_distinct_target",
                }
        events.append(event)
        attempts.append(
            {
                "attempt_id": stable_id("attempt", [run_id, "step3", object_id, "correction"], 22),
                "chr": gap["chr"],
                "object_id": object_id,
                "stage": "step3",
                "status": event["status"],
                "reason": event["reason"],
                "candidate_count": len(related),
                "accepted_event_id": event_id if event["status"] in {"accepted", "superseded"} else "",
            }
        )
    return events, attempts


def replay_step3(
    input_records: dict[str, str],
    correction_events: list[dict[str, object]],
    refill_events: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
    filter_events: list[dict[str, object]] | None = None,
    second_refill_events: list[dict[str, object]] | None = None,
) -> dict[str, str]:
    corrections_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in correction_events:
        if event["status"] in {"accepted", "superseded"}:
            corrections_by_chr[str(event["chr"])].append(event)
    corrected: dict[str, str] = {}
    for chromosome, sequence in input_records.items():
        cursor = 0
        parts: list[str] = []
        for event in sorted(corrections_by_chr.get(chromosome, []), key=lambda row: int(row["edit"]["input_start"])):
            start0 = int(event["edit"]["input_start"]) - 1
            end0 = int(event["edit"]["input_end"])
            if start0 < cursor or end0 < start0:
                fail(f"overlapping Step3 correction replay edits for {chromosome}")
            parts.append(sequence[cursor:start0])
            parts.append("N" * int(event["edit"]["replacement_length"]))
            cursor = end0
        parts.append(sequence[cursor:])
        corrected[chromosome] = "".join(parts)
    def replay_refills(
        records: dict[str, str],
        events: list[dict[str, object]],
    ) -> dict[str, str]:
        refill_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
        for event in events:
            if event["status"] in {"accepted", "superseded"}:
                refill_by_chr[str(event["chr"])].append(event)
        output: dict[str, str] = {}
        for chromosome, sequence in records.items():
            cursor = 0
            parts = []
            for event in sorted(
                refill_by_chr.get(chromosome, []),
                key=lambda row: int(row["edit"]["input_start"]),
            ):
                start0 = int(event["edit"]["input_start"]) - 1
                end0 = int(event["edit"]["input_end"])
                if start0 < cursor or end0 < start0:
                    fail(f"overlapping Step3 refill replay edits for {chromosome}")
                parts.append(sequence[cursor:start0])
                source = event["source"]
                replacement = sources[(source["dataset"], source["contig"])][
                    int(source["start"]) - 1 : int(source["end"])
                ]
                if source["orientation"] == "-":
                    replacement = reverse_complement(replacement)
                if sha256_bytes(replacement.encode("ascii")) != event["edit"]["replacement_sequence_sha256"]:
                    fail(f"Step3 refill replacement checksum mismatch: {event['event_id']}")
                parts.append(replacement)
                cursor = end0
            parts.append(sequence[cursor:])
            output[chromosome] = "".join(parts)
        return output

    round1 = replay_refills(corrected, refill_events)
    filtered = (
        replay_filter_records(round1, filter_events)
        if filter_events is not None
        else round1
    )
    return replay_refills(filtered, second_refill_events or [])


def mark_refills_removed_by_filter(
    refill_events: list[dict[str, object]],
    filter_events: list[dict[str, object]],
    refill_usage: list[dict[str, object]],
    refill_evidence: list[dict[str, object]],
) -> None:
    filter_by_chr = {
        str(event["chr"]): event
        for event in filter_events
        if event["status"] == "accepted"
    }
    superseded: dict[str, str] = {}
    for event in refill_events:
        if event["status"] != "accepted":
            continue
        filter_event = filter_by_chr.get(str(event["chr"]))
        if filter_event is None:
            continue
        start, end = int(event["q_after"]["start"]), int(event["q_after"]["end"])
        if not any(
            intervals_overlap(start, end, int(left), int(right))
            for left, right in filter_event["edit"]["removed_intervals"]
        ):
            continue
        event["status"] = "superseded"
        event["reason"] = "accepted_then_removed_by_step3_filter"
        event["superseded_by_event_id"] = filter_event["event_id"]
        event["final_path_segment_id"] = ""
        filter_event.setdefault("superseded_event_ids", []).append(event["event_id"])
        superseded[str(event["event_id"])] = str(filter_event["event_id"])
    if not superseded:
        return
    superseded_evidence = {
        str(evidence_id)
        for event in refill_events
        if event.get("event_id") in superseded
        for evidence_id in event["evidence_ids"]
    }
    for row in refill_evidence:
        if row["evidence_id"] in superseded_evidence:
            row["status"] = "superseded"
    for row in refill_usage:
        if row["event_id"] not in superseded:
            continue
        if row["status"] == "consumed":
            row["status"] = "superseded"
        row["final_path_segment_id"] = ""
        row["reason"] = "accepted_then_removed_by_step3_filter"


def finalize_step3_public_coordinates(
    events: list[dict[str, object]],
    q2_records: dict[str, str],
    q3_records: dict[str, str],
    q2_sha256: str,
    q3_sha256: str,
    output_paths: dict[str, list[dict[str, object]]],
) -> None:
    gap_coordinates = final_gap_coordinates(output_paths)
    evidence_coordinates: dict[str, tuple[int, int]] = {}
    for path in output_paths.values():
        cursor = 0
        for segment in path:
            segment_end = cursor + int(segment["length"])
            for evidence_id in segment.get("evidence_ids", []):
                evidence_coordinates[str(evidence_id)] = (cursor + 1, segment_end)
            cursor = segment_end
    for event in events:
        chromosome = str(event["chr"])
        q2_length = len(q2_records[chromosome])
        q3_length = len(q3_records[chromosome])
        if event["action"] == "filter_component":
            event["q_before"] = {
                "version": "q2",
                "start": 1,
                "end": q2_length,
                "sha256": q2_sha256,
            }
            q_after = (1, q3_length)
            projection = "whole_chromosome_filter"
        else:
            event["q_before"]["version"] = "q2"
            event["q_before"]["sha256"] = q2_sha256
            event["q_before"]["start"] = min(
                max(1, int(event["q_before"]["start"])), q2_length
            )
            event["q_before"]["end"] = min(
                max(int(event["q_before"]["start"]), int(event["q_before"]["end"])),
                q2_length,
            )
            q_after = next(
                (
                    evidence_coordinates[str(evidence_id)]
                    for evidence_id in event["evidence_ids"]
                    if str(evidence_id) in evidence_coordinates
                ),
                None,
            )
            if q_after is not None:
                projection = "final_path_evidence_segment"
            elif str(event["object_id"]) in gap_coordinates:
                q_after = gap_coordinates[str(event["object_id"])]
                projection = "surviving_origin_gap"
            else:
                point = min(max(1, int(event["q_before"]["start"])), q3_length)
                q_after = (point, point)
                projection = "resolved_or_removed_boundary"
        event["q_after"] = {
            "version": "q3",
            "start": int(q_after[0]),
            "end": int(q_after[1]),
            "sha256": q3_sha256,
        }
        event["q_after_projection"] = projection


def reference_alignment_target(
    server_dir: Path,
) -> tuple[dict[str, str], list[dict[str, str]], dict[str, int]]:
    reference = read_single(
        server_dir / "metadata/reference.tsv",
        ["reference_name", "species_name", "assembly_label", "fasta_relpath", "fai_relpath"],
    )
    records = read_fasta(server_dir / reference["fasta_relpath"])
    target = {
        "donor_set_id": f"reference:{reference['reference_name']}",
        "fasta_relpath": reference["fasta_relpath"],
        "fasta_sha256": sha256_file(server_dir / reference["fasta_relpath"]),
    }
    members = [
        {
            "member_id": f"reference:{name}",
            "dataset_name": "__reference__",
            "contig_name": name,
            "source_start": "1",
            "source_end": str(len(sequence)),
            "orientation": "+",
            "fasta_record_name": name,
        }
        for name, sequence in records
    ]
    return target, members, {name: len(sequence) for name, sequence in records}


def run_step3(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    primary_dataset: str,
    consumed: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
    threads: int,
    repair_mode: str = DEFAULT_REPAIR_MODE,
) -> tuple[dict[str, object], bool]:
    stage = "step3"
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    q_input_sha256 = sha256_file(server_dir / "grt/q/q2.fa")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "engine_sha256": ENGINE_SHA256,
        "stage": stage,
        "q_version": "q2",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "structural_target": {
            "kind": "ordinary_donor",
            "target_id": donor_set["donor_set_id"],
            "target_relpath": donor_set["fasta_relpath"],
            "target_sha256": donor_set["fasta_sha256"],
        },
        "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        "mummer_parameters": grt_mummer_parameters(threads),
        "correction_parameters": {
            "repair_mode": repair_mode,
            "max_search_distance": CORRECTION_SEARCH_RANGE,
            "normalized_gap_length": NORMALIZED_GAP_LENGTH,
            "reference_overlap_margin": CORRECTION_MARGIN,
            "any_reference_overlap_is_type5": True,
            "large_edit_bp": CORRECTION_LARGE_EDIT_BP,
            "max_overlap_edit_ratio": CORRECTION_MAX_OVERLAP_EDIT_RATIO,
            "primary_dataset": primary_dataset,
            "direct_primary_overlap": {
                "minimum_bp": PRIMARY_OVERLAP_MIN_BP,
                "maximum_bp": PRIMARY_OVERLAP_MAX_BP,
                "maximum_left_trim": PRIMARY_OVERLAP_MAX_LEFT_TRIM,
                "policy": PRIMARY_OVERLAP_POLICY,
                "matching": "exact_oriented_suffix_prefix",
                "support_sequence_inserted": False,
            },
        },
        "refill_parameters": {
            "preset": MINIMAP_PRESET,
            "min_alignment": REFILL_MIN_ALIGNMENT,
            "min_identity": REFILL_MIN_IDENTITY,
            "max_fill_length": REFILL_MAX_LENGTH,
            "rounds": 2,
            "post_round1_filter_min_component_length": MIN_COMPONENT_LENGTH,
            "post_round1_filter_connector_length": FILTER_CONNECTOR_LENGTH,
        },
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT step3 cache hit: {fingerprint}")
        return cached, True
    invalidate_step23_from(server_dir, stage)
    artifact_relpath = "grt/evidence/step3"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".step3.", dir=artifact_dir.parent))
    q_output_temporary = server_dir / f"grt/q/.q3.fa.tmp.{os.getpid()}"
    try:
        alignments, mummer_identities, _tasks = collect_mummer(
            server_dir,
            temporary,
            artifact_relpath,
            stage,
            q_input_sha256,
            chromosome_order,
            input_records,
            input_q_rows,
            donor_set,
            donor_members,
            tools,
            threads,
        )
        members_by_record = {row["fasta_record_name"]: row for row in donor_members}
        fragment_rows = [
            row
            for row in read_tsv(
                server_dir / "metadata/grt_donor_fragments.tsv",
                DONOR_FRAGMENT_FIELDS,
            )
            if row["donor_set_id"] == donor_set["donor_set_id"]
        ]
        gaps = [gap for chromosome in chromosome_order for gap in gap_objects(chromosome, "q2", input_records[chromosome])]
        correction_candidates = build_correction_candidates(
            gaps,
            alignments,
            members_by_record,
            repair_mode=repair_mode,
            structural_target="ordinary_donor",
        )
        promote_direct_primary_overlap_merges(
            gaps,
            correction_candidates,
            input_paths,
            sources,
            primary_dataset,
        )
        reject_candidates_spanning_other_gaps(correction_candidates, gaps)
        annotate_candidate_fragments(
            correction_candidates, donor_members, fragment_rows
        )
        ineligible = [row for row in correction_candidates if not row.get("eligible", True)]
        eligible = [row for row in correction_candidates if row.get("eligible", True)]
        correction_candidates = [*arbitrate(eligible, consumed), *ineligible]
        correction_usage = correction_usage_rows(run_id, donor_set["donor_set_id"], correction_candidates)
        correction_evidence: list[dict[str, object]] = []
        for candidate in correction_candidates:
            evidence_id = stable_id("ev-step3-correction", candidate["candidate_id"], 22)
            candidate["evidence_id"] = evidence_id
            candidate["evidence_ids"] = [evidence_id]
            identity = mummer_identities[str(candidate["chr"])]
            correction_evidence.append(evidence_row(
                    evidence_id=evidence_id,
                    stage="step3",
                    evidence_type="mummer_structural_correction",
                    status=str(candidate["outcome"]),
                    q_version="q2",
                    q_source_sha256=q_input_sha256,
                    query_relpath=identity["query_relpath"],
                    query_sha256=identity["query_sha256"],
                    donor_set_id=donor_set["donor_set_id"],
                    target_relpath=donor_set["fasta_relpath"],
                    target_sha256=donor_set["fasta_sha256"],
                    candidate=candidate,
                    tool="nucmer/delta-filter/show-coords",
                    tool_version=" | ".join(tools[name]["version"] for name in ("nucmer", "delta-filter", "show-coords")),
                    preset="nucmer-c1000-l100;delta-filter-l10000;show-coords-r-l",
                    parameters={
                        **grt_mummer_parameters(threads),
                        **fingerprint_payload["correction_parameters"],
                        "classification": {
                            "error_type": candidate.get("error_type", "unknown"),
                            "error_subtype": candidate.get("error_subtype", "unspecified"),
                            "features": candidate.get("error_features", []),
                            "confidence": candidate.get("confidence", "low"),
                            "confidence_score": candidate.get("confidence_score", 0.0),
                            "gap_in_error_region": bool(candidate.get("gap_in_error_region", False)),
                        },
                    },
                    raw_relpath=identity["coords_relpath"],
                    raw_sha256=identity["coords_sha256"],
                    coordinate_system="mummer_1_based_closed",
                ))
        accepted_correction_intervals = [
            {
                "candidate_id": row["candidate_id"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "stage": "step3",
            }
            for row in correction_candidates
            if row["outcome"] == "accepted" and row.get("source_consumable", True)
        ]
        corrected_paths, corrected_records, correction_prototypes, gap_origins = apply_corrections(
            chromosome_order,
            input_paths,
            input_records,
            gaps,
            correction_candidates,
            sources,
        )
        write_fasta(
            temporary / "corrected.fa",
            [(chromosome, corrected_records[chromosome]) for chromosome in chromosome_order],
        )
        internal_q_rows = q_rows_for_paths("q2_corrected", chromosome_order, corrected_paths)
        corrected_gaps, refill_candidates, refill_artifacts, refill_rejections = run_refill_alignment(
            server_dir,
            temporary,
            artifact_relpath,
            q_input_sha256,
            chromosome_order,
            corrected_records,
            internal_q_rows,
            donor_set,
            donor_members,
            minimap,
            threads,
            round_name="round1",
        )
        attach_gap_origins(corrected_gaps, gap_origins)
        annotate_gap_path_origins(corrected_paths, corrected_gaps)
        reject_candidates_spanning_other_gaps(
            refill_candidates,
            corrected_gaps,
            refill_rejections,
        )
        annotate_candidate_fragments(
            refill_candidates, donor_members, fragment_rows
        )
        refill_candidates = arbitrate(
            refill_candidates,
            [*consumed, *accepted_correction_intervals],
        )
        refill_evidence = stage_evidence_rows(
            "step3",
            "q2",
            q_input_sha256,
            donor_set,
            minimap,
            refill_artifacts,
            refill_candidates,
        )
        for candidate, row in zip(refill_candidates, refill_evidence):
            origin = next(
                gap["origin"]
                for gap in corrected_gaps
                if gap["object_id"] == candidate["object_id"]
            )
            evidence_id = stable_id("ev-step3-refill", candidate["candidate_id"], 22)
            candidate["evidence_id"] = evidence_id
            candidate["evidence_ids"] = [evidence_id]
            row["evidence_id"] = evidence_id
            row["evidence_type"] = "corrected_gap_flank_refill"
            row["target_start"] = origin["q2_start"]
            row["target_end"] = origin["q2_end"]
            row["parameters_json"] = canonical_json(
                {
                    **fingerprint_payload["refill_parameters"],
                    "working_query_space": "q2_after_mummer_corrections",
                    "target_projection": "origin_q2_gap",
                    "corrected_fasta_sha256": sha256_file(temporary / "corrected.fa"),
                }
            )
        round1_paths, round1_records, refill_events, refill_usage, refill_attempts = apply_round(
            run_id,
            "step3",
            "q2",
            "q3",
            chromosome_order,
            corrected_paths,
            corrected_records,
            corrected_gaps,
            refill_candidates,
            assignments,
            q_input_sha256,
            sources,
            action="refill",
        )
        for row in refill_usage:
            row["donor_set_id"] = donor_set["donor_set_id"]
        refill_by_origin_round1 = finalize_refill_origins(
            refill_events, corrected_gaps
        )
        filter_paths_result, filter_records, filter_events = apply_filter(
            run_id,
            chromosome_order,
            round1_paths,
            round1_records,
            q_input_sha256,
            sources,
            stage="step3",
            q_input_version="q2",
            q_output_version="q3",
        )
        mark_refills_removed_by_filter(
            refill_events,
            filter_events,
            refill_usage,
            refill_evidence,
        )

        filtered_q_rows = q_rows_for_paths(
            "q2_corrected_filtered", chromosome_order, filter_paths_result
        )
        (
            round2_gaps,
            round2_candidates,
            round2_artifacts,
            round2_rejections,
        ) = run_refill_alignment(
            server_dir,
            temporary,
            artifact_relpath,
            q_input_sha256,
            chromosome_order,
            filter_records,
            filtered_q_rows,
            donor_set,
            donor_members,
            minimap,
            threads,
            round_name="round2",
        )
        attach_gap_origins_from_paths(
            filter_paths_result,
            round2_gaps,
            gaps,
        )
        reject_candidates_spanning_other_gaps(
            round2_candidates,
            round2_gaps,
            round2_rejections,
        )
        annotate_candidate_fragments(
            round2_candidates, donor_members, fragment_rows
        )
        round1_consumed = [
            {
                "candidate_id": row["candidate_id"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "stage": "step3",
            }
            for row in refill_candidates
            if row["outcome"] == "accepted"
        ]
        round2_candidates = arbitrate(
            round2_candidates,
            [*consumed, *accepted_correction_intervals, *round1_consumed],
        )
        round2_evidence = stage_evidence_rows(
            "step3",
            "q2",
            q_input_sha256,
            donor_set,
            minimap,
            round2_artifacts,
            round2_candidates,
        )
        round2_gap_by_object = {
            str(gap["object_id"]): gap for gap in round2_gaps
        }
        for candidate, row in zip(round2_candidates, round2_evidence):
            origin = round2_gap_by_object[str(candidate["object_id"])]["origin"]
            evidence_id = stable_id("ev-step3-refill-round2", candidate["candidate_id"], 22)
            candidate["evidence_id"] = evidence_id
            candidate["evidence_ids"] = [evidence_id]
            row["evidence_id"] = evidence_id
            row["evidence_type"] = "post_filter_gap_flank_refill"
            row["target_start"] = origin["q2_start"]
            row["target_end"] = origin["q2_end"]
            row["parameters_json"] = canonical_json(
                {
                    **fingerprint_payload["refill_parameters"],
                    "working_query_space": "q2_after_correction_round1_filter",
                    "target_projection": "origin_q2_gap",
                }
            )
        (
            output_paths,
            output_records,
            round2_events,
            round2_usage,
            round2_attempts,
        ) = apply_round(
            run_id,
            "step3",
            "q2",
            "q3",
            chromosome_order,
            filter_paths_result,
            filter_records,
            round2_gaps,
            round2_candidates,
            assignments,
            q_input_sha256,
            sources,
            action="refill",
        )
        for row in round2_usage:
            row["donor_set_id"] = donor_set["donor_set_id"]
        refill_by_origin_round2 = finalize_refill_origins(
            round2_events, round2_gaps
        )
        write_fasta(
            q_output_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        refill_by_origin = dict(refill_by_origin_round1)
        for object_id, event in refill_by_origin_round2.items():
            if (
                event["status"] == "accepted"
                or object_id not in refill_by_origin
                or refill_by_origin[object_id]["status"] != "accepted"
            ):
                refill_by_origin[object_id] = event
        refill_object_by_corrected = {
            str(gap["object_id"]): str(gap["origin"]["object_id"])
            for gap in corrected_gaps
        }
        for attempt in refill_attempts:
            attempt["object_id"] = refill_object_by_corrected[str(attempt["object_id"])]
        round2_object_by_filtered = {
            str(gap["object_id"]): str(gap["origin"]["object_id"])
            for gap in round2_gaps
        }
        for attempt in round2_attempts:
            attempt["object_id"] = round2_object_by_filtered[str(attempt["object_id"])]
        correction_events, correction_attempts = build_correction_events(
            run_id,
            q_input_sha256,
            q_output_sha256,
            gaps,
            corrected_gaps,
            correction_candidates,
            correction_prototypes,
            refill_events,
            refill_by_origin,
            assignments,
        )
        superseded_ids = {
            event["event_id"] for event in correction_events if event["status"] == "superseded"
        }
        for row in correction_usage:
            if row["event_id"] in superseded_ids and row["status"] == "accepted":
                row["status"] = "superseded"
                row["reason"] = "correction_superseded_by_refill"
        superseded_evidence = {
            evidence_id
            for event in correction_events
            if event["status"] == "superseded"
            for evidence_id in event["evidence_ids"]
        }
        for row in correction_evidence:
            if row["evidence_id"] in superseded_evidence:
                row["status"] = "superseded"
        events = [
            *correction_events,
            *refill_events,
            *filter_events,
            *round2_events,
        ]
        attempts = [
            *correction_attempts,
            *refill_attempts,
            *round2_attempts,
        ]
        usage_rows = [
            *correction_usage,
            *refill_usage,
            *round2_usage,
        ]
        evidence_rows = [
            *correction_evidence,
            *refill_evidence,
            *round2_evidence,
        ]
        finalize_step3_public_coordinates(
            events,
            input_records,
            output_records,
            q_input_sha256,
            q_output_sha256,
            output_paths,
        )
        if replay_step3(
            input_records,
            correction_events,
            refill_events,
            sources,
            filter_events,
            round2_events,
        ) != output_records:
            fail("Step3 accepted events do not deterministically reconstruct q3")
        q_rows = q_rows_for_paths("q3", chromosome_order, output_paths)
        classification_rows = [
            {
                "chr": row["chr"],
                "object_id": row["object_id"],
                "candidate_id": row["candidate_id"],
                "error_type": row.get("error_type", "unknown"),
                "error_subtype": row.get("error_subtype", "unspecified"),
                "error_features_json": canonical_json(row.get("error_features", [])),
                "confidence": row.get("confidence", "low"),
                "confidence_score": f"{float(row.get('confidence_score', 0.0)):.9f}",
                "gap_in_error_region": str(bool(row.get("gap_in_error_region", False))).lower(),
                "repair_mode": row.get("repair_mode", repair_mode),
                "repair_reason": row.get("repair_reason", ""),
                "outcome": row.get("outcome", "rejected"),
                "event_id": row.get("event_id", ""),
                "fragment_id": row.get("fragment_id", ""),
                "donor_reuse": str(bool(row.get("donor_reuse", False))).lower(),
                "donor_reuse_of": row.get("donor_reuse_of", ""),
            }
            for row in correction_candidates
        ]
        write_tsv(temporary / "correction_candidates.tsv", CANDIDATE_FIELDS, candidate_table_rows(correction_candidates))
        write_tsv(
            temporary / "classifications.tsv",
            CLASSIFICATION_FIELDS,
            classification_rows,
        )
        write_tsv(
            temporary / "refill_candidates.tsv",
            CANDIDATE_FIELDS,
            candidate_table_rows([*refill_candidates, *round2_candidates]),
        )
        write_tsv(
            temporary / "refill_round1_candidates.tsv",
            CANDIDATE_FIELDS,
            candidate_table_rows(refill_candidates),
        )
        write_tsv(
            temporary / "refill_round2_candidates.tsv",
            CANDIDATE_FIELDS,
            candidate_table_rows(round2_candidates),
        )
        write_tsv(
            temporary / "refill_rejections.tsv",
            REJECTION_FIELDS,
            [*refill_rejections, *round2_rejections],
        )
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_jsonl(temporary / "events.jsonl", events)
        accepted_intervals = [
            *accepted_correction_intervals,
            *[
                {
                    "candidate_id": row["candidate_id"],
                    "source_dataset": row["source_dataset"],
                    "source_contig": row["source_contig"],
                    "source_start": row["source_start"],
                    "source_end": row["source_end"],
                    "stage": "step3",
                }
                for row in refill_candidates
                if row["outcome"] == "accepted"
            ],
            *[
                {
                    "candidate_id": row["candidate_id"],
                    "source_dataset": row["source_dataset"],
                    "source_contig": row["source_contig"],
                    "source_start": row["source_start"],
                    "source_end": row["source_end"],
                    "stage": "step3",
                }
                for row in round2_candidates
                if row["outcome"] == "accepted"
            ],
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": "q2",
            "q_input_sha256": q_input_sha256,
            "q_output_version": "q3",
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "target_sha256": donor_set["fasta_sha256"],
            "q_rows": q_rows,
            "evidence_rows": evidence_rows,
            "usage_rows": usage_rows,
            "events": events,
            "attempts": attempts,
            "classification_rows": classification_rows,
            "accepted_intervals": accepted_intervals,
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q_output_temporary, server_dir / "grt/q/q3.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix() for path in artifact_dir.rglob("*") if path.is_file()
        ] + ["grt/q/q3.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            f"GRT step3 complete: gaps={len(gaps)}, corrections="
            f"{sum(row['outcome'] == 'accepted' for row in correction_candidates)}, "
            f"refills={sum(row['outcome'] == 'accepted' for row in [*refill_candidates, *round2_candidates])}"
        )
        return result, False
    except BaseException:
        q_output_temporary.unlink(missing_ok=True)
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step3-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def publish_step23_metadata(
    server_dir: Path,
    results: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
) -> None:
    metadata = server_dir / "metadata"
    q_rows = [
        row
        for row in read_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS)
        if row["q_version"] not in {"q2", "q3", "q4"}
    ]
    evidence_rows = [
        row
        for row in read_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere", "candidate_validation"}
    ]
    usage_rows = [
        row
        for row in read_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    events = [
        json.loads(line)
        for line in (metadata / "grt_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = [
        row
        for row in events
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    attempts = [
        row
        for row in read_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere"}
    ]
    stage_rows = [
        row
        for row in read_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS)
        if row["stage"] not in {"step2", "step3", "step4_telomere", "finalize"}
    ]
    for result in results:
        q_rows.extend(result["q_rows"])
        evidence_rows.extend(result["evidence_rows"])
        usage_rows.extend(result["usage_rows"])
        events.extend(result["events"])
        attempts.extend(result["attempts"])
        stage_rows.append(stage_status_row(server_dir, result))
    tool_rows = [
        row
        for row in read_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS)
        if row["tool"]
        not in {
            "grt_step23",
            "step23_nucmer",
            "step23_delta_filter",
            "step23_show_coords",
            "step23_minimap2",
        }
    ]
    tool_rows.extend(
        [
            {
                "tool": "grt_step23",
                "version": str(ENGINE_VERSION),
                "executable": ".prepare_lib/tools/grt_step23.py",
            },
            {
                "tool": "step23_nucmer",
                "version": tools["nucmer"]["version"],
                "executable": tools["nucmer"]["resolved"],
            },
            {
                "tool": "step23_delta_filter",
                "version": tools["delta-filter"]["version"],
                "executable": tools["delta-filter"]["resolved"],
            },
            {
                "tool": "step23_show_coords",
                "version": tools["show-coords"]["version"],
                "executable": tools["show-coords"]["resolved"],
            },
            {
                "tool": "step23_minimap2",
                "version": minimap["version"],
                "executable": minimap["resolved"],
            },
        ]
    )
    strategy_rows = [
        row
        for result in results
        for row in result.get("strategies", [])
    ]
    classification_rows = [
        row
        for result in results
        for row in result.get("classification_rows", [])
    ]
    atomic_write_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS, usage_rows)
    atomic_write_jsonl(metadata / "grt_events.jsonl", events)
    atomic_write_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
    atomic_write_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS, stage_rows)
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)
    atomic_write_tsv(
        metadata / "grt_step2_strategies.tsv",
        STRATEGY_FIELDS,
        strategy_rows,
    )
    atomic_write_tsv(
        metadata / "grt_step3_classifications.tsv",
        CLASSIFICATION_FIELDS,
        classification_rows,
    )


def reconcile_step2_events_with_step3(
    step2: dict[str, object],
    step3: dict[str, object],
) -> None:
    """Supersede accepted Step2 source segments removed by Step3 edits."""
    surviving_evidence = {
        str(evidence_id)
        for row in step3["q_rows"]
        for evidence_id in json.loads(str(row["evidence_ids_json"]))
    }
    step3_events = {str(event["event_id"]): event for event in step3["events"]}

    def accepted_replacement(event: dict[str, object]) -> dict[str, object] | None:
        if event["status"] == "accepted":
            return event
        replacement_id = event.get("superseded_by_event_id")
        replacement = step3_events.get(str(replacement_id)) if replacement_id else None
        return replacement if replacement and replacement["status"] == "accepted" else None

    q2_rows_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in step2["q_rows"]:
        q2_rows_by_chr[str(row["chr"])].append(row)
    superseded: dict[str, str] = {}
    superseded_path_evidence: set[str] = set()
    for event in step2["events"]:
        if event["status"] != "accepted" or event["action"] not in {
            "fill",
            "patch",
            "refill",
            "replace",
        }:
            continue
        chromosome = str(event["chr"])
        after_start = int(event["q_after"]["start"])
        after_end = int(event["q_after"]["end"])
        path_evidence = {
            str(evidence_id)
            for row in q2_rows_by_chr.get(chromosome, [])
            if intervals_overlap(
                after_start,
                after_end,
                int(row["q_start"]),
                int(row["q_end"]),
            )
            for evidence_id in json.loads(str(row["evidence_ids_json"]))
        }
        if path_evidence & surviving_evidence:
            continue
        replacements = []
        for candidate in step3["events"]:
            if str(candidate["chr"]) != chromosome:
                continue
            replacement = accepted_replacement(candidate)
            if replacement is None:
                continue
            if candidate["action"] == "filter_component" or intervals_overlap(
                after_start,
                after_end,
                int(candidate["q_before"]["start"]),
                int(candidate["q_before"]["end"]),
            ):
                replacements.append((candidate, replacement))
        if not replacements:
            fail(
                "accepted Step2 path segment disappeared in q3 without an "
                f"accepted structural replacement: {event['event_id']}"
            )
        candidate, replacement = sorted(
            replacements,
            key=lambda pair: (
                pair[0]["action"] == "filter_component",
                int(pair[0]["q_before"]["end"])
                - int(pair[0]["q_before"]["start"]),
                str(pair[0]["event_id"]),
            ),
        )[0]
        event["status"] = "superseded"
        event["reason"] = f"accepted_then_removed_by_step3:{candidate['event_id']}"
        event["superseded_by_event_id"] = replacement["event_id"]
        event["final_path_segment_id"] = ""
        replacement.setdefault("superseded_event_ids", []).append(event["event_id"])
        superseded[str(event["event_id"])] = str(replacement["event_id"])
        superseded_path_evidence.update(path_evidence)
    if not superseded:
        return
    for row in step2["usage_rows"]:
        if row["event_id"] not in superseded:
            continue
        if row["status"] == "consumed":
            row["status"] = "superseded"
        row["final_path_segment_id"] = ""
        row["reason"] = "accepted_then_removed_by_step3"
    for row in step2["evidence_rows"]:
        if row["evidence_id"] in superseded_path_evidence and row["status"] == "accepted":
            row["status"] = "superseded"


def execute(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != SCHEMA_VERSION
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; Step2/3 has no legacy fallback")
    recipe = read_single(
        server_dir / "metadata/grt_recipe.tsv",
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
    )
    donor_set, donor_members, _donor_freeze = verify_donor_freeze(server_dir, recipe)
    sources = source_catalog(server_dir)
    assignments = assignment_map(server_dir)
    all_q_rows = read_tsv(server_dir / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS)
    q1_rows = [row for row in all_q_rows if row["q_version"] == "q1"]
    if not q1_rows or not (server_dir / "grt/q/q1.fa").is_file():
        fail("Step2 requires a completed q1/Step1 mapping")
    chromosome_order, q1_paths, q1_records = load_q_paths(server_dir, "q1", q1_rows, sources)
    tools = {
        "nucmer": executable_identity(args.nucmer),
        "delta-filter": executable_identity(args.delta_filter),
        "show-coords": executable_identity(args.show_coords),
    }
    minimap = executable_identity(args.minimap2)
    existing_usage = read_tsv(server_dir / "metadata/grt_donor_usage.tsv", USAGE_FIELDS)
    existing_events = [
        json.loads(line)
        for line in (server_dir / "metadata/grt_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    initial_consumed = consumed_intervals(
        [row for row in existing_usage if row["stage"].startswith("step1_")],
        existing_events,
    )
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "donor_set_id": donor_set["donor_set_id"],
            "q1_sha256": sha256_file(server_dir / "grt/q/q1.fa"),
            "engine_version": ENGINE_VERSION,
            "engine_sha256": ENGINE_SHA256,
            "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        },
        24,
    )
    step2, _step2_cached = run_step2(
        server_dir,
        run_id,
        chromosome_order,
        q1_paths,
        q1_records,
        q1_rows,
        donor_set,
        donor_members,
        assignments,
        sources,
        initial_consumed,
        tools,
        minimap,
        args.threads,
        args.repair_mode,
    )
    publish_step23_metadata(server_dir, [step2], tools, minimap)
    _, q2_paths, q2_records = load_q_paths(server_dir, "q2", step2["q_rows"], sources)
    step3_consumed = [*initial_consumed, *step2["accepted_intervals"]]
    step3, _step3_cached = run_step3(
        server_dir,
        run_id,
        chromosome_order,
        q2_paths,
        q2_records,
        step2["q_rows"],
        donor_set,
        donor_members,
        assignments,
        sources,
        recipe["primary_dataset"],
        step3_consumed,
        tools,
        minimap,
        args.threads,
        args.repair_mode,
    )
    reconcile_step2_events_with_step3(step2, step3)
    publish_step23_metadata(server_dir, [step2, step3], tools, minimap)
    if step2["donor_set_id"] != donor_set["donor_set_id"] or step3["donor_set_id"] != donor_set["donor_set_id"]:
        fail("Step2/3 do not reference the same frozen donor set as Step1")
    if step2["target_sha256"] != donor_set["fasta_sha256"] or step3["target_sha256"] != donor_set["fasta_sha256"]:
        fail("Step2/3 donor FASTA hash drifted from frozen D0")
    print(
        f"GRT Step2/3 complete: run={run_id}, donor_set={donor_set['donor_set_id']}, "
        f"q3_sha256={sha256_file(server_dir / 'grt/q/q3.fa')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--nucmer", default="nucmer")
    parser.add_argument("--delta-filter", dest="delta_filter", default="delta-filter")
    parser.add_argument("--show-coords", dest="show_coords", default="show-coords")
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument(
        "--repair-mode",
        choices=sorted(REPAIR_MODES),
        default=DEFAULT_REPAIR_MODE,
        help="CorrectRefill structural repair mode (default: aggressive)",
    )
    args = parser.parse_args()
    if args.threads < 1:
        fail("threads must be a positive integer")
    execute(args)


if __name__ == "__main__":
    main()
