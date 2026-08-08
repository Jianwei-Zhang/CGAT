#!/usr/bin/env python3

"""Run traceable GRT PatchRepair and CorrectRefill against one frozen D0."""

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

from grt_prepare_inputs import (
    CHR_ASSIGNMENT_FIELDS,
    EVIDENCE_FIELDS,
    Q_SEGMENT_FIELDS,
    WORKFLOW,
    canonical_json,
    executable_identity,
    read_tsv,
    reverse_complement,
    sha256_bytes,
    sha256_file,
    stable_id,
    write_fasta,
    write_tsv,
)
from grt_step1 import (
    ATTEMPT_FIELDS,
    STAGE_FIELDS,
    TOOL_FIELDS,
    USAGE_FIELDS,
    apply_round,
    atomic_write_jsonl,
    atomic_write_tsv,
    build_candidates,
    build_flanks,
    cached_chromosome_alignment,
    commit_stage_directory,
    fasta_bytes,
    gap_objects,
    json_hash,
    load_q_paths,
    member_source_interval,
    parse_paf,
    path_sequence,
    q_rows_for_paths,
    read_fasta_allow_empty,
    read_single,
    slice_path,
    source_assignment,
    source_catalog,
    stage_evidence_rows,
    stage_status_row,
    verify_donor_freeze,
    write_checkpoint,
    write_jsonl,
)


ENGINE_VERSION = 2
MUMMER_MIN_CLUSTER = 1_000
MUMMER_MIN_MATCH = 100
MUMMER_MIN_ALIGNMENT = 10_000
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
NORMALIZED_GAP_LENGTH = 100
MINIMAP_PRESET = "asm5"
REPAIR_MODES = {"conservative", "aggressive"}
DEFAULT_REPAIR_MODE = "aggressive"

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


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def command_identity(identity: dict[str, str]) -> dict[str, str]:
    return {
        "resolved": identity["resolved"],
        "sha256": identity["sha256"],
        "version": identity["version"],
    }


def run_logged(
    command: list[str],
    cwd: Path,
    command_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    stdout_redirect: Path | None = None,
) -> None:
    command_path.write_text(shlex.join(command) + "\n", encoding="utf-8", newline="")
    with stderr_path.open("w", encoding="utf-8", newline="") as stderr_handle:
        if stdout_redirect is None:
            with stdout_path.open("w", encoding="utf-8", newline="") as stdout_handle:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    check=False,
                )
        else:
            stdout_path.write_text("redirected to " + stdout_redirect.name + "\n", encoding="utf-8")
            with stdout_redirect.open("w", encoding="utf-8", newline="") as output_handle:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    stdout=output_handle,
                    stderr=stderr_handle,
                    check=False,
                )
    if completed.returncode != 0:
        fail(
            f"command failed with exit code {completed.returncode}; "
            f"command={command_path}, stderr={stderr_path}"
        )


def mummer_parameters(threads: int) -> dict[str, object]:
    return {
        "nucmer": {
            "min_cluster": MUMMER_MIN_CLUSTER,
            "min_match": MUMMER_MIN_MATCH,
            "batch": 500_000_000,
            "threads": threads,
        },
        "delta_filter": {"reference_best": True, "min_alignment": MUMMER_MIN_ALIGNMENT},
        "show_coords": {"reference_sorted": True, "include_lengths": True},
    }


