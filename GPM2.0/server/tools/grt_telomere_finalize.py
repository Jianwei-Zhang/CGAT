#!/usr/bin/env python3

"""Recover missing q3 telomeres from frozen Dtel and finalize traceable q4."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from grt_prepare_inputs import (
    DONOR_MEMBER_FIELDS,
    EVIDENCE_FIELDS,
    Q_SEGMENT_FIELDS,
    WORKFLOW,
    canonical_json,
    executable_identity,
    read_fasta,
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
    atomic_write_jsonl,
    atomic_write_tsv,
    commit_stage_directory,
    fasta_bytes,
    json_hash,
    load_q_paths,
    member_source_interval,
    path_sequence,
    q_rows_for_paths,
    read_fasta_allow_empty,
    read_single,
    slice_path,
    source_assignment,
    source_catalog,
    stage_status_row,
    write_checkpoint,
    write_jsonl,
)
from grt_step23 import (
    command_identity,
    intervals_overlap,
    parse_mummer_coords,
    run_logged,
)


ENGINE_VERSION = 1
END_SEARCH_WINDOW = 2_000
ALIGNMENT_QUERY_WINDOW = 5_000_000
MAX_EXTRACT_LENGTH = 5_000_000
MUMMER_MIN_CLUSTER = 1_000
MUMMER_MIN_MATCH = 100
MUMMER_MIN_ALIGNMENT = 10_000
CANDIDATE_MIN_ALIGNMENT = 15_000
CANDIDATE_MIN_IDENTITY = 0.99
MINIMAP_PRESET = "asm5"
MINIMAP_MIN_IDENTITY = 0.99
MINIMAP_MIN_OVERLAP = 3_000
MINIMAP_MIN_MAPQ = 20

RULE_FIELDS = [
    "rule_id",
    "motif",
    "chromosome_min_repeat",
    "donor_min_repeat",
    "min_telomere_bp",
    "source",
]
TERMINAL_FIELDS = [
    "chr",
    "terminal",
    "q3_start",
    "q3_end",
    "initial_status",
    "final_status",
    "matched_rule_ids_json",
    "candidate_count",
    "accepted_event_id",
    "reason",
]
CANDIDATE_FIELDS = [
    "candidate_id",
    "chr",
    "terminal",
    "object_id",
    "rank",
    "member_id",
    "source_dataset",
    "source_contig",
    "extract_source_start",
    "extract_source_end",
    "used_source_start",
    "used_source_end",
    "orientation",
    "mummer_identity",
    "mummer_aligned_length",
    "minimap_identity",
    "minimap_overlap",
    "minimap_mapq",
    "target_start",
    "target_end",
    "extension_length",
    "telomere_bp",
    "telomere_repeat_count",
    "matched_rule_ids_json",
    "mummer_evidence_id",
    "minimap_evidence_id",
    "outcome",
    "reason",
    "event_id",
    "final_path_segment_id",
]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load_telomere_rules(server_dir: Path) -> list[dict[str, object]]:
    rows = read_tsv(server_dir / "metadata/grt_telomere_rules.tsv", RULE_FIELDS)
    rules: list[dict[str, object]] = []
    seen: set[tuple[str, int, int, int]] = set()
    for row in rows:
        motif = row["motif"].upper()
        if not motif or re.search(r"[^ACGT]", motif):
            fail(f"invalid telomere motif in rule {row['rule_id']}")
        rule = {
            "rule_id": row["rule_id"],
            "motif": motif,
            "chromosome_min_repeat": int(row["chromosome_min_repeat"]),
            "donor_min_repeat": int(row["donor_min_repeat"]),
            "min_telomere_bp": int(row["min_telomere_bp"]),
            "source": row["source"],
        }
        if min(
            int(rule["chromosome_min_repeat"]),
            int(rule["donor_min_repeat"]),
            int(rule["min_telomere_bp"]),
        ) < 1:
            fail(f"telomere rule {row['rule_id']} has a non-positive threshold")
        key = (
            motif,
            int(rule["chromosome_min_repeat"]),
            int(rule["donor_min_repeat"]),
            int(rule["min_telomere_bp"]),
        )
        if key not in seen:
            seen.add(key)
            rules.append(rule)
    if not rules:
        fail("no telomere rules are available")
    return rules


def tandem_matches(
    sequence: str,
    rules: list[dict[str, object]],
    threshold_field: str,
    require_min_bp: bool,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    sequence = sequence.upper()
    for rule in rules:
        motif = str(rule["motif"])
        minimum = int(rule[threshold_field])
        for match in re.finditer(f"(?:{re.escape(motif)}){{{minimum},}}", sequence):
            length = match.end() - match.start()
            if require_min_bp and length < int(rule["min_telomere_bp"]):
                continue
            matches.append(
                {
                    "rule_id": rule["rule_id"],
                    "start0": match.start(),
                    "end0": match.end(),
                    "length": length,
                    "repeat_count": length // len(motif),
                }
            )
    return sorted(
        matches,
        key=lambda row: (
            -int(row["length"]),
            -int(row["repeat_count"]),
            str(row["rule_id"]),
            int(row["start0"]),
        ),
    )


def terminal_signal(
    sequence: str,
    terminal: str,
    rules: list[dict[str, object]],
) -> dict[str, object]:
    window_length = min(END_SEARCH_WINDOW, len(sequence))
    offset = 0 if terminal == "5prime" else len(sequence) - window_length
    window = sequence[offset : offset + window_length]
    matches = tandem_matches(window, rules, "chromosome_min_repeat", False)
    return {
        "present": bool(matches),
        "window_start": offset + 1,
        "window_end": offset + window_length,
        "matched_rule_ids": sorted({str(row["rule_id"]) for row in matches}),
        "max_telomere_bp": max((int(row["length"]) for row in matches), default=0),
        "max_repeat_count": max((int(row["repeat_count"]) for row in matches), default=0),
    }


def candidate_terminal_signal(
    sequence: str,
    terminal: str,
    rules: list[dict[str, object]],
) -> dict[str, object]:
    matches = tandem_matches(sequence, rules, "donor_min_repeat", True)
    boundary = max(1, len(sequence) // 10)
    if terminal == "5prime":
        terminal_matches = [row for row in matches if int(row["start0"]) < boundary]
    else:
        terminal_matches = [row for row in matches if int(row["end0"]) > len(sequence) - boundary]
    return {
        "present": bool(terminal_matches),
        "matched_rule_ids": sorted({str(row["rule_id"]) for row in terminal_matches}),
        "max_telomere_bp": max((int(row["length"]) for row in terminal_matches), default=0),
        "max_repeat_count": max(
            (int(row["repeat_count"]) for row in terminal_matches), default=0
        ),
    }


def compose_orientation(left: str, right: str) -> str:
    return "+" if left == right else "-"


def oriented_interval_to_record(
    record_length: int,
    orientation: str,
    start: int,
    end: int,
) -> tuple[int, int]:
    if not (1 <= start <= end <= record_length):
        fail("invalid oriented donor interval")
    if orientation == "+":
        return start, end
    return record_length - end + 1, record_length - start + 1


def source_interval_for_oriented_record(
    member: dict[str, str],
    record_length: int,
    orientation: str,
    start: int,
    end: int,
) -> tuple[int, int, str]:
    local_start, local_end = oriented_interval_to_record(
        record_length, orientation, start, end
    )
    source_start, source_end = member_source_interval(member, local_start, local_end)
    return (
        source_start,
        source_end,
        compose_orientation(member["orientation"], orientation),
    )


def verify_telomere_donor_freeze(
    server_dir: Path,
    recipe: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, str]], dict[str, str]]:
    donor_sets = read_tsv(
        server_dir / "metadata/grt_donor_sets.tsv",
        [
            "donor_set_id",
            "donor_kind",
            "manifest_relpath",
            "fasta_relpath",
            "fasta_sha256",
            "member_count",
        ],
    )
    matching = [
        row
        for row in donor_sets
        if row["donor_set_id"] == recipe["tel_donor_set_id"]
        and row["donor_kind"] == "telomere"
    ]
    if len(matching) != 1:
        fail("recipe does not identify exactly one frozen telomere donor set")
    donor_set = matching[0]
    donor_path = server_dir / donor_set["fasta_relpath"]
    if sha256_file(donor_path) != donor_set["fasta_sha256"]:
        fail("frozen Dtel FASTA checksum changed")
    all_members = read_tsv(server_dir / "metadata/grt_donor_members.tsv", DONOR_MEMBER_FIELDS)
    members = [row for row in all_members if row["donor_set_id"] == donor_set["donor_set_id"]]
    manifest = read_tsv(server_dir / donor_set["manifest_relpath"], DONOR_MEMBER_FIELDS)
    if members != manifest or len(members) != int(donor_set["member_count"]):
        fail("frozen Dtel manifest differs from its member registry")
    records = dict(read_fasta_allow_empty(donor_path))
    if set(records) != {row["fasta_record_name"] for row in members}:
        fail("frozen Dtel FASTA records differ from its manifest")
    for member in members:
        if sha256_bytes(records[member["fasta_record_name"]].encode("ascii")) != member[
            "sequence_sha256"
        ]:
            fail(f"frozen Dtel member checksum changed: {member['member_id']}")
    donor_freeze = json.loads(
        (server_dir / "grt/checkpoints/donor_freeze.json").read_text(encoding="utf-8")
    )
    if donor_freeze.get("tel_donor_set_id") != donor_set["donor_set_id"]:
        fail("donor-freeze checkpoint does not reference the recipe Dtel")
    return donor_set, members, donor_freeze


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


def cached_terminal_mummer(
    server_dir: Path,
    chromosome: str,
    terminal: str,
    q3_sha256: str,
    chromosome_sequence: str,
    donor_set: dict[str, str],
    members_by_record: dict[str, dict[str, str]],
    donor_lengths: dict[str, int],
    tools: dict[str, dict[str, str]],
    threads: int,
    should_align: bool,
) -> tuple[Path, bool, dict[str, object]]:
    if terminal == "5prime":
        query_offset = 0
        query_sequence = chromosome_sequence[:ALIGNMENT_QUERY_WINDOW]
    else:
        query_offset = max(0, len(chromosome_sequence) - ALIGNMENT_QUERY_WINDOW)
        query_sequence = chromosome_sequence[query_offset:]
    query_name = f"{chromosome}__{terminal}"
    query_payload = fasta_bytes([(query_name, query_sequence)])
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": "step4_telomere",
        "chr": chromosome,
        "terminal": terminal,
        "q3_sha256": q3_sha256,
        "q3_chromosome_sha256": sha256_bytes(chromosome_sequence.encode("ascii")),
        "query_offset0": query_offset,
        "query_sha256": sha256_bytes(query_payload),
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "tools": {name: command_identity(identity) for name, identity in tools.items()},
        "parameters": mummer_parameters(threads),
        "should_align": should_align,
    }
    fingerprint = json_hash(fingerprint_payload)
    terminal_key = stable_id("terminal", [chromosome, terminal], 16)
    cache_parent = server_dir / f"grt/cache/telomere/mummer/{terminal_key}"
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
                    "step4_telomere",
                    query_name,
                    len(query_sequence),
                    members_by_record,
                    donor_lengths,
                )
                return cache_dir, True, {
                    "terminal_key": terminal_key,
                    "query_name": query_name,
                    "query_offset0": query_offset,
                    "query_length": len(query_sequence),
                }
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
            run_logged(
                [
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
                ],
                temporary,
                temporary / "nucmer.command.txt",
                temporary / "nucmer.stdout.log",
                temporary / "nucmer.stderr.log",
            )
            if not delta.is_file() or delta.stat().st_size == 0:
                fail(f"nucmer did not create a non-empty delta for {chromosome}:{terminal}")
            run_logged(
                [
                    tools["delta-filter"]["resolved"],
                    "-r",
                    "-l",
                    str(MUMMER_MIN_ALIGNMENT),
                    str(delta),
                ],
                temporary,
                temporary / "delta_filter.command.txt",
                temporary / "delta_filter.stdout.log",
                temporary / "delta_filter.stderr.log",
                filtered,
            )
            if not filtered.is_file():
                fail(f"delta-filter did not create output for {chromosome}:{terminal}")
            run_logged(
                [tools["show-coords"]["resolved"], "-r", "-l", str(filtered)],
                temporary,
                temporary / "show_coords.command.txt",
                temporary / "show_coords.stdout.log",
                temporary / "show_coords.stderr.log",
                coords,
            )
            if not coords.is_file():
                fail(f"show-coords did not create output for {chromosome}:{terminal}")
        else:
            for path in (delta, filtered, coords):
                path.write_bytes(b"")
            for prefix in ("nucmer", "delta_filter", "show_coords"):
                (temporary / f"{prefix}.command.txt").write_text(
                    "skipped: terminal is present or frozen Dtel is empty\n",
                    encoding="utf-8",
                    newline="",
                )
                (temporary / f"{prefix}.stdout.log").write_text("", encoding="utf-8")
                (temporary / f"{prefix}.stderr.log").write_text("", encoding="utf-8")
        parse_mummer_coords(
            coords,
            "step4_telomere",
            query_name,
            len(query_sequence),
            members_by_record,
            donor_lengths,
        )
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": "step4_telomere",
            "chr": chromosome,
            "terminal": terminal,
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
        return cache_dir, False, {
            "terminal_key": terminal_key,
            "query_name": query_name,
            "query_offset0": query_offset,
            "query_length": len(query_sequence),
        }
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step4-mummer-{terminal_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def extract_terminal_candidates(
    chromosome: str,
    terminal: str,
    object_id: str,
    alignments: list[dict[str, object]],
    members_by_record: dict[str, dict[str, str]],
    donor_records: dict[str, str],
    rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for alignment in alignments:
        if (
            float(alignment["identity"]) >= CANDIDATE_MIN_IDENTITY
            and min(int(alignment["ref_aligned"]), int(alignment["query_aligned"]))
            >= CANDIDATE_MIN_ALIGNMENT
        ):
            grouped[str(alignment["ref_record"])].append(alignment)
    candidates: list[dict[str, object]] = []
    for ref_record, rows in sorted(grouped.items()):
        record_sequence = donor_records[ref_record]
        record_length = len(record_sequence)
        oriented_rows: list[tuple[dict[str, object], int, int]] = []
        for row in rows:
            if row["orientation"] == "+":
                oriented_start = int(row["ref_min"])
                oriented_end = int(row["ref_max"])
            else:
                oriented_start = record_length - int(row["ref_max"]) + 1
                oriented_end = record_length - int(row["ref_min"]) + 1
            oriented_rows.append((row, oriented_start, oriented_end))
        if terminal == "5prime":
            selected, aligned_start, aligned_end = min(
                oriented_rows,
                key=lambda value: (
                    value[1],
                    -float(value[0]["identity"]),
                    -int(value[0]["ref_aligned"]),
                    int(value[0]["line_number"]),
                ),
            )
            extract_start = max(1, aligned_end - MAX_EXTRACT_LENGTH + 1)
            extract_end = aligned_end
        else:
            selected, aligned_start, aligned_end = max(
                oriented_rows,
                key=lambda value: (
                    value[2],
                    float(value[0]["identity"]),
                    int(value[0]["ref_aligned"]),
                    -int(value[0]["line_number"]),
                ),
            )
            extract_start = aligned_start
            extract_end = min(record_length, aligned_start + MAX_EXTRACT_LENGTH - 1)
        orientation = str(selected["orientation"])
        oriented_record = record_sequence if orientation == "+" else reverse_complement(record_sequence)
        extract_sequence = oriented_record[extract_start - 1 : extract_end]
        telomere = candidate_terminal_signal(extract_sequence, terminal, rules)
        member = members_by_record[ref_record]
        source_start, source_end, source_orientation = source_interval_for_oriented_record(
            member,
            record_length,
            orientation,
            extract_start,
            extract_end,
        )
        candidate_id = stable_id(
            "tel-candidate",
            {
                "chr": chromosome,
                "terminal": terminal,
                "member_id": member["member_id"],
                "source_start": source_start,
                "source_end": source_end,
                "orientation": source_orientation,
                "mummer_line": selected["line_number"],
            },
            24,
        )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "chr": chromosome,
                "terminal": terminal,
                "object_id": object_id,
                "member_id": member["member_id"],
                "ref_record": ref_record,
                "source_dataset": member["dataset_name"],
                "source_contig": member["contig_name"],
                "extract_source_start": source_start,
                "extract_source_end": source_end,
                "extract_record_start": extract_start,
                "extract_record_end": extract_end,
                "orientation": source_orientation,
                "record_alignment_orientation": orientation,
                "extract_sequence": extract_sequence,
                "mummer_identity": float(selected["identity"]),
                "mummer_aligned_length": min(
                    int(selected["ref_aligned"]), int(selected["query_aligned"])
                ),
                "mummer_line": int(selected["line_number"]),
                "mummer_query_start": int(selected["query_min"]),
                "mummer_query_end": int(selected["query_max"]),
                "telomere_bp": int(telomere["max_telomere_bp"]),
                "telomere_repeat_count": int(telomere["max_repeat_count"]),
                "matched_rule_ids": telomere["matched_rule_ids"],
                "outcome": "candidate" if telomere["present"] else "rejected",
                "reason": "mummer_anchor_and_terminal_repeat" if telomere["present"] else "telomere_repeat_not_at_external_end",
            }
        )
    return candidates


def parse_candidate_paf(
    path: Path,
    candidate: dict[str, object],
    target_name: str,
    target_length: int,
    target_offset0: int,
    chromosome_length: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query_name = str(candidate["candidate_id"])
    query_length = len(str(candidate["extract_sequence"]))
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                fail(f"invalid minimap2 PAF row at {path}:{line_number}")
            try:
                parsed_query_length = int(fields[1])
                query_start0 = int(fields[2])
                query_end0 = int(fields[3])
                parsed_target_length = int(fields[6])
                target_start0 = int(fields[7])
                target_end0 = int(fields[8])
                matches = int(fields[9])
                block_length = int(fields[10])
                mapq = int(fields[11])
            except ValueError:
                fail(f"non-numeric minimap2 PAF row at {path}:{line_number}")
            if (
                fields[0] != query_name
                or parsed_query_length != query_length
                or fields[5] != target_name
                or parsed_target_length != target_length
            ):
                fail(f"minimap2 PAF identity/length mismatch at {path}:{line_number}")
            if not (
                fields[4] in {"+", "-"}
                and 0 <= query_start0 < query_end0 <= query_length
                and 0 <= target_start0 < target_end0 <= target_length
                and 0 <= matches <= block_length
                and block_length > 0
                and 0 <= mapq <= 255
            ):
                fail(f"invalid minimap2 PAF coordinates at {path}:{line_number}")
            target_start = target_offset0 + target_start0 + 1
            target_end = target_offset0 + target_end0
            if target_end > chromosome_length:
                fail(f"minimap2 PAF target projection exceeds q3 at {path}:{line_number}")
            overlap = query_end0 - query_start0
            identity = matches / block_length
            rows.append(
                {
                    "line_number": line_number,
                    "raw_line": line,
                    "query_start0": query_start0,
                    "query_end0": query_end0,
                    "strand": fields[4],
                    "target_start": target_start,
                    "target_end": target_end,
                    "identity": identity,
                    "overlap": overlap,
                    "mapq": mapq,
                    "score": identity
                    * min(1.0, overlap / 5_000.0)
                    * (0.7 + 0.3 * min(1.0, mapq / 60.0)),
                }
            )
    return rows


def cached_candidate_minimap(
    server_dir: Path,
    candidate: dict[str, object],
    chromosome_sequence: str,
    q3_sha256: str,
    minimap: dict[str, str],
    threads: int,
) -> tuple[Path, bool, list[dict[str, object]], dict[str, object]]:
    terminal = str(candidate["terminal"])
    if terminal == "5prime":
        target_offset0 = 0
        target_sequence = chromosome_sequence[:ALIGNMENT_QUERY_WINDOW]
    else:
        target_offset0 = max(0, len(chromosome_sequence) - ALIGNMENT_QUERY_WINDOW)
        target_sequence = chromosome_sequence[target_offset0:]
    target_name = f"{candidate['chr']}__{terminal}__q3"
    query_name = str(candidate["candidate_id"])
    query_payload = fasta_bytes([(query_name, str(candidate["extract_sequence"]))])
    target_payload = fasta_bytes([(target_name, target_sequence)])
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": "step4_telomere",
        "candidate_id": candidate["candidate_id"],
        "q3_sha256": q3_sha256,
        "query_sha256": sha256_bytes(query_payload),
        "target_sha256": sha256_bytes(target_payload),
        "target_offset0": target_offset0,
        "tool": command_identity(minimap),
        "parameters": {
            "preset": MINIMAP_PRESET,
            "secondary": False,
            "cigar": True,
            "threads": threads,
            "min_identity": MINIMAP_MIN_IDENTITY,
            "min_overlap": MINIMAP_MIN_OVERLAP,
            "min_mapq": MINIMAP_MIN_MAPQ,
        },
    }
    fingerprint = json_hash(fingerprint_payload)
    candidate_key = stable_id("candidate", candidate["candidate_id"], 18)
    cache_parent = server_dir / f"grt/cache/telomere/minimap/{candidate_key}"
    cache_dir = cache_parent / fingerprint
    output_names = [
        "query.fa",
        "target.fa",
        "result.paf",
        "minimap2.command.txt",
        "minimap2.stdout.log",
        "minimap2.stderr.log",
    ]
    checkpoint_path = cache_dir / "cache.json"
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
                rows = parse_candidate_paf(
                    cache_dir / "result.paf",
                    candidate,
                    target_name,
                    len(target_sequence),
                    target_offset0,
                    len(chromosome_sequence),
                )
                return cache_dir, True, rows, {
                    "candidate_key": candidate_key,
                    "target_offset0": target_offset0,
                    "target_name": target_name,
                }
        except (OSError, TypeError, ValueError, json.JSONDecodeError, SystemExit):
            pass
    cache_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=cache_parent))
    try:
        (temporary / "query.fa").write_bytes(query_payload)
        (temporary / "target.fa").write_bytes(target_payload)
        run_logged(
            [
                minimap["resolved"],
                "-x",
                MINIMAP_PRESET,
                "-c",
                "--secondary=no",
                "-t",
                str(threads),
                "-o",
                str(temporary / "result.paf"),
                str(temporary / "target.fa"),
                str(temporary / "query.fa"),
            ],
            temporary,
            temporary / "minimap2.command.txt",
            temporary / "minimap2.stdout.log",
            temporary / "minimap2.stderr.log",
        )
        if not (temporary / "result.paf").is_file():
            fail(f"minimap2 did not create a PAF for {candidate['candidate_id']}")
        rows = parse_candidate_paf(
            temporary / "result.paf",
            candidate,
            target_name,
            len(target_sequence),
            target_offset0,
            len(chromosome_sequence),
        )
        checkpoint = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": "step4_telomere",
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
        return cache_dir, False, rows, {
            "candidate_key": candidate_key,
            "target_offset0": target_offset0,
            "target_name": target_name,
        }
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step4-minimap-{candidate_key}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def validate_candidate_alignment(
    candidate: dict[str, object],
    rows: list[dict[str, object]],
    member: dict[str, str],
    record_length: int,
    chromosome_length: int,
) -> None:
    valid = [
        row
        for row in rows
        if row["strand"] == "+"
        and float(row["identity"]) >= MINIMAP_MIN_IDENTITY
        and int(row["overlap"]) >= MINIMAP_MIN_OVERLAP
        and int(row["mapq"]) >= MINIMAP_MIN_MAPQ
    ]
    if not valid:
        candidate["outcome"] = "rejected"
        candidate["reason"] = "no_high_stringency_terminal_overlap"
        return
    best = max(
        valid,
        key=lambda row: (
            float(row["score"]),
            int(row["overlap"]),
            float(row["identity"]),
            int(row["mapq"]),
            -int(row["line_number"]),
        ),
    )
    extract_start = int(candidate["extract_record_start"])
    extract_end = int(candidate["extract_record_end"])
    if candidate["terminal"] == "5prime":
        used_oriented_start = extract_start
        used_oriented_end = extract_start + int(best["query_end0"]) - 1
        extension_length = used_oriented_end - used_oriented_start + 1 - int(best["target_end"])
        used_sequence = str(candidate["extract_sequence"])[: int(best["query_end0"])]
    else:
        used_oriented_start = extract_start + int(best["query_end0"])
        used_oriented_end = extract_end
        extension_length = (
            used_oriented_end
            - used_oriented_start
            + 1
            - (chromosome_length - int(best["target_end"]))
        )
        used_sequence = str(candidate["extract_sequence"])[int(best["query_end0"]) :]
    if used_oriented_start > used_oriented_end or extension_length <= 0:
        candidate["outcome"] = "rejected"
        candidate["reason"] = "validated_overlap_does_not_extend_terminal"
        return
    local_start, local_end = oriented_interval_to_record(
        record_length,
        str(candidate["record_alignment_orientation"]),
        used_oriented_start,
        used_oriented_end,
    )
    source_start, source_end = member_source_interval(member, local_start, local_end)
    candidate.update(
        {
            "used_record_start": used_oriented_start,
            "used_record_end": used_oriented_end,
            "used_source_start": source_start,
            "used_source_end": source_end,
            "minimap_identity": float(best["identity"]),
            "minimap_overlap": int(best["overlap"]),
            "minimap_mapq": int(best["mapq"]),
            "minimap_line": int(best["line_number"]),
            "target_start": int(best["target_start"]),
            "target_end": int(best["target_end"]),
            "extension_length": extension_length,
            "used_sequence_sha256": sha256_bytes(used_sequence.encode("ascii")),
            "outcome": "candidate",
            "reason": "passed_mummer_telomere_and_minimap_validation",
        }
    )


def candidate_rank_key(candidate: dict[str, object]) -> tuple[object, ...]:
    return (
        -int(candidate.get("telomere_bp", 0)),
        -int(candidate.get("telomere_repeat_count", 0)),
        -int(candidate.get("minimap_overlap", 0)),
        -float(candidate.get("minimap_identity", 0.0)),
        -int(candidate.get("minimap_mapq", 0)),
        -float(candidate.get("mummer_identity", 0.0)),
        -int(candidate.get("mummer_aligned_length", 0)),
        str(candidate["source_dataset"]),
        str(candidate["source_contig"]),
        int(candidate.get("used_source_start", candidate["extract_source_start"])),
        str(candidate["candidate_id"]),
    )


def arbitrate_candidates(
    chromosome_order: list[str],
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        grouped[(str(candidate["chr"]), str(candidate["terminal"]))].append(candidate)
    accepted_intervals: list[dict[str, object]] = []
    accepted_by_chr: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for chromosome in chromosome_order:
        for terminal in ("5prime", "3prime"):
            rows = sorted(grouped.get((chromosome, terminal), []), key=candidate_rank_key)
            for rank, candidate in enumerate(rows, start=1):
                candidate["rank"] = rank
            accepted: dict[str, object] | None = None
            for candidate in rows:
                if candidate["outcome"] != "candidate":
                    continue
                source_conflict = next(
                    (
                        row
                        for row in accepted_intervals
                        if row["source_dataset"] == candidate["source_dataset"]
                        and row["source_contig"] == candidate["source_contig"]
                        and intervals_overlap(
                            int(row["source_start"]),
                            int(row["source_end"]),
                            int(candidate["used_source_start"]),
                            int(candidate["used_source_end"]),
                        )
                    ),
                    None,
                )
                if source_conflict is not None:
                    candidate["outcome"] = "conflicted"
                    candidate["reason"] = (
                        "source_interval_conflicts_with:"
                        + str(source_conflict["candidate_id"])
                    )
                    continue
                other_terminal = "3prime" if terminal == "5prime" else "5prime"
                other = accepted_by_chr[chromosome].get(other_terminal)
                if other is not None:
                    left_cut = (
                        int(candidate["target_end"])
                        if terminal == "5prime"
                        else int(other["target_end"])
                    )
                    right_cut = (
                        int(other["target_end"])
                        if terminal == "5prime"
                        else int(candidate["target_end"])
                    )
                    if left_cut > right_cut:
                        candidate["outcome"] = "conflicted"
                        candidate["reason"] = f"terminal_edits_overlap:{other['candidate_id']}"
                        continue
                candidate["outcome"] = "accepted"
                candidate["reason"] = "accepted_by_terminal_rank_and_global_interval_arbitration"
                accepted = candidate
                accepted_intervals.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "source_dataset": candidate["source_dataset"],
                        "source_contig": candidate["source_contig"],
                        "source_start": candidate["used_source_start"],
                        "source_end": candidate["used_source_end"],
                    }
                )
                accepted_by_chr[chromosome][terminal] = candidate
                break
            if accepted is not None:
                for candidate in rows:
                    if candidate["outcome"] == "candidate":
                        candidate["outcome"] = "rejected"
                        candidate["reason"] = f"lower_ranked_than:{accepted['candidate_id']}"
            else:
                for candidate in rows:
                    if candidate["outcome"] == "candidate":
                        candidate["outcome"] = "rejected"
                        candidate["reason"] = "no_candidate_survived_arbitration"
    return candidates


def build_candidate_segment(
    candidate: dict[str, object],
    source_card_key: str,
) -> dict[str, object]:
    return {
        "segment_kind": "source",
        "length": int(candidate["used_source_end"]) - int(candidate["used_source_start"]) + 1,
        "dataset_name": candidate["source_dataset"],
        "contig_name": candidate["source_contig"],
        "source_start": int(candidate["used_source_start"]),
        "source_end": int(candidate["used_source_end"]),
        "orientation": candidate["orientation"],
        "source_card_key": source_card_key,
        "evidence_ids": [candidate["mummer_evidence_id"], candidate["minimap_evidence_id"]],
    }


def apply_telomere_candidates(
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    candidates: list[dict[str, object]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
) -> tuple[
    dict[str, list[dict[str, object]]],
    dict[str, str],
    dict[tuple[str, str], dict[str, object]],
]:
    accepted = {
        (str(row["chr"]), str(row["terminal"])): row
        for row in candidates
        if row["outcome"] == "accepted"
    }
    output_paths: dict[str, list[dict[str, object]]] = {}
    output_records: dict[str, str] = {}
    placements: dict[tuple[str, str], dict[str, object]] = {}
    for chromosome in chromosome_order:
        left = accepted.get((chromosome, "5prime"))
        right = accepted.get((chromosome, "3prime"))
        left_cut = int(left["target_end"]) if left is not None else 0
        right_cut = int(right["target_end"]) if right is not None else len(input_records[chromosome])
        if not 0 <= left_cut <= right_cut <= len(input_records[chromosome]):
            fail(f"terminal edits overlap or exceed q3 for {chromosome}")
        path: list[dict[str, object]] = []
        cursor = 0
        if left is not None:
            original_assignment, _placement_mode, source_card_key = source_assignment(
                assignments, left
            )
            left["original_assignment"] = original_assignment
            left["source_card_key"] = source_card_key
            segment = build_candidate_segment(left, source_card_key)
            if sha256_bytes(path_sequence([segment], sources).encode("ascii")) != left[
                "used_sequence_sha256"
            ]:
                fail(f"5prime source projection mismatch: {left['candidate_id']}")
            path.append(segment)
            placements[(chromosome, "5prime")] = {
                "q4_start": 1,
                "q4_end": int(segment["length"]),
                "source_card_key": source_card_key,
                "original_assignment": original_assignment,
            }
            cursor = int(segment["length"])
        path.extend(slice_path(input_paths[chromosome], left_cut, right_cut))
        cursor += right_cut - left_cut
        if right is not None:
            original_assignment, _placement_mode, source_card_key = source_assignment(
                assignments, right
            )
            right["original_assignment"] = original_assignment
            right["source_card_key"] = source_card_key
            segment = build_candidate_segment(right, source_card_key)
            if sha256_bytes(path_sequence([segment], sources).encode("ascii")) != right[
                "used_sequence_sha256"
            ]:
                fail(f"3prime source projection mismatch: {right['candidate_id']}")
            path.append(segment)
            placements[(chromosome, "3prime")] = {
                "q4_start": cursor + 1,
                "q4_end": cursor + int(segment["length"]),
                "source_card_key": source_card_key,
                "original_assignment": original_assignment,
            }
        output_paths[chromosome] = path
        output_records[chromosome] = path_sequence(path, sources)
    return output_paths, output_records, placements


def build_events_usage_attempts(
    run_id: str,
    chromosome_order: list[str],
    input_records: dict[str, str],
    output_records: dict[str, str],
    q3_sha256: str,
    q4_sha256: str,
    terminal_rows: list[dict[str, object]],
    candidates: list[dict[str, object]],
    placements: dict[tuple[str, str], dict[str, object]],
    donor_set_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    by_terminal: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for candidate in candidates:
        by_terminal[(str(candidate["chr"]), str(candidate["terminal"]))].append(candidate)
    terminal_map = {
        (str(row["chr"]), str(row["terminal"])): row for row in terminal_rows
    }
    events: list[dict[str, object]] = []
    usage_rows: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    for chromosome in chromosome_order:
        for terminal in ("5prime", "3prime"):
            terminal_row = terminal_map[(chromosome, terminal)]
            if terminal_row["initial_status"] == "present":
                continue
            related = sorted(
                by_terminal.get((chromosome, terminal), []), key=candidate_rank_key
            )
            accepted = next((row for row in related if row["outcome"] == "accepted"), None)
            object_id = str(terminal_row["object_id"])
            event_id = stable_id("event", [run_id, "step4_telomere", object_id], 24)
            final_path_segment_id = (
                stable_id("grt-segment", [event_id, accepted["candidate_id"]], 24)
                if accepted is not None
                else ""
            )
            usage_ids: list[str] = []
            for candidate in related:
                source_start = int(
                    candidate.get("used_source_start", candidate["extract_source_start"])
                )
                source_end = int(
                    candidate.get("used_source_end", candidate["extract_source_end"])
                )
                candidate_usage_id = stable_id(
                    "usage-candidate", ["step4_telomere", candidate["candidate_id"]], 22
                )
                outcome_usage_id = stable_id(
                    "usage-outcome", ["step4_telomere", candidate["candidate_id"]], 22
                )
                candidate_segment_id = (
                    final_path_segment_id if candidate is accepted else ""
                )
                usage_rows.extend(
                    [
                        {
                            "usage_id": candidate_usage_id,
                            "donor_set_id": donor_set_id,
                            "member_id": candidate["member_id"],
                            "source_dataset": candidate["source_dataset"],
                            "source_contig": candidate["source_contig"],
                            "source_start": source_start,
                            "source_end": source_end,
                            "stage": "step4_telomere",
                            "status": "candidate",
                            "event_id": event_id,
                            "final_path_segment_id": "",
                            "reason": "mummer_terminal_candidate",
                        },
                        {
                            "usage_id": outcome_usage_id,
                            "donor_set_id": donor_set_id,
                            "member_id": candidate["member_id"],
                            "source_dataset": candidate["source_dataset"],
                            "source_contig": candidate["source_contig"],
                            "source_start": source_start,
                            "source_end": source_end,
                            "stage": "step4_telomere",
                            "status": (
                                "consumed"
                                if candidate["outcome"] == "accepted"
                                else candidate["outcome"]
                            ),
                            "event_id": event_id,
                            "final_path_segment_id": candidate_segment_id,
                            "reason": candidate["reason"],
                        },
                    ]
                )
                candidate["event_id"] = event_id
                candidate["final_path_segment_id"] = candidate_segment_id
                candidate["usage_ids"] = [candidate_usage_id, outcome_usage_id]
                usage_ids.extend([candidate_usage_id, outcome_usage_id])
            evidence_ids = sorted(
                {
                    str(evidence_id)
                    for row in related
                    for evidence_id in (
                        row.get("mummer_evidence_id", ""),
                        row.get("minimap_evidence_id", ""),
                    )
                    if evidence_id
                }
            )
            terminal_task_evidence = str(terminal_row.get("task_evidence_id", ""))
            if terminal_task_evidence:
                evidence_ids.append(terminal_task_evidence)
                evidence_ids = sorted(set(evidence_ids))
            if accepted is not None:
                placement = placements[(chromosome, terminal)]
                source = {
                    "dataset": accepted["source_dataset"],
                    "contig": accepted["source_contig"],
                    "start": int(accepted["used_source_start"]),
                    "end": int(accepted["used_source_end"]),
                    "orientation": accepted["orientation"],
                    "original_assignment": placement["original_assignment"],
                }
                q_after_start = int(placement["q4_start"])
                q_after_end = int(placement["q4_end"])
                status = "accepted"
                reason = str(accepted["reason"])
                source_card_key = str(placement["source_card_key"])
                terminal_row["final_status"] = "recovered"
                terminal_row["matched_rule_ids"] = list(accepted["matched_rule_ids"])
                terminal_row["accepted_event_id"] = event_id
                terminal_row["reason"] = reason
                accepted["event_id"] = event_id
                accepted["final_path_segment_id"] = final_path_segment_id
            else:
                source = None
                source_card_key = ""
                status = (
                    "conflicted"
                    if related and all(row["outcome"] == "conflicted" for row in related)
                    else "unresolved"
                )
                reason = (
                    "all_terminal_candidates_conflicted"
                    if status == "conflicted"
                    else "no_valid_terminal_candidate"
                )
                terminal_row["final_status"] = "unresolved"
                terminal_row["reason"] = reason
                if terminal == "5prime":
                    q_after_start = 1
                    q_after_end = min(END_SEARCH_WINDOW, len(output_records[chromosome]))
                else:
                    q_after_start = max(
                        1, len(output_records[chromosome]) - END_SEARCH_WINDOW + 1
                    )
                    q_after_end = len(output_records[chromosome])
            if terminal == "5prime":
                q_before_start = 1
                q_before_end = min(END_SEARCH_WINDOW, len(input_records[chromosome]))
            else:
                q_before_start = max(
                    1, len(input_records[chromosome]) - END_SEARCH_WINDOW + 1
                )
                q_before_end = len(input_records[chromosome])
            event = {
                "run_id": run_id,
                "event_id": event_id,
                "stage": "step4_telomere",
                "chr": chromosome,
                "object_id": object_id,
                "action": "extend_telomere",
                "status": status,
                "reason": reason,
                "q_before": {
                    "version": "q3",
                    "start": q_before_start,
                    "end": q_before_end,
                    "sha256": q3_sha256,
                },
                "q_after": {
                    "version": "q4",
                    "start": q_after_start,
                    "end": q_after_end,
                    "sha256": q4_sha256,
                },
                "source": source,
                "evidence_ids": evidence_ids,
                "usage_ids": usage_ids,
                "source_card_key": source_card_key,
                "final_path_segment_id": final_path_segment_id,
            }
            if accepted is not None:
                event["edit"] = {
                    "operation": "replace_terminal",
                    "terminal": terminal,
                    "alignment_target_start": int(accepted["target_start"]),
                    "alignment_target_end": int(accepted["target_end"]),
                    "q3_cut_after": int(accepted["target_end"]),
                    "replacement_sequence_sha256": accepted["used_sequence_sha256"],
                }
            events.append(event)
            attempts.append(
                {
                    "attempt_id": stable_id(
                        "attempt", [run_id, "step4_telomere", object_id], 22
                    ),
                    "chr": chromosome,
                    "object_id": object_id,
                    "stage": "step4_telomere",
                    "status": status,
                    "reason": reason,
                    "candidate_count": len(related),
                    "accepted_event_id": event_id if accepted is not None else "",
                }
            )
    return events, usage_rows, attempts


def assignment_map(server_dir: Path) -> dict[tuple[str, str], set[str]]:
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in read_tsv(
        server_dir / "metadata/chr_assignments.tsv",
        [
            "dataset_name",
            "seq_name",
            "seq_length_bp",
            "assigned_chr_name",
            "support_bp",
            "support_percent",
            "anchor_start",
        ],
    ):
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    return assignments


def evidence_status(outcome: str) -> str:
    if outcome == "accepted":
        return "accepted"
    if outcome == "conflicted":
        return "conflicted"
    return "rejected"


def common_evidence_row(
    *,
    evidence_id: str,
    evidence_type: str,
    status: str,
    q3_sha256: str,
    query_relpath: str,
    query_sha256: str,
    donor_set_id: str,
    target_relpath: str,
    target_sha256: str,
    source_dataset: str = "",
    source_contig: str = "",
    source_start: object = "",
    source_end: object = "",
    orientation: str = "",
    target_chr: str = "",
    target_start: object = "",
    target_end: object = "",
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
        "stage": "step4_telomere",
        "evidence_type": evidence_type,
        "status": status,
        "q_version": "q3",
        "q_source_sha256": q3_sha256,
        "query_artifact_relpath": query_relpath,
        "query_sha256": query_sha256,
        "donor_set_id": donor_set_id,
        "target_artifact_relpath": target_relpath,
        "target_sha256": target_sha256,
        "source_dataset": source_dataset,
        "source_contig": source_contig,
        "source_start": source_start,
        "source_end": source_end,
        "orientation": orientation,
        "target_chr": target_chr,
        "target_start": target_start,
        "target_end": target_end,
        "tool": tool,
        "tool_version": tool_version,
        "preset": preset,
        "parameters_json": canonical_json(parameters),
        "raw_artifact_relpath": raw_relpath,
        "raw_artifact_sha256": raw_sha256,
        "coordinate_system": coordinate_system,
        "projection_status": "projected",
    }


def checkpoint_result(
    server_dir: Path, stage: str, fingerprint: str
) -> dict[str, object] | None:
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
        result = json.loads(
            (server_dir / str(checkpoint["result_relpath"])).read_text(encoding="utf-8")
        )
        if result.get("stage") != stage or result.get("input_fingerprint") != fingerprint:
            return None
        return result
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def invalidate_step4(server_dir: Path) -> None:
    for stage in ("step4_telomere", "finalize"):
        (server_dir / f"grt/checkpoints/{stage}.json").unlink(missing_ok=True)
    (server_dir / "grt/q/q4.fa").unlink(missing_ok=True)
    (server_dir / "metadata/grt_final_path.json").unlink(missing_ok=True)
    artifact = server_dir / "grt/evidence/step4_telomere"
    if artifact.is_dir():
        shutil.rmtree(artifact)


def run_step4(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    q3_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    rules: list[dict[str, object]],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
    threads: int,
) -> tuple[dict[str, object], bool]:
    q3_sha256 = sha256_file(server_dir / "grt/q/q3.fa")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": "step4_telomere",
        "q_version": "q3",
        "q3_sha256": q3_sha256,
        "q_segments_sha256": json_hash(q3_rows),
        "tel_donor_set_id": donor_set["donor_set_id"],
        "tel_donor_sha256": donor_set["fasta_sha256"],
        "rules": rules,
        "tools": {
            name: command_identity(identity)
            for name, identity in {**tools, "minimap2": minimap}.items()
        },
        "parameters": {
            "end_search_window": END_SEARCH_WINDOW,
            "alignment_query_window": ALIGNMENT_QUERY_WINDOW,
            "max_extract_length": MAX_EXTRACT_LENGTH,
            "candidate_min_alignment": CANDIDATE_MIN_ALIGNMENT,
            "candidate_min_identity": CANDIDATE_MIN_IDENTITY,
            "mummer": mummer_parameters(threads),
            "minimap": {
                "preset": MINIMAP_PRESET,
                "min_identity": MINIMAP_MIN_IDENTITY,
                "min_overlap": MINIMAP_MIN_OVERLAP,
                "min_mapq": MINIMAP_MIN_MAPQ,
            },
        },
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, "step4_telomere", fingerprint)
    if cached is not None:
        print(f"GRT step4_telomere cache hit: {fingerprint}")
        return cached, True
    invalidate_step4(server_dir)
    artifact_relpath = "grt/evidence/step4_telomere"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".step4.", dir=artifact_dir.parent))
    q4_temporary = server_dir / f"grt/q/.q4.fa.tmp.{os.getpid()}"
    members_by_record = {row["fasta_record_name"]: row for row in donor_members}
    donor_records = dict(read_fasta_allow_empty(server_dir / donor_set["fasta_relpath"]))
    donor_lengths = {name: len(sequence) for name, sequence in donor_records.items()}
    terminal_rows: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []
    try:
        for chromosome in chromosome_order:
            for terminal in ("5prime", "3prime"):
                signal = terminal_signal(input_records[chromosome], terminal, rules)
                object_id = stable_id(
                    "missing-telomere",
                    ["q3", chromosome, terminal, q3_sha256],
                    22,
                )
                row: dict[str, object] = {
                    "chr": chromosome,
                    "terminal": terminal,
                    "object_id": object_id,
                    "q3_start": signal["window_start"],
                    "q3_end": signal["window_end"],
                    "initial_status": "present" if signal["present"] else "missing_telomere",
                    "final_status": "already_present" if signal["present"] else "pending",
                    "matched_rule_ids": signal["matched_rule_ids"],
                    "candidate_count": 0,
                    "accepted_event_id": "",
                    "reason": "telomere_signal_already_present" if signal["present"] else "",
                }
                should_align = not bool(signal["present"]) and bool(donor_records)
                cache_dir, cache_hit, identity = cached_terminal_mummer(
                    server_dir,
                    chromosome,
                    terminal,
                    q3_sha256,
                    input_records[chromosome],
                    donor_set,
                    members_by_record,
                    donor_lengths,
                    tools,
                    threads,
                    should_align,
                )
                print(
                    f"GRT Step4 MUMmer {chromosome}:{terminal}: "
                    f"{'cache hit' if cache_hit else 'computed'}"
                )
                destination = temporary / "mummer" / "by_terminal" / str(identity["terminal_key"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(cache_dir, destination)
                query_relpath = (
                    f"{artifact_relpath}/mummer/by_terminal/{identity['terminal_key']}/query.fa"
                )
                coords_relpath = (
                    f"{artifact_relpath}/mummer/by_terminal/{identity['terminal_key']}/result.coords"
                )
                task_evidence_id = stable_id(
                    "ev-step4-task", [chromosome, terminal, fingerprint], 22
                )
                row["task_evidence_id"] = task_evidence_id
                alignments = parse_mummer_coords(
                    destination / "result.coords",
                    "step4_telomere",
                    str(identity["query_name"]),
                    int(identity["query_length"]),
                    members_by_record,
                    donor_lengths,
                )
                terminal_candidates = (
                    extract_terminal_candidates(
                        chromosome,
                        terminal,
                        object_id,
                        alignments,
                        members_by_record,
                        donor_records,
                        rules,
                    )
                    if not signal["present"]
                    else []
                )
                row["candidate_count"] = len(terminal_candidates)
                row["mummer_query_relpath"] = query_relpath
                row["mummer_query_sha256"] = sha256_file(destination / "query.fa")
                row["mummer_coords_relpath"] = coords_relpath
                row["mummer_coords_sha256"] = sha256_file(destination / "result.coords")
                row["query_offset0"] = int(identity["query_offset0"])
                for candidate in terminal_candidates:
                    candidate["mummer_query_relpath"] = query_relpath
                    candidate["mummer_query_sha256"] = row["mummer_query_sha256"]
                    candidate["mummer_coords_relpath"] = coords_relpath
                    candidate["mummer_coords_sha256"] = row["mummer_coords_sha256"]
                    candidate["mummer_target_start"] = int(identity["query_offset0"]) + int(
                        candidate["mummer_query_start"]
                    )
                    candidate["mummer_target_end"] = int(identity["query_offset0"]) + int(
                        candidate["mummer_query_end"]
                    )
                    candidate["mummer_evidence_id"] = stable_id(
                        "ev-step4-mummer", candidate["candidate_id"], 22
                    )
                candidates.extend(terminal_candidates)
                terminal_rows.append(row)

        for candidate in candidates:
            if candidate["outcome"] != "candidate":
                candidate["minimap_evidence_id"] = ""
                continue
            cache_dir, cache_hit, paf_rows, identity = cached_candidate_minimap(
                server_dir,
                candidate,
                input_records[str(candidate["chr"])],
                q3_sha256,
                minimap,
                threads,
            )
            print(
                f"GRT Step4 minimap2 {candidate['candidate_id']}: "
                f"{'cache hit' if cache_hit else 'computed'}"
            )
            destination = temporary / "minimap" / "by_candidate" / str(identity["candidate_key"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_dir, destination)
            candidate["minimap_query_relpath"] = (
                f"{artifact_relpath}/minimap/by_candidate/{identity['candidate_key']}/query.fa"
            )
            candidate["minimap_target_relpath"] = (
                f"{artifact_relpath}/minimap/by_candidate/{identity['candidate_key']}/target.fa"
            )
            candidate["minimap_paf_relpath"] = (
                f"{artifact_relpath}/minimap/by_candidate/{identity['candidate_key']}/result.paf"
            )
            candidate["minimap_query_sha256"] = sha256_file(destination / "query.fa")
            candidate["minimap_target_sha256"] = sha256_file(destination / "target.fa")
            candidate["minimap_paf_sha256"] = sha256_file(destination / "result.paf")
            candidate["minimap_evidence_id"] = stable_id(
                "ev-step4-minimap", candidate["candidate_id"], 22
            )
            member = next(
                row for row in donor_members if row["member_id"] == candidate["member_id"]
            )
            validate_candidate_alignment(
                candidate,
                paf_rows,
                member,
                donor_lengths[str(candidate["ref_record"])],
                len(input_records[str(candidate["chr"])]),
            )

        arbitrate_candidates(chromosome_order, candidates)
        output_paths, output_records, placements = apply_telomere_candidates(
            chromosome_order,
            input_paths,
            input_records,
            candidates,
            assignments,
            sources,
        )
        write_fasta(
            q4_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q4_sha256 = sha256_file(q4_temporary)
        events, usage_rows, attempts = build_events_usage_attempts(
            run_id,
            chromosome_order,
            input_records,
            output_records,
            q3_sha256,
            q4_sha256,
            terminal_rows,
            candidates,
            placements,
            donor_set["donor_set_id"],
        )

        accepted_by_terminal = {
            (str(row["chr"]), str(row["terminal"])): row
            for row in candidates
            if row["outcome"] == "accepted"
        }
        for row in terminal_rows:
            if row["initial_status"] == "present":
                status = "background"
            elif (str(row["chr"]), str(row["terminal"])) in accepted_by_terminal:
                status = "accepted"
            else:
                status = "rejected"
            evidence_rows.append(
                common_evidence_row(
                    evidence_id=str(row["task_evidence_id"]),
                    evidence_type="mummer_terminal_search",
                    status=status,
                    q3_sha256=q3_sha256,
                    query_relpath=str(row["mummer_query_relpath"]),
                    query_sha256=str(row["mummer_query_sha256"]),
                    donor_set_id=donor_set["donor_set_id"],
                    target_relpath=donor_set["fasta_relpath"],
                    target_sha256=donor_set["fasta_sha256"],
                    target_chr=str(row["chr"]),
                    target_start=row["q3_start"],
                    target_end=row["q3_end"],
                    tool="nucmer/delta-filter/show-coords",
                    tool_version=" | ".join(
                        tools[name]["version"]
                        for name in ("nucmer", "delta-filter", "show-coords")
                    ),
                    preset="nucmer-c1000-l100;delta-filter-r-l10000;show-coords-r-l",
                    parameters={
                        **mummer_parameters(threads),
                        "terminal": row["terminal"],
                        "query_offset0": row["query_offset0"],
                    },
                    raw_relpath=str(row["mummer_coords_relpath"]),
                    raw_sha256=str(row["mummer_coords_sha256"]),
                    coordinate_system="mummer_1_based_closed",
                )
            )
        for candidate in candidates:
            evidence_rows.append(
                common_evidence_row(
                    evidence_id=str(candidate["mummer_evidence_id"]),
                    evidence_type="mummer_telomere_anchor",
                    status=evidence_status(str(candidate["outcome"])),
                    q3_sha256=q3_sha256,
                    query_relpath=str(candidate["mummer_query_relpath"]),
                    query_sha256=str(candidate["mummer_query_sha256"]),
                    donor_set_id=donor_set["donor_set_id"],
                    target_relpath=donor_set["fasta_relpath"],
                    target_sha256=donor_set["fasta_sha256"],
                    source_dataset=str(candidate["source_dataset"]),
                    source_contig=str(candidate["source_contig"]),
                    source_start=candidate["extract_source_start"],
                    source_end=candidate["extract_source_end"],
                    orientation=str(candidate["orientation"]),
                    target_chr=str(candidate["chr"]),
                    target_start=candidate["mummer_target_start"],
                    target_end=candidate["mummer_target_end"],
                    tool="nucmer/delta-filter/show-coords",
                    tool_version=" | ".join(
                        tools[name]["version"]
                        for name in ("nucmer", "delta-filter", "show-coords")
                    ),
                    preset="nucmer-c1000-l100;delta-filter-r-l10000;show-coords-r-l",
                    parameters={
                        **mummer_parameters(threads),
                        "candidate_min_identity": CANDIDATE_MIN_IDENTITY,
                        "candidate_min_alignment": CANDIDATE_MIN_ALIGNMENT,
                        "mummer_line": candidate["mummer_line"],
                    },
                    raw_relpath=str(candidate["mummer_coords_relpath"]),
                    raw_sha256=str(candidate["mummer_coords_sha256"]),
                    coordinate_system="mummer_1_based_closed",
                )
            )
            if not candidate.get("minimap_evidence_id"):
                continue
            evidence_rows.append(
                common_evidence_row(
                    evidence_id=str(candidate["minimap_evidence_id"]),
                    evidence_type="minimap2_terminal_overlap_validation",
                    status=evidence_status(str(candidate["outcome"])),
                    q3_sha256=q3_sha256,
                    query_relpath=str(candidate["minimap_query_relpath"]),
                    query_sha256=str(candidate["minimap_query_sha256"]),
                    donor_set_id="",
                    target_relpath=str(candidate["minimap_target_relpath"]),
                    target_sha256=str(candidate["minimap_target_sha256"]),
                    source_dataset=str(candidate["source_dataset"]),
                    source_contig=str(candidate["source_contig"]),
                    source_start=candidate.get(
                        "used_source_start", candidate["extract_source_start"]
                    ),
                    source_end=candidate.get(
                        "used_source_end", candidate["extract_source_end"]
                    ),
                    orientation=str(candidate["orientation"]),
                    target_chr=str(candidate["chr"]),
                    target_start=candidate.get("target_start", candidate["mummer_target_start"]),
                    target_end=candidate.get("target_end", candidate["mummer_target_end"]),
                    tool="minimap2",
                    tool_version=minimap["version"],
                    preset=MINIMAP_PRESET,
                    parameters={
                        "secondary": False,
                        "cigar": True,
                        "min_identity": MINIMAP_MIN_IDENTITY,
                        "min_overlap": MINIMAP_MIN_OVERLAP,
                        "min_mapq": MINIMAP_MIN_MAPQ,
                    },
                    raw_relpath=str(candidate["minimap_paf_relpath"]),
                    raw_sha256=str(candidate["minimap_paf_sha256"]),
                    coordinate_system="paf_0_based_half_open",
                )
            )

        for chromosome in chromosome_order:
            for terminal in ("5prime", "3prime"):
                before = terminal_signal(input_records[chromosome], terminal, rules)
                after = terminal_signal(output_records[chromosome], terminal, rules)
                accepted = accepted_by_terminal.get((chromosome, terminal))
                if accepted is not None and (before["present"] or not after["present"]):
                    fail(f"accepted telomere candidate did not restore {chromosome}:{terminal}")
                if accepted is None and before["present"] != after["present"]:
                    fail(f"unmodified terminal status drifted for {chromosome}:{terminal}")

        q_rows = q_rows_for_paths("q4", chromosome_order, output_paths)
        for candidate in candidates:
            candidate.pop("extract_sequence", None)
        write_tsv(
            temporary / "terminal_status.tsv",
            TERMINAL_FIELDS,
            [
                {
                    **{field: row.get(field, "") for field in TERMINAL_FIELDS},
                    "matched_rule_ids_json": canonical_json(row["matched_rule_ids"]),
                }
                for row in terminal_rows
            ],
        )
        write_tsv(
            temporary / "candidates.tsv",
            CANDIDATE_FIELDS,
            [
                {
                    **{field: row.get(field, "") for field in CANDIDATE_FIELDS},
                    "mummer_identity": (
                        f"{float(row['mummer_identity']):.9f}" if row.get("mummer_identity") is not None else ""
                    ),
                    "minimap_identity": (
                        f"{float(row['minimap_identity']):.9f}" if row.get("minimap_identity") is not None else ""
                    ),
                    "matched_rule_ids_json": canonical_json(row["matched_rule_ids"]),
                }
                for row in sorted(
                    candidates,
                    key=lambda value: (
                        chromosome_order.index(str(value["chr"])),
                        0 if value["terminal"] == "5prime" else 1,
                        int(value.get("rank", 999999)),
                        str(value["candidate_id"]),
                    ),
                )
            ],
        )
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_jsonl(temporary / "events.jsonl", events)
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": "step4_telomere",
            "input_fingerprint": fingerprint,
            "q_input_version": "q3",
            "q_input_sha256": q3_sha256,
            "q_output_version": "q4",
            "q_output_sha256": q4_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "target_sha256": donor_set["fasta_sha256"],
            "q_rows": q_rows,
            "evidence_rows": evidence_rows,
            "usage_rows": usage_rows,
            "events": events,
            "attempts": attempts,
            "terminal_rows": terminal_rows,
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q4_temporary, server_dir / "grt/q/q4.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix()
            for path in artifact_dir.rglob("*")
            if path.is_file()
        ] + ["grt/q/q4.fa"]
        write_checkpoint(
            server_dir,
            "step4_telomere",
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            "GRT step4_telomere complete: "
            f"recovered={sum(row['outcome'] == 'accepted' for row in candidates)}, "
            f"unresolved={sum(row['final_status'] == 'unresolved' for row in terminal_rows)}"
        )
        return result, False
    except BaseException:
        q4_temporary.unlink(missing_ok=True)
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"step4-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def event_is_path_producing(event: dict[str, object]) -> bool:
    return bool(event.get("final_path_segment_id")) and event.get("action") in {
        "fill",
        "patch",
        "refill",
        "extend_telomere",
    }


def segment_matches_event(
    segment: dict[str, object], event: dict[str, object]
) -> bool:
    source = event.get("source")
    if not isinstance(source, dict) or segment["segment_kind"] != "source":
        return False
    if not set(segment["evidence_ids"]).intersection(event.get("evidence_ids", [])):
        return False
    return (
        segment["dataset_name"] == source["dataset"]
        and segment["contig_name"] == source["contig"]
        and int(segment["source_start"]) == int(source["start"])
        and int(segment["source_end"]) == int(source["end"])
        and segment["orientation"] == source["orientation"]
        and segment["source_card_key"] == event["source_card_key"]
    )


def build_final_path(
    chromosome_order: list[str],
    q4_paths: dict[str, list[dict[str, object]]],
    q4_records: dict[str, str],
    events: list[dict[str, object]],
) -> dict[str, object]:
    path_events = [
        event
        for event in events
        if event.get("status") == "accepted" and event_is_path_producing(event)
    ]
    event_by_segment_id: dict[str, dict[str, object]] = {}
    for event in path_events:
        segment_id = str(event["final_path_segment_id"])
        if segment_id in event_by_segment_id:
            fail(f"duplicate event Final Path segment ID: {segment_id}")
        event_by_segment_id[segment_id] = event
    matched_event_ids: set[str] = set()
    chromosomes: list[dict[str, object]] = []
    used_segment_ids: set[str] = set()
    for chromosome in chromosome_order:
        final_segments: list[dict[str, object]] = []
        for index, segment in enumerate(q4_paths[chromosome], start=1):
            if segment["segment_kind"] == "gap":
                segment_id = stable_id(
                    "final-gap",
                    [chromosome, index, segment["length"], segment["evidence_ids"]],
                    24,
                )
                final_segment = {
                    "segment_id": segment_id,
                    "kind": "gap",
                    "length": int(segment["length"]),
                    "orientation": None,
                    "event_id": None,
                    "source": None,
                    "evidence_ids": [],
                }
            else:
                matches = [
                    event
                    for event in path_events
                    if event["chr"] == chromosome and segment_matches_event(segment, event)
                ]
                if len(matches) > 1:
                    fail(
                        "one q4 source segment matches multiple accepted GRT events: "
                        f"{chromosome}:{segment['dataset_name']}:{segment['contig_name']}"
                    )
                event = matches[0] if matches else None
                if event is not None:
                    segment_id = str(event["final_path_segment_id"])
                    kind = "telomere" if event["action"] == "extend_telomere" else "patch"
                    event_id: str | None = str(event["event_id"])
                    matched_event_ids.add(event_id)
                else:
                    if str(segment["source_card_key"]).endswith(
                        (":grt_promoted", ":cross_chr_grt_usage")
                    ):
                        fail(
                            "GRT-derived q4 source segment lacks one exact accepted event: "
                            f"{chromosome}:{segment['dataset_name']}:{segment['contig_name']}"
                        )
                    segment_id = stable_id(
                        "final-source",
                        {
                            "chr": chromosome,
                            "index": index,
                            "dataset": segment["dataset_name"],
                            "contig": segment["contig_name"],
                            "start": segment["source_start"],
                            "end": segment["source_end"],
                            "orientation": segment["orientation"],
                            "evidence": segment["evidence_ids"],
                        },
                        24,
                    )
                    kind = "source"
                    event_id = None
                final_segment = {
                    "segment_id": segment_id,
                    "kind": kind,
                    "length": int(segment["length"]),
                    "orientation": segment["orientation"],
                    "event_id": event_id,
                    "source": {
                        "dataset": segment["dataset_name"],
                        "contig": segment["contig_name"],
                        "start": int(segment["source_start"]),
                        "end": int(segment["source_end"]),
                        "orientation": segment["orientation"],
                    },
                    "evidence_ids": list(segment["evidence_ids"]),
                }
            if segment_id in used_segment_ids:
                fail(f"duplicate generated Final Path segment ID: {segment_id}")
            used_segment_ids.add(segment_id)
            final_segments.append(final_segment)
        chromosomes.append(
            {
                "chr": chromosome,
                "q4_length": len(q4_records[chromosome]),
                "q4_sha256": sha256_bytes(q4_records[chromosome].encode("ascii")),
                "segments": final_segments,
            }
        )
    expected_event_ids = {str(event["event_id"]) for event in path_events}
    if matched_event_ids != expected_event_ids:
        missing = sorted(expected_event_ids - matched_event_ids)
        fail(f"accepted path-producing events are absent from q4: {missing}")
    return {
        "workflow": WORKFLOW,
        "schema_version": "1",
        "q4_relpath": "grt/q/q4.fa",
        "chromosomes": chromosomes,
    }


def verify_final_path(
    final_path: dict[str, object],
    q4_records: dict[str, str],
    sources: dict[tuple[str, str], str],
) -> None:
    chromosomes = final_path.get("chromosomes")
    if not isinstance(chromosomes, list) or not chromosomes:
        fail("Final Path has no chromosomes")
    seen: set[str] = set()
    for chromosome in chromosomes:
        if not isinstance(chromosome, dict):
            fail("Final Path chromosome is not an object")
        name = str(chromosome.get("chr", ""))
        if name not in q4_records or name in seen:
            fail(f"Final Path has an invalid or duplicate chromosome: {name}")
        seen.add(name)
        rebuilt: list[str] = []
        segments = chromosome.get("segments")
        if not isinstance(segments, list) or not segments:
            fail(f"Final Path chromosome has no segments: {name}")
        for segment in segments:
            if segment["kind"] == "gap":
                rebuilt.append("N" * int(segment["length"]))
                continue
            source = segment.get("source")
            if not isinstance(source, dict):
                fail(f"Final Path source segment lacks source identity: {segment['segment_id']}")
            key = (str(source["dataset"]), str(source["contig"]))
            if key not in sources:
                fail(f"Final Path source is absent from immutable catalog: {key[0]}:{key[1]}")
            start = int(source["start"])
            end = int(source["end"])
            sequence = sources[key][start - 1 : end]
            if source["orientation"] == "-":
                sequence = reverse_complement(sequence)
            if len(sequence) != int(segment["length"]):
                fail(f"Final Path segment length mismatch: {segment['segment_id']}")
            rebuilt.append(sequence)
        rebuilt_sequence = "".join(rebuilt)
        expected_sequence = q4_records[name]
        expected_sha = sha256_bytes(expected_sequence.encode("ascii"))
        if (
            rebuilt_sequence != expected_sequence
            or int(chromosome.get("q4_length", -1)) != len(expected_sequence)
            or chromosome.get("q4_sha256") != expected_sha
        ):
            fail(f"Final Path does not exactly reconstruct q4 chromosome {name}")
    if seen != set(q4_records):
        fail("Final Path chromosome set differs from q4")


def atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    os.replace(temporary, path)


def reconcile_terminal_supersession(
    server_dir: Path,
    q3_rows: list[dict[str, object]],
    q4_paths: dict[str, list[dict[str, object]]],
    events: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
    usage_rows: list[dict[str, object]],
) -> None:
    tel_events = {
        str(event["event_id"]): event
        for event in events
        if event["stage"] == "step4_telomere" and event["status"] == "accepted"
    }
    for event in events:
        replacing_id = event.get("superseded_by_event_id")
        if event.get("status") == "superseded" and replacing_id in tel_events:
            tel_events[str(replacing_id)].setdefault("superseded_event_ids", []).append(
                event["event_id"]
            )
    q3_records = dict(read_fasta(server_dir / "grt/q/q3.fa"))
    for event in events:
        if event.get("status") != "accepted" or not event_is_path_producing(event):
            continue
        if event.get("stage") == "step4_telomere":
            continue
        surviving = any(
            segment_matches_event(segment, event)
            for segment in q4_paths[str(event["chr"])]
        )
        if surviving:
            continue
        source = event.get("source")
        matching_q3_rows = [
            row
            for row in q3_rows
            if row["chr"] == event["chr"]
            and row["segment_kind"] == "source"
            and row["dataset_name"] == source["dataset"]
            and row["contig_name"] == source["contig"]
            and int(row["source_start"]) == int(source["start"])
            and int(row["source_end"]) == int(source["end"])
            and row["orientation"] == source["orientation"]
            and set(json.loads(str(row["evidence_ids_json"]))).intersection(
                event["evidence_ids"]
            )
        ]
        if len(matching_q3_rows) != 1:
            fail(
                "accepted event disappeared before q4 without one exact q3 segment: "
                + str(event["event_id"])
            )
        q3_row = matching_q3_rows[0]
        row_start = int(q3_row["q_start"])
        row_end = int(q3_row["q_end"])
        replacing: list[dict[str, object]] = []
        partial: list[str] = []
        for tel_event in tel_events.values():
            if tel_event["chr"] != event["chr"]:
                continue
            edit = tel_event["edit"]
            cut = int(edit["q3_cut_after"])
            if edit["terminal"] == "5prime":
                removed_start, removed_end = 1, cut
            else:
                removed_start, removed_end = cut + 1, len(q3_records[str(event["chr"])])
            if removed_start > removed_end:
                continue
            if removed_start <= row_start and row_end <= removed_end:
                replacing.append(tel_event)
            elif intervals_overlap(removed_start, removed_end, row_start, row_end):
                partial.append(str(tel_event["event_id"]))
        if partial:
            fail(
                f"telomere recovery partially removes accepted event {event['event_id']}: {partial}"
            )
        if len(replacing) != 1:
            fail(
                "accepted event absent from q4 is not fully superseded by one terminal event: "
                + str(event["event_id"])
            )
        replacement = replacing[0]
        event["status"] = "superseded"
        event["reason"] = f"superseded_by_terminal_extension:{replacement['event_id']}"
        event["superseded_by_event_id"] = replacement["event_id"]
        event["final_path_segment_id"] = ""
        replacement.setdefault("superseded_event_ids", []).append(event["event_id"])
        for row in evidence_rows:
            if row["evidence_id"] in event["evidence_ids"] and row["status"] == "accepted":
                row["status"] = "superseded"
        for row in usage_rows:
            if row["event_id"] == event["event_id"] and row["status"] in {
                "accepted",
                "consumed",
            }:
                row["status"] = "superseded"
                row["final_path_segment_id"] = ""
                row["reason"] = "superseded_by_terminal_extension"
    for tel_event in tel_events.values():
        if "superseded_event_ids" in tel_event:
            tel_event["superseded_event_ids"] = sorted(
                set(tel_event["superseded_event_ids"])
            )


def write_finalize_checkpoint(
    server_dir: Path,
    q4_sha256: str,
    final_path_sha256: str,
    events: list[dict[str, object]],
    q_rows: list[dict[str, object]],
) -> Path:
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": "finalize",
        "q4_sha256": q4_sha256,
        "final_path_sha256": final_path_sha256,
        "events_sha256": json_hash(events),
        "q4_segments_sha256": json_hash(q_rows),
    }
    checkpoint = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": "finalize",
        "status": "success",
        "input_fingerprint": json_hash(fingerprint_payload),
        "fingerprint_payload": fingerprint_payload,
        "output_hashes": {
            "grt/q/q4.fa": q4_sha256,
            "metadata/grt_final_path.json": final_path_sha256,
        },
    }
    path = server_dir / "grt/checkpoints/finalize.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, checkpoint)
    return path


def publish_metadata_and_finalize(
    server_dir: Path,
    result: dict[str, object],
    sources: dict[tuple[str, str], str],
    tools: dict[str, dict[str, str]],
    minimap: dict[str, str],
) -> dict[str, object]:
    metadata = server_dir / "metadata"
    q_rows: list[dict[str, object]] = [
        row
        for row in read_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS)
        if row["q_version"] != "q4"
    ]
    q_rows.extend(result["q_rows"])
    evidence_rows: list[dict[str, object]] = [
        row
        for row in read_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS)
        if row["stage"] != "step4_telomere"
    ]
    evidence_rows.extend(result["evidence_rows"])
    usage_rows: list[dict[str, object]] = [
        row
        for row in read_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS)
        if row["stage"] != "step4_telomere"
    ]
    usage_rows.extend(result["usage_rows"])
    events: list[dict[str, object]] = [
        json.loads(line)
        for line in (metadata / "grt_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events = [row for row in events if row["stage"] != "step4_telomere"]
    events.extend(result["events"])
    attempts: list[dict[str, object]] = [
        row
        for row in read_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS)
        if row["stage"] != "step4_telomere"
    ]
    attempts.extend(result["attempts"])
    stage_rows: list[dict[str, object]] = [
        row
        for row in read_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS)
        if row["stage"] not in {"step4_telomere", "finalize"}
    ]
    tool_rows = [
        row
        for row in read_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS)
        if row["tool"]
        not in {
            "grt_telomere_finalize",
            "step4_nucmer",
            "step4_delta_filter",
            "step4_show_coords",
            "step4_minimap2",
        }
    ]
    tool_rows.extend(
        [
            {
                "tool": "grt_telomere_finalize",
                "version": str(ENGINE_VERSION),
                "executable": ".prepare_lib/tools/grt_telomere_finalize.py",
            },
            {
                "tool": "step4_nucmer",
                "version": tools["nucmer"]["version"],
                "executable": tools["nucmer"]["resolved"],
            },
            {
                "tool": "step4_delta_filter",
                "version": tools["delta-filter"]["version"],
                "executable": tools["delta-filter"]["resolved"],
            },
            {
                "tool": "step4_show_coords",
                "version": tools["show-coords"]["version"],
                "executable": tools["show-coords"]["resolved"],
            },
            {
                "tool": "step4_minimap2",
                "version": minimap["version"],
                "executable": minimap["resolved"],
            },
        ]
    )
    q4_rows = [row for row in q_rows if row["q_version"] == "q4"]
    chromosome_order, q4_paths, q4_record_list = load_q_paths(
        server_dir, "q4", q4_rows, sources
    )
    q4_records = q4_record_list
    q3_rows = [row for row in q_rows if row["q_version"] == "q3"]
    reconcile_terminal_supersession(
        server_dir,
        q3_rows,
        q4_paths,
        events,
        evidence_rows,
        usage_rows,
    )
    final_path = build_final_path(chromosome_order, q4_paths, q4_records, events)
    verify_final_path(final_path, q4_records, sources)

    atomic_write_tsv(metadata / "grt_q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_donor_usage.tsv", USAGE_FIELDS, usage_rows)
    atomic_write_jsonl(metadata / "grt_events.jsonl", events)
    atomic_write_tsv(metadata / "grt_gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)
    atomic_write_json(metadata / "grt_final_path.json", final_path)
    verify_final_path(
        json.loads((metadata / "grt_final_path.json").read_text(encoding="utf-8")),
        dict(read_fasta(server_dir / "grt/q/q4.fa")),
        sources,
    )
    q4_sha256 = sha256_file(server_dir / "grt/q/q4.fa")
    finalize_checkpoint = write_finalize_checkpoint(
        server_dir,
        q4_sha256,
        sha256_file(metadata / "grt_final_path.json"),
        events,
        q4_rows,
    )
    stage_rows.append(stage_status_row(server_dir, result))
    stage_rows.append(
        {
            "stage": "finalize",
            "q_input_version": "q4",
            "q_input_sha256": q4_sha256,
            "q_output_version": "q4",
            "q_output_sha256": q4_sha256,
            "donor_set_id": "",
            "status": "success",
            "checkpoint_relpath": "grt/checkpoints/finalize.json",
            "checkpoint_sha256": sha256_file(finalize_checkpoint),
        }
    )
    atomic_write_tsv(metadata / "grt_stage_status.tsv", STAGE_FIELDS, stage_rows)
    return final_path


def execute(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != "1"
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; Step4 has no legacy fallback")
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
    donor_set, donor_members, _donor_freeze = verify_telomere_donor_freeze(
        server_dir, recipe
    )
    sources = source_catalog(server_dir)
    assignments = assignment_map(server_dir)
    q_rows = read_tsv(server_dir / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS)
    q3_rows = [row for row in q_rows if row["q_version"] == "q3"]
    if not q3_rows or not (server_dir / "grt/q/q3.fa").is_file():
        fail("Step4 requires a completed q3/Step2-3 mapping")
    chromosome_order, q3_paths, q3_records = load_q_paths(
        server_dir, "q3", q3_rows, sources
    )
    rules = load_telomere_rules(server_dir)
    tools = {
        "nucmer": executable_identity(args.nucmer),
        "delta-filter": executable_identity(args.delta_filter),
        "show-coords": executable_identity(args.show_coords),
    }
    minimap = executable_identity(args.minimap2)
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "tel_donor_set_id": donor_set["donor_set_id"],
            "q3_sha256": sha256_file(server_dir / "grt/q/q3.fa"),
            "engine_version": ENGINE_VERSION,
            "tools": {
                name: command_identity(identity)
                for name, identity in {**tools, "minimap2": minimap}.items()
            },
        },
        24,
    )
    result, _cached = run_step4(
        server_dir,
        run_id,
        chromosome_order,
        q3_paths,
        q3_records,
        q3_rows,
        donor_set,
        donor_members,
        assignments,
        sources,
        rules,
        tools,
        minimap,
        args.threads,
    )
    final_path = publish_metadata_and_finalize(
        server_dir, result, sources, tools, minimap
    )
    print(
        f"GRT q4 finalized: run={run_id}, Dtel={donor_set['donor_set_id']}, "
        f"chromosomes={len(final_path['chromosomes'])}, "
        f"q4_sha256={sha256_file(server_dir / 'grt/q/q4.fa')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--nucmer", default="nucmer")
    parser.add_argument("--delta-filter", dest="delta_filter", default="delta-filter")
    parser.add_argument("--show-coords", dest="show_coords", default="show-coords")
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=10)
    args = parser.parse_args()
    if args.threads < 1:
        fail("threads must be a positive integer")
    execute(args)


if __name__ == "__main__":
    main()