def parse_mummer_coords(
    path: Path,
    stage: str,
    chromosome: str,
    chromosome_length: int,
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("/")
                or stripped.startswith("NUCMER")
                or stripped.startswith("[")
                or stripped.startswith("=")
            ):
                continue
            fields = [value for value in stripped.split() if value != "|"]
            if len(fields) < 11:
                fail(f"invalid MUMmer coords row at {path}:{line_number}")
            try:
                ref_start, ref_end, query_start, query_end = map(int, fields[:4])
                ref_aligned, query_aligned = map(int, fields[4:6])
                identity = float(fields[6])
                ref_length, query_length = map(int, fields[7:9])
            except ValueError:
                fail(f"non-numeric MUMmer coords row at {path}:{line_number}")
            ref_record, query_record = fields[-2:]
            if ref_record not in members_by_record:
                fail(f"MUMmer coords references unknown D0 member at {path}:{line_number}")
            if query_record != chromosome:
                fail(f"MUMmer coords query is not {chromosome} at {path}:{line_number}")
            if ref_length != donor_lengths[ref_record] or query_length != chromosome_length:
                fail(f"MUMmer coords length columns disagree with FASTA at {path}:{line_number}")
            if not (
                1 <= min(ref_start, ref_end) <= max(ref_start, ref_end) <= ref_length
                and 1 <= min(query_start, query_end) <= max(query_start, query_end) <= query_length
                and ref_aligned >= 1
                and query_aligned >= 1
                and 0 <= identity <= 100
            ):
                fail(f"MUMmer coords has invalid coordinates at {path}:{line_number}")
            member = members_by_record[ref_record]
            orientation = "+" if (ref_end - ref_start) * (query_end - query_start) >= 0 else "-"
            rows.append(
                {
                    "stage": stage,
                    "chr": chromosome,
                    "line_number": line_number,
                    "member_id": member["member_id"],
                    "source_dataset": member["dataset_name"],
                    "source_contig": member["contig_name"],
                    "ref_record": ref_record,
                    "ref_start": ref_start,
                    "ref_end": ref_end,
                    "ref_min": min(ref_start, ref_end),
                    "ref_max": max(ref_start, ref_end),
                    "query_start": query_start,
                    "query_end": query_end,
                    "query_min": min(query_start, query_end),
                    "query_max": max(query_start, query_end),
                    "orientation": orientation,
                    "identity": identity / 100.0,
                    "ref_aligned": ref_aligned,
                    "query_aligned": query_aligned,
                    "ref_length": ref_length,
                    "query_length": query_length,
                    "raw_line": line,
                }
            )
    return rows


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
) -> tuple[Path, bool, str]:
    query_payload = fasta_bytes([(chromosome, q_sequence)])
    parameters = mummer_parameters(threads)
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "q_segments_sha256": json_hash(q_segment_rows),
        "query_artifact_sha256": sha256_bytes(query_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tools": {name: command_identity(value) for name, value in tools.items()},
        "parameters": parameters,
        "should_align": should_align,
    }
    fingerprint = json_hash(fingerprint_payload)
    chromosome_key = stable_id("chr", chromosome, 16)
    cache_parent = server_dir / f"grt/cache/step23/{stage}/mummer/{chromosome_key}"
    cache_dir = cache_parent / fingerprint
    checkpoint_path = cache_dir / "cache.json"
    output_names = [
        "query.fa",
        "result.delta",
        "result.filtered.delta",
        "result.coords",
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
        delta = temporary / "result.delta"
        filtered = temporary / "result.filtered.delta"
        coords = temporary / "result.coords"
        if should_align:
            donor_path = server_dir / donor_set["fasta_relpath"]
            prefix = temporary / "result"
            nucmer_command = [
                tools["nucmer"]["resolved"],
                "-c",
                str(MUMMER_MIN_CLUSTER),
                "-l",
                str(MUMMER_MIN_MATCH),
                "--batch=500000000",
                "-t",
                str(threads),
                "-p",
                str(prefix),
                str(donor_path),
                str(temporary / "query.fa"),
            ]
            run_logged(
                nucmer_command,
                temporary,
                temporary / "nucmer.command.txt",
                temporary / "nucmer.stdout.log",
                temporary / "nucmer.stderr.log",
            )
            if not delta.is_file() or delta.stat().st_size == 0:
                fail(f"nucmer did not create a non-empty delta for {stage}:{chromosome}")
            filter_command = [
                tools["delta-filter"]["resolved"],
                "-r",
                "-l",
                str(MUMMER_MIN_ALIGNMENT),
                str(delta),
            ]
            run_logged(
                filter_command,
                temporary,
                temporary / "delta_filter.command.txt",
                temporary / "delta_filter.stdout.log",
                temporary / "delta_filter.stderr.log",
                filtered,
            )
            if not filtered.is_file():
                fail(f"delta-filter did not create output for {stage}:{chromosome}")
            coords_command = [
                tools["show-coords"]["resolved"],
                "-r",
                "-l",
                str(filtered),
            ]
            run_logged(
                coords_command,
                temporary,
                temporary / "show_coords.command.txt",
                temporary / "show_coords.stdout.log",
                temporary / "show_coords.stderr.log",
                coords,
            )
            if not coords.is_file():
                fail(f"show-coords did not create output for {stage}:{chromosome}")
        else:
            for path in (delta, filtered, coords):
                path.write_bytes(b"")
            for prefix in ("nucmer", "delta_filter", "show_coords"):
                (temporary / f"{prefix}.command.txt").write_text(
                    "skipped: no remaining gap or frozen D0 is empty\n",
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
) -> tuple[list[dict[str, object]], dict[str, dict[str, str]], list[dict[str, object]]]:
    members_by_record = {row["fasta_record_name"]: row for row in donor_members}
    donor_records = dict(read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"]))
    if set(members_by_record) != set(donor_records):
        fail("ordinary D0 FASTA records differ from its frozen member manifest")
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
            donor_set,
            members_by_record,
            donor_lengths,
            tools,
            threads,
            should_align,
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
                    if not reason and patch_start >= patch_end:
                        reason = "empty_patch_interval"
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
        "stage": "step2_candidate_validation",
        "chr": chromosome,
        "q_source_sha256": q_source_sha256,
        "q_chromosome_sha256": sha256_bytes(q_sequence.encode("ascii")),
        "query_sha256": sha256_bytes(query_payload),
        "target_sha256": sha256_bytes(target_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
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


def intervals_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return left_start <= right_end and right_start <= left_end


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


def arbitrate(
    candidates: list[dict[str, object]],
    consumed: list[dict[str, object]],
) -> list[dict[str, object]]:
    valid = [row for row in candidates if row.get("outcome") == "candidate"]
    ordered = sorted(
        valid,
        key=lambda row: (
            -int(bool(row.get("validation_passed", False))),
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
        source_collision = next(
            (
                row
                for row in occupied_sources
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
        if source_collision is not None:
            candidate["outcome"] = "conflicted"
            blocker = source_collision.get("candidate_id") or source_collision.get("usage_id") or "prior_usage"
            candidate["reason"] = f"source_interval_consumed_by:{blocker}"
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
        candidate["reason"] = "accepted_by_global_interval_arbitration"
        accepted_objects.add(object_id)
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


def candidate_table_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        row = {field: candidate.get(field, "") for field in CANDIDATE_FIELDS}
        row["identity"] = f"{float(candidate['identity']):.9f}"
        row["validation_passed"] = str(bool(candidate.get("validation_passed", False))).lower()
        rows.append(row)
    return rows


def assignment_map(server_dir: Path) -> dict[tuple[str, str], set[str]]:
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in read_tsv(
        server_dir / "metadata/chr_assignments.tsv",
        CHR_ASSIGNMENT_FIELDS,
    ):
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    return assignments


def consumed_intervals(usage_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "candidate_id": row.get("event_id") or row["usage_id"],
            "usage_id": row["usage_id"],
            "source_dataset": row["source_dataset"],
            "source_contig": row["source_contig"],
            "source_start": int(row["source_start"]),
            "source_end": int(row["source_end"]),
            "stage": row["stage"],
        }
        for row in usage_rows
        if row["status"] in {"consumed", "accepted", "superseded"}
    ]


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


def checkpoint_result(server_dir: Path, stage: str, fingerprint: str) -> dict[str, object] | None:
    checkpoint_path = server_dir / f"grt/checkpoints/{stage}.json"
    if not checkpoint_path.is_file():
        return None
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        hashes = checkpoint.get("output_hashes", {})
        if (
            checkpoint.get("workflow") != WORKFLOW
            or checkpoint.get("stage") != stage
            or checkpoint.get("status") != "success"
            or checkpoint.get("input_fingerprint") != fingerprint
            or not hashes
        ):
            return None
        for relpath, expected in hashes.items():
            path = server_dir / relpath
            if not path.is_file() or sha256_file(path) != expected:
                return None
        result = json.loads((server_dir / checkpoint["result_relpath"]).read_text(encoding="utf-8"))
        if result.get("stage") != stage or result.get("input_fingerprint") != fingerprint:
            return None
        return result
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def step2_strategy(gap_count: int, patch_candidate_count: int, accepted_patch_count: int) -> str:
    """Return the GRT controller branch for one chromosome."""
    if gap_count == 0:
        return "no_gaps"
    if patch_candidate_count == 0:
        return "no_patch_fixer"
    if accepted_patch_count == 0:
        return "full_fixer_reuse_patches"
    return "partial_success_no_fixer"


def invalidate_from(server_dir: Path, stage: str) -> None:
    order = ["step2", "step3"]
    outputs = {"step2": "q2", "step3": "q3"}
    start = order.index(stage)
    for invalid_stage in order[start:]:
        (server_dir / f"grt/checkpoints/{invalid_stage}.json").unlink(missing_ok=True)
        (server_dir / f"grt/q/{outputs[invalid_stage]}.fa").unlink(missing_ok=True)
        artifact = server_dir / f"grt/evidence/{invalid_stage}"
        if artifact.is_dir():
            shutil.rmtree(artifact)
    for downstream_stage in ("step4_telomere", "finalize"):
        (server_dir / f"grt/checkpoints/{downstream_stage}.json").unlink(missing_ok=True)
    (server_dir / "grt/q/q4.fa").unlink(missing_ok=True)
    step4_artifact = server_dir / "grt/evidence/step4_telomere"
    if step4_artifact.is_dir():
        shutil.rmtree(step4_artifact)
    (server_dir / "metadata/grt_final_path.json").unlink(missing_ok=True)


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
        "stage": stage,
        "q_version": "q1",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        "mummer_parameters": mummer_parameters(threads),
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
    invalidate_from(server_dir, stage)
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
        candidates = arbitrate(candidates, consumed)
        validated_patch_counts = {
            chromosome: sum(
                1 for row in candidates
                if str(row["chr"]) == chromosome and row.get("validation_passed")
            )
            for chromosome in chromosome_order
        }
        accepted_patch_counts = {
            chromosome: sum(
                1 for row in candidates
                if str(row["chr"]) == chromosome and row.get("outcome") == "accepted"
            )
            for chromosome in chromosome_order
        }
        strategy_rows: list[dict[str, object]] = []
        fallback_candidates: list[dict[str, object]] = []
        for chromosome in chromosome_order:
            gap_count = sum(1 for gap in gaps if str(gap["chr"]) == chromosome)
            patch_count = patch_candidate_counts[chromosome]
            accepted_count = accepted_patch_counts[chromosome]
            strategy = step2_strategy(gap_count, patch_count, accepted_count)
            if strategy in {"no_patch_fixer", "full_fixer_reuse_patches"}:
                chromosome_gaps = [gap for gap in gaps if str(gap["chr"]) == chromosome]
                chromosome_alignments = [row for row in alignments if str(row["chr"]) == chromosome]
                fallback_candidates.extend(
                    build_step2_fallback_candidates(
                        chromosome_gaps,
                        chromosome_alignments,
                        members_by_record,
                        sources,
                        repair_mode=repair_mode,
                    )
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
        if fallback_candidates:
            fallback_candidates = arbitrate(fallback_candidates, consumed)
            candidates.extend(fallback_candidates)
        fallback_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in fallback_candidates:
            fallback_by_chr[str(row["chr"])].append(row)
        for strategy_row in strategy_rows:
            rows = fallback_by_chr.get(strategy_row["chr"], [])
            strategy_row["fallback_candidate_count"] = len(rows)
            strategy_row["accepted_fallback_count"] = sum(
                1 for row in rows if row.get("outcome") == "accepted"
            )
            if strategy_row["strategy"] == "partial_success_no_fixer":
                strategy_row["strategy_applied"] = "patcher_result"
                strategy_row["reason"] = "at_least_one_validated_patch_accepted"
            elif strategy_row["accepted_fallback_count"]:
                strategy_row["strategy_applied"] = (
                    "fixer_and_new_patches"
                    if strategy_row["strategy"] == "no_patch_fixer"
                    else "fixer_and_reused_patches"
                )
                strategy_row["reason"] = "correctrefill_source_retry_accepted"
            else:
                strategy_row["strategy_applied"] = "fixer_only"
                strategy_row["reason"] = "no_validated_fallback_source_interval"
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
                    preset="nucmer-c1000-l100;delta-filter-r-l10000;show-coords-r-l",
                    parameters=mummer_parameters(threads),
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
                        evidence_type="correctrefill_fallback",
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
                        preset="grt-type1-type6-source-retry",
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
        output_paths, output_records, events, usage_rows, attempts = apply_round(
            run_id,
            stage,
            "q1",
            "q2",
            chromosome_order,
            input_paths,
            input_records,
            gaps,
            candidates,
            assignments,
            q_input_sha256,
            sources,
            action="patch",
        )
        candidate_by_event = {
            str(candidate.get("event_id")): candidate
            for candidate in candidates
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
            if candidate.get("fallback"):
                event["fallback"] = {
                    "parent_candidate_id": candidate.get("fallback_parent_candidate_id", ""),
                    "strategy": candidate.get("fallback_strategy", ""),
                    "error_type": candidate.get("error_type", "unknown"),
                    "error_subtype": candidate.get("error_subtype", "unspecified"),
                    "repair_mode": repair_mode,
                }
        for row in usage_rows:
            row["donor_set_id"] = donor_set["donor_set_id"]
        q_rows = q_rows_for_paths("q2", chromosome_order, output_paths)
        write_fasta(q_output_temporary, [(chromosome, output_records[chromosome]) for chromosome in chromosome_order])
        q_output_sha256 = sha256_file(q_output_temporary)
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
            if row["outcome"] == "accepted"
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
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

    feature_names: list[str] = []
    if features["query_overlap"]:
        feature_names.append(f"query_overlap_{features['query_overlap_length']}")
    if features["ref_overlap"]:
        feature_names.append(f"ref_overlap_{features['ref_overlap_length']}")
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
    elif features["ref_overlap"] and float(features["ref_overlap_ratio"]) >= 0.10:
        error_type = "type5"
        overlap = int(features["ref_overlap_length"])
        subtype = "small_ref_overlap" if overlap < 10_000 else (
            "medium_ref_overlap" if overlap < 50_000 else "large_ref_overlap"
        )
    elif features["ref_overlap"]:
        error_type, subtype = "type4", "small_ref_overlap"
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


def _step3_project_ref_interval(row: dict[str, object], ref_start: int, ref_end: int) -> tuple[int, int]:
    ref_min, ref_max = int(row["ref_min"]), int(row["ref_max"])
    query_min, query_max = int(row["query_min"]), int(row["query_max"])
    ref_span = max(1, ref_max - ref_min)
    query_span = max(1, query_max - query_min)
    if row["orientation"] == "+":
        start = query_min + round((ref_start - ref_min) * query_span / ref_span)
        end = query_min + round((ref_end - ref_min) * query_span / ref_span)
    else:
        start = query_max - round((ref_end - ref_min) * query_span / ref_span)
        end = query_max - round((ref_start - ref_min) * query_span / ref_span)
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
        return max(1, query_start - CORRECTION_MARGIN), query_end, "reference_overlap_with_margin"
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
    lefts = [row for row in chromosome_alignments if int(row["query_max"]) < gap_pos]
    rights = [row for row in chromosome_alignments if int(row["query_min"]) > gap_pos]
    lefts = [row for row in lefts if gap_pos - int(row["query_max"]) <= CORRECTION_SEARCH_RANGE]
    rights = [row for row in rights if int(row["query_min"]) - gap_pos <= CORRECTION_SEARCH_RANGE]
    if not lefts or not rights:
        return []
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    seen: set[tuple[int, int]] = set()
    grouped_left: dict[str, list[dict[str, object]]] = defaultdict(list)
    grouped_right: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in lefts:
        grouped_left[str(row["ref_record"])].append(row)
    for row in rights:
        grouped_right[str(row["ref_record"])].append(row)
    for ref_record in sorted(set(grouped_left) & set(grouped_right)):
        left = max(grouped_left[ref_record], key=lambda row: (int(row["query_max"]), float(row["identity"]), -int(row["line_number"])))
        right = min(grouped_right[ref_record], key=lambda row: (int(row["query_min"]), -float(row["identity"]), int(row["line_number"])))
        seen.add((int(left["line_number"]), int(right["line_number"])))
        pairs.append((left, right))
    left = max(lefts, key=lambda row: (int(row["query_max"]), float(row["identity"]), -int(row["line_number"])))
    right = min(rights, key=lambda row: (int(row["query_min"]), -float(row["identity"]), int(row["line_number"])))
    if (int(left["line_number"]), int(right["line_number"])) not in seen:
        pairs.append((left, right))
    return pairs


def build_correction_candidates(
    gaps: list[dict[str, object]],
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    repair_mode: str = DEFAULT_REPAIR_MODE,
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
        gap_pos = int(gap["start0"]) + 1
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
            query_length = int(left["query_length"])
            start = max(1, min(start, query_length))
            end = max(start, min(end, query_length))
            eligible, repair_reason = _step3_repair_decision(
                error_type, confidence_score, left, right, start, end, repair_mode
            )
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
                    "validation_passed": True,
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
    Server mode the donor source and coordinates are already explicit, so the
    equivalent retry can use the validated source interval directly.  This
    avoids reconstructing implicit assemblies while still reusing the same
    Type1--Type6 boundary decision and donor provenance.
    """
    structural = build_correction_candidates(
        gaps, alignments, members_by_record, repair_mode=repair_mode
    )
    fallback: list[dict[str, object]] = []
    for correction in structural:
        if not correction.get("eligible", True):
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


def correction_usage_rows(
    run_id: str,
    donor_set_id: str,
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        event_id = stable_id("event", [run_id, "step3", candidate["object_id"], "correction"], 24)
        candidate["event_id"] = event_id
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
        cursor = 0
        output_cursor = 0
        result_path: list[dict[str, object]] = []
        accepted_by_object = {str(row["object_id"]): row for row in accepted}
        for candidate in accepted:
            start0 = int(candidate["input_start"]) - 1
            end0 = int(candidate["input_end"])
            if start0 < cursor or end0 < start0 or end0 > len(sequence):
                fail(f"overlapping or invalid Step3 correction edit: {candidate['candidate_id']}")
            result_path.extend(slice_path(path, cursor, start0))
            output_cursor += start0 - cursor
            gap_segment = {
                "segment_kind": "gap",
                "length": NORMALIZED_GAP_LENGTH,
                "dataset_name": "",
                "contig_name": "",
                "source_start": None,
                "source_end": None,
                "orientation": "",
                "source_card_key": "",
                "evidence_ids": [],
            }
            result_path.append(gap_segment)
            output_start = output_cursor + 1
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
            }
            prototypes.append(prototype)
            gap_origin_by_output[(chromosome, output_start - 1, output_end)] = {
                "object_id": candidate["object_id"],
                "q2_start": int(candidate["input_start"]),
                "q2_end": int(candidate["input_end"]),
                "correction_candidate_id": candidate["candidate_id"],
            }
        result_path.extend(slice_path(path, cursor, len(sequence)))
        output_paths[chromosome] = result_path
        output_records[chromosome] = path_sequence(result_path, sources)
        chromosome_gaps = [gap for gap in gaps if gap["chr"] == chromosome]
        for gap in chromosome_gaps:
            if str(gap["object_id"]) in accepted_by_object:
                continue
            shift = 0
            for candidate in accepted:
                if int(candidate["input_end"]) < int(gap["start0"]) + 1:
                    shift += NORMALIZED_GAP_LENGTH - (
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
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, dict[str, str]],
    list[dict[str, object]],
]:
    flank_records, gaps, query_map = build_flanks("q2_corrected", chromosome_order, records)
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
        "q_source": "q2_after_mummer_corrections",
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
            "step3_refill",
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
        print(f"GRT step3 refill {chromosome}: {'cache hit' if cache_hit else 'computed'}")
        destination = temporary / "refill" / "by_chr" / chromosome_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cache_dir, destination)
        paf = destination / "result.paf"
        paf_parts.append(paf.read_bytes())
        paf_rows.extend(parse_paf(paf, chromosome_query_map, target_lengths))
        artifact_identities[chromosome] = {
            "query_relpath": f"{artifact_relpath}/refill/by_chr/{chromosome_key}/flanks.fa",
            "query_sha256": sha256_file(destination / "flanks.fa"),
            "raw_relpath": f"{artifact_relpath}/refill/by_chr/{chromosome_key}/result.paf",
            "raw_sha256": sha256_file(paf),
        }
    (temporary / "refill" / "flanks.fa").write_bytes(fasta_bytes(flank_records))
    (temporary / "refill" / "result.paf").write_bytes(b"".join(paf_parts))
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
            original_assignment, _placement_mode, _source_card_key = source_assignment(assignments, candidate)
            source_card_key = ""
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
                    "replacement_kind": "gap",
                    "input_coordinate_space": "q2_1_based_closed",
                    "input_start": int(candidate["input_start"]),
                    "input_end": int(candidate["input_end"]),
                    "intermediate_output_start": prototype["intermediate_start"],
                    "intermediate_output_end": prototype["intermediate_end"],
                    "replacement_length": NORMALIZED_GAP_LENGTH,
                    "replacement_sequence_sha256": sha256_bytes(("N" * NORMALIZED_GAP_LENGTH).encode("ascii")),
                },
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
    refill_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in refill_events:
        if event["status"] == "accepted":
            refill_by_chr[str(event["chr"])].append(event)
    output: dict[str, str] = {}
    for chromosome, sequence in corrected.items():
        cursor = 0
        parts = []
        for event in sorted(refill_by_chr.get(chromosome, []), key=lambda row: int(row["edit"]["input_start"])):
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
        "stage": stage,
        "q_version": "q2",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tools": {name: command_identity(value) for name, value in {**tools, "minimap2": minimap}.items()},
        "mummer_parameters": mummer_parameters(threads),
        "correction_parameters": {
            "repair_mode": repair_mode,
            "max_search_distance": CORRECTION_SEARCH_RANGE,
            "normalized_gap_length": NORMALIZED_GAP_LENGTH,
            "reference_overlap_margin": CORRECTION_MARGIN,
        },
        "refill_parameters": {
            "preset": MINIMAP_PRESET,
            "min_alignment": REFILL_MIN_ALIGNMENT,
            "min_identity": REFILL_MIN_IDENTITY,
            "max_fill_length": REFILL_MAX_LENGTH,
        },
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT step3 cache hit: {fingerprint}")
        return cached, True
    invalidate_from(server_dir, stage)
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
        gaps = [gap for chromosome in chromosome_order for gap in gap_objects(chromosome, "q2", input_records[chromosome])]
        correction_candidates = build_correction_candidates(
            gaps, alignments, members_by_record, repair_mode=repair_mode
        )
        reject_candidates_spanning_other_gaps(correction_candidates, gaps)
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
            correction_evidence.append(
                evidence_row(
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
                    preset="nucmer-c1000-l100;delta-filter-r-l10000;show-coords-r-l",
                    parameters={
                        **mummer_parameters(threads),
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
                )
            )
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
            if row["outcome"] == "accepted"
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
        )
        attach_gap_origins(corrected_gaps, gap_origins)
        reject_candidates_spanning_other_gaps(
            refill_candidates,
            corrected_gaps,
            refill_rejections,
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
        output_paths, output_records, refill_events, refill_usage, refill_attempts = apply_round(
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
        write_fasta(q_output_temporary, [(chromosome, output_records[chromosome]) for chromosome in chromosome_order])
        q_output_sha256 = sha256_file(q_output_temporary)
        refill_by_origin = finalize_refill_origins(refill_events, corrected_gaps)
        refill_object_by_corrected = {
            str(gap["object_id"]): str(gap["origin"]["object_id"])
            for gap in corrected_gaps
        }
        for attempt in refill_attempts:
            attempt["object_id"] = refill_object_by_corrected[str(attempt["object_id"])]
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
        events = [*correction_events, *refill_events]
        attempts = [*correction_attempts, *refill_attempts]
        usage_rows = [*correction_usage, *refill_usage]
        evidence_rows = [*correction_evidence, *refill_evidence]
        if replay_step3(input_records, correction_events, refill_events, sources) != output_records:
            fail("Step3 accepted events do not deterministically reconstruct q3")
        q_rows = q_rows_for_paths("q3", chromosome_order, output_paths)
        write_tsv(temporary / "correction_candidates.tsv", CANDIDATE_FIELDS, candidate_table_rows(correction_candidates))
        write_tsv(temporary / "refill_candidates.tsv", CANDIDATE_FIELDS, candidate_table_rows(refill_candidates))
        write_tsv(temporary / "refill_rejections.tsv", REJECTION_FIELDS, refill_rejections)
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
        ]
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
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
            f"refills={sum(row['outcome'] == 'accepted' for row in refill_candidates)}"
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


def publish_metadata(
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
    atomic_write_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS, usage_rows)
    atomic_write_jsonl(metadata / "grt_events.jsonl", events)
    atomic_write_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
    atomic_write_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS, stage_rows)
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)


def execute(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != "1"
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
    initial_consumed = consumed_intervals(
        [row for row in existing_usage if row["stage"].startswith("step1_")]
    )
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "donor_set_id": donor_set["donor_set_id"],
            "q1_sha256": sha256_file(server_dir / "grt/q/q1.fa"),
            "engine_version": ENGINE_VERSION,
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
    publish_metadata(server_dir, [step2], tools, minimap)
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
        step3_consumed,
        tools,
        minimap,
        args.threads,
        args.repair_mode,
    )
    publish_metadata(server_dir, [step2, step3], tools, minimap)
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
