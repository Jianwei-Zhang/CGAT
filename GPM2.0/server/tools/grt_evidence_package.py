#!/usr/bin/env python3

"""Publish GRT-used source cards, display PAF evidence, and package integrity."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from grt_contract import ContractError, validate_contract
from grt_prepare_inputs import (
    CHR_ASSIGNMENT_FIELDS,
    EVIDENCE_FIELDS,
    WORKFLOW,
    canonical_json,
    executable_identity,
    read_fasta,
    read_tsv,
    sha256_file,
    stable_id,
    write_fasta,
)
from grt_step1 import (
    TOOL_FIELDS,
    atomic_write_tsv,
    read_single,
    source_assignment,
    source_catalog,
)


ENGINE_VERSION = 1
DISPLAY_PRESET = "asm5"
USED_CONTIG_FIELDS = [
    "source_card_key",
    "dataset_name",
    "contig_name",
    "original_assignment",
    "target_chr",
    "placement_mode",
    "ref_alignment_status",
    "anchor_start",
    "orientation",
    "ref_evidence_ids_json",
    "accepted_event_ids_json",
    "final_path_segment_ids_json",
    "pairwise_evidence_ids_json",
]
DATASET_FIELDS = [
    "dataset_name",
    "assembler",
    "assembler_version",
    "fasta_relpath",
    "fai_relpath",
    "self_alignment_available",
]


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="",
    )
    os.replace(temporary, path)


def json_list(values: list[str]) -> str:
    return json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":"))


def relative(server_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(server_dir.resolve()).as_posix()


def read_events(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        fail(f"required event registry is missing: {path}")
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"invalid event JSON at {path}:{line_number}: {exc}")
            if not isinstance(row, dict):
                fail(f"event at {path}:{line_number} is not an object")
            rows.append(row)
    return rows


def path_producing(event: dict[str, object]) -> bool:
    return event.get("action") in {"fill", "patch", "refill", "extend_telomere"} or (
        event.get("action") == "replace"
        and isinstance(event.get("edit"), dict)
        and event["edit"].get("replacement_kind") == "source"
    )


def final_segment_anchors(final_path: dict[str, object]) -> dict[str, tuple[str, int]]:
    anchors: dict[str, tuple[str, int]] = {}
    chromosomes = final_path.get("chromosomes")
    if not isinstance(chromosomes, list):
        fail("grt_final_path.json lacks chromosomes")
    for chromosome in chromosomes:
        if not isinstance(chromosome, dict) or not isinstance(chromosome.get("segments"), list):
            fail("grt_final_path.json has an invalid chromosome")
        cursor = 1
        for segment in chromosome["segments"]:
            if not isinstance(segment, dict):
                fail("grt_final_path.json has an invalid segment")
            segment_id = str(segment.get("segment_id", ""))
            length = int(segment.get("length", 0))
            if not segment_id or length < 1 or segment_id in anchors:
                fail(f"invalid or duplicate Final Path segment: {segment_id}")
            anchors[segment_id] = (str(chromosome.get("chr", "")), cursor)
            cursor += length
    return anchors


def accepted_source_cards(
    events: list[dict[str, object]],
    assignments: dict[tuple[str, str], set[str]],
    segment_anchors: dict[str, tuple[str, int]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in events:
        if event.get("status") != "accepted" or event.get("source") is None or not path_producing(event):
            continue
        source = event["source"]
        if not isinstance(source, dict):
            fail(f"accepted event {event.get('event_id')} has invalid source")
        candidate = {
            "source_dataset": source.get("dataset"),
            "source_contig": source.get("contig"),
            "chr": event.get("chr"),
        }
        original_assignment, placement_mode, expected_key = source_assignment(assignments, candidate)
        if source.get("original_assignment") != original_assignment:
            fail(f"accepted event {event.get('event_id')} has stale original_assignment")
        if event.get("source_card_key") != expected_key:
            fail(f"accepted event {event.get('event_id')} has a non-canonical source_card_key")
        segment_id = str(event.get("final_path_segment_id", ""))
        if segment_id not in segment_anchors or segment_anchors[segment_id][0] != event.get("chr"):
            fail(f"accepted event {event.get('event_id')} lacks its Final Path segment")
        event["_placement_mode"] = placement_mode
        event["_path_anchor"] = segment_anchors[segment_id][1]
        grouped[expected_key].append(event)

    cards: list[dict[str, object]] = []
    for card_key in sorted(grouped):
        card_events = sorted(grouped[card_key], key=lambda row: str(row["event_id"]))
        prototype = card_events[0]
        source = prototype["source"]
        identities = {
            (
                str(event["source"]["dataset"]),
                str(event["source"]["contig"]),
                str(event["source"]["orientation"]),
                str(event["chr"]),
                str(event["_placement_mode"]),
            )
            for event in card_events
        }
        if len(identities) != 1:
            fail(f"source card {card_key} has incompatible accepted placements")
        cards.append(
            {
                "source_card_key": card_key,
                "dataset_name": str(source["dataset"]),
                "contig_name": str(source["contig"]),
                "original_assignment": str(source["original_assignment"]),
                "target_chr": str(prototype["chr"]),
                "placement_mode": str(prototype["_placement_mode"]),
                "orientation": str(source["orientation"]),
                "event_ids": [str(event["event_id"]) for event in card_events],
                "segment_ids": [str(event["final_path_segment_id"]) for event in card_events],
                "grt_anchor": min(int(event["_path_anchor"]) for event in card_events),
            }
        )
    return cards


def parse_source_paf(path: Path, contig: str, source_length: int) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    if not path.is_file():
        fail(f"source-vs-reference PAF is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 12:
                fail(f"invalid PAF row at {path}:{line_number}")
            if fields[0] != contig:
                continue
            try:
                qlen, qstart, qend = map(int, fields[1:4])
                tlen, tstart, tend = map(int, fields[6:9])
                matches, block_length, mapq = map(int, fields[9:12])
            except ValueError:
                fail(f"non-integer PAF fields at {path}:{line_number}")
            strand = fields[4]
            if (
                qlen != source_length
                or strand not in {"+", "-"}
                or not (0 <= qstart < qend <= qlen)
                or not (0 <= tstart < tend <= tlen)
                or block_length < 1
            ):
                fail(f"inconsistent source PAF row at {path}:{line_number}")
            anchor = (
                tstart + 1 - (qstart + 1) + 1
                if strand == "+"
                else tstart + 1 - source_length + qend
            )
            hits.append(
                {
                    "target": fields[5],
                    "target_start": tstart + 1,
                    "target_end": tend,
                    "matches": matches,
                    "block_length": block_length,
                    "mapq": mapq,
                    "strand": strand,
                    "anchor": max(1, anchor),
                    "line_number": line_number,
                }
            )
    return hits


def alignment_profile(server_dir: Path, dataset_name: str) -> tuple[str, str, str]:
    options = {
        row["key"]: row["value"]
        for row in read_tsv(server_dir / "metadata/prepare_options.tsv", ["key", "value"])
    }
    tool = options.get("alignment_engine", "unknown")
    preset_key = {
        "minimap2": "minimap_preset",
        "blastn": "blastn_task",
        "winnowmap": "winnowmap_preset",
    }.get(tool, "")
    version_path = server_dir / f"runs/{dataset_name}_vs_ref/tool_version.txt"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else "unknown"
    return tool, version[:200], options.get(preset_key, "")


def build_ref_evidence(
    server_dir: Path,
    card: dict[str, object],
    source_sequence: str,
    dataset_row: dict[str, str],
    reference_row: dict[str, str],
) -> tuple[dict[str, object], str, int]:
    dataset = str(card["dataset_name"])
    contig = str(card["contig_name"])
    target_chr = str(card["target_chr"])
    paf_path = server_dir / f"runs/{dataset}_vs_ref/result.paf"
    hits = parse_source_paf(paf_path, contig, len(source_sequence))
    target_hits = [hit for hit in hits if hit["target"] == target_chr]
    hit_chromosomes = sorted({str(hit["target"]) for hit in hits})
    if target_hits:
        status = "multi_hit" if len(hits) > 1 else (
            "hit" if card["original_assignment"] == "assigned" else "weak_hit"
        )
        best = sorted(
            target_hits,
            key=lambda hit: (
                -int(hit["block_length"]),
                -int(hit["matches"]),
                -int(hit["mapq"]),
                int(hit["target_start"]),
                int(hit["line_number"]),
            ),
        )[0]
        anchor = int(best["anchor"])
        evidence_target_chr = target_chr
        target_start = int(best["target_start"])
        target_end = int(best["target_end"])
        anchor_source = "reference_paf"
    elif hits:
        status = "other_chr_only"
        best = sorted(
            hits,
            key=lambda hit: (-int(hit["block_length"]), -int(hit["matches"]), str(hit["target"])),
        )[0]
        anchor = int(card["grt_anchor"])
        evidence_target_chr = str(best["target"])
        target_start = int(best["target_start"])
        target_end = int(best["target_end"])
        anchor_source = "grt_final_path"
    else:
        status = "no_hit"
        best = None
        anchor = int(card["grt_anchor"])
        evidence_target_chr = ""
        target_start = ""
        target_end = ""
        anchor_source = "grt_final_path"

    dataset_path = server_dir / dataset_row["fasta_relpath"]
    reference_path = server_dir / reference_row["fasta_relpath"]
    tool, version, preset = alignment_profile(server_dir, dataset)
    parameters = {
        "anchor_source": anchor_source,
        "hit_chromosomes": hit_chromosomes,
        "role": "source_ref_profile",
        "source_hit_count": len(hits),
        "target_hit_count": len(target_hits),
    }
    evidence_id = stable_id(
        "grt-ref-profile",
        [card["source_card_key"], sha256_file(paf_path), parameters],
        24,
    )
    row = {
        "evidence_id": evidence_id,
        "stage": "assignment",
        "evidence_type": "grt_usage_ref_profile",
        "status": "accepted",
        "q_version": "",
        "q_source_sha256": "",
        "query_artifact_relpath": dataset_row["fasta_relpath"],
        "query_sha256": sha256_file(dataset_path),
        "donor_set_id": "",
        "target_artifact_relpath": reference_row["fasta_relpath"],
        "target_sha256": sha256_file(reference_path),
        "source_dataset": dataset,
        "source_contig": contig,
        "source_start": 1,
        "source_end": len(source_sequence),
        "orientation": card["orientation"],
        "target_chr": evidence_target_chr,
        "target_start": target_start,
        "target_end": target_end,
        "tool": tool,
        "tool_version": version,
        "preset": preset,
        "parameters_json": canonical_json(parameters),
        "raw_artifact_relpath": relative(server_dir, paf_path),
        "raw_artifact_sha256": sha256_file(paf_path),
        "coordinate_system": "paf_0_based_half_open",
        "projection_status": "projected",
    }
    return row, status, max(1, anchor)


def existing_display_evidence(
    server_dir: Path,
    card: dict[str, object],
    source_sequence: str,
    dataset_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    names = [row["dataset_name"] for row in dataset_rows]
    source_dataset = str(card["dataset_name"])
    chr_name = str(card["target_chr"])
    if source_dataset not in names:
        fail(f"source card dataset is absent: {source_dataset}")
    chr_run = server_dir / f"runs/chr_{chr_name}"
    results: list[dict[str, object]] = []
    source_index = names.index(source_dataset)
    for other_index, other_dataset in enumerate(names):
        source_fasta = chr_run / f"datasets/{source_dataset}.fa"
        other_fasta = chr_run / f"datasets/{other_dataset}.fa"
        if not source_fasta.is_file() or not other_fasta.is_file():
            continue
        if other_dataset == source_dataset:
            run_dir = chr_run / f"{source_dataset}_vs_self"
            left_fasta = right_fasta = source_fasta
            source_role = "both"
        elif source_index < other_index:
            run_dir = chr_run / f"{source_dataset}_vs_{other_dataset}"
            left_fasta, right_fasta = source_fasta, other_fasta
            source_role = "target"
        else:
            run_dir = chr_run / f"{other_dataset}_vs_{source_dataset}"
            left_fasta, right_fasta = other_fasta, source_fasta
            source_role = "query"
        paf_path = run_dir / "result.paf"
        if not paf_path.is_file():
            continue
        tool, version, preset = alignment_profile(server_dir, source_dataset)
        parameters = {
            "provenance": "existing_main_view",
            "role": "display_pairwise",
            "source_paf_role": source_role,
            "target_dataset": other_dataset,
        }
        evidence_id = stable_id(
            "grt-display-existing",
            [card["source_card_key"], relative(server_dir, paf_path), sha256_file(paf_path)],
            24,
        )
        results.append(
            {
                "evidence_id": evidence_id,
                "stage": "display_pairwise",
                "evidence_type": "grt_usage_display_pairwise",
                "status": "accepted",
                "q_version": "",
                "q_source_sha256": "",
                "query_artifact_relpath": relative(server_dir, right_fasta),
                "query_sha256": sha256_file(right_fasta),
                "donor_set_id": "",
                "target_artifact_relpath": relative(server_dir, left_fasta),
                "target_sha256": sha256_file(left_fasta),
                "source_dataset": source_dataset,
                "source_contig": card["contig_name"],
                "source_start": 1,
                "source_end": len(source_sequence),
                "orientation": card["orientation"],
                "target_chr": chr_name,
                "target_start": "",
                "target_end": "",
                "tool": tool,
                "tool_version": version,
                "preset": preset,
                "parameters_json": canonical_json(parameters),
                "raw_artifact_relpath": relative(server_dir, paf_path),
                "raw_artifact_sha256": sha256_file(paf_path),
                "coordinate_system": "paf_0_based_half_open",
                "projection_status": "native",
            }
        )
    return results


def run_display_minimap(
    executable: dict[str, str],
    threads: int,
    run_dir: Path,
    target_records: list[tuple[str, str]],
    query_record: tuple[str, str],
) -> tuple[Path, Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    target_path = run_dir / "target.fa"
    query_path = run_dir / "query.fa"
    result_path = run_dir / "result.paf"
    checkpoint_path = run_dir / "checkpoint.json"
    write_fasta(target_path, target_records)
    write_fasta(query_path, [query_record])
    command = [
        executable["resolved"],
        "-x",
        DISPLAY_PRESET,
        "-c",
        "--secondary=no",
        "-t",
        str(threads),
        "-o",
        str(result_path),
        str(target_path),
        str(query_path),
    ]
    fingerprint = stable_id(
        "display-pairwise",
        {
            "engine_version": ENGINE_VERSION,
            "query_sha256": sha256_file(query_path),
            "target_sha256": sha256_file(target_path),
            "tool_sha256": executable["sha256"],
            "command": command[1:],
        },
        40,
    )
    cached = False
    if checkpoint_path.is_file() and result_path.is_file():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            cached = (
                checkpoint.get("fingerprint") == fingerprint
                and checkpoint.get("result_sha256") == sha256_file(result_path)
            )
        except json.JSONDecodeError:
            cached = False
    if not cached:
        (run_dir / "command.txt").write_text(shlex.join(command) + "\n", encoding="utf-8", newline="")
        with (run_dir / "stdout.log").open("w", encoding="utf-8") as stdout_handle, (
            run_dir / "stderr.log"
        ).open("w", encoding="utf-8") as stderr_handle:
            completed = subprocess.run(
                command,
                check=False,
                cwd=run_dir,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
            )
        if completed.returncode != 0 or not result_path.is_file():
            fail(f"display minimap2 failed ({completed.returncode}): {run_dir}")
        atomic_write_json(
            checkpoint_path,
            {
                "workflow": WORKFLOW,
                "engine_version": ENGINE_VERSION,
                "fingerprint": fingerprint,
                "result_sha256": sha256_file(result_path),
            },
        )
    return query_path, target_path, result_path


def supplemental_display_evidence(
    server_dir: Path,
    card: dict[str, object],
    source_sequence: str,
    dataset_rows: list[dict[str, str]],
    visible: dict[tuple[str, str], list[tuple[str, str]]],
    minimap: dict[str, str],
    threads: int,
) -> list[dict[str, object]]:
    card_dir = stable_id("card", card["source_card_key"], 20)
    results: list[dict[str, object]] = []
    for dataset_row in dataset_rows:
        target_dataset = dataset_row["dataset_name"]
        target_records = [
            (name, sequence)
            for name, sequence in visible.get((str(card["target_chr"]), target_dataset), [])
            if (target_dataset, name) != (card["dataset_name"], card["contig_name"])
        ]
        if not target_records:
            continue
        run_dir = server_dir / f"grt/evidence/display/by_card/{card_dir}/{target_dataset}"
        query_path, target_path, paf_path = run_display_minimap(
            minimap,
            threads,
            run_dir,
            target_records,
            (str(card["contig_name"]), source_sequence),
        )
        parameters = {
            "provenance": "grt_supplement",
            "role": "display_pairwise",
            "target_dataset": target_dataset,
            "target_members": [name for name, _sequence in target_records],
        }
        evidence_id = stable_id(
            "grt-display-supplement",
            [card["source_card_key"], target_dataset, sha256_file(paf_path)],
            24,
        )
        results.append(
            {
                "evidence_id": evidence_id,
                "stage": "display_pairwise",
                "evidence_type": "grt_usage_display_pairwise",
                "status": "accepted",
                "q_version": "",
                "q_source_sha256": "",
                "query_artifact_relpath": relative(server_dir, query_path),
                "query_sha256": sha256_file(query_path),
                "donor_set_id": "",
                "target_artifact_relpath": relative(server_dir, target_path),
                "target_sha256": sha256_file(target_path),
                "source_dataset": card["dataset_name"],
                "source_contig": card["contig_name"],
                "source_start": 1,
                "source_end": len(source_sequence),
                "orientation": card["orientation"],
                "target_chr": card["target_chr"],
                "target_start": "",
                "target_end": "",
                "tool": "minimap2",
                "tool_version": minimap["version"],
                "preset": DISPLAY_PRESET,
                "parameters_json": canonical_json(parameters),
                "raw_artifact_relpath": relative(server_dir, paf_path),
                "raw_artifact_sha256": sha256_file(paf_path),
                "coordinate_system": "paf_0_based_half_open",
                "projection_status": "native",
            }
        )
    return results


def visible_members(
    cards: list[dict[str, object]],
    assignment_rows: list[dict[str, str]],
    sources: dict[tuple[str, str], str],
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    members: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for row in assignment_rows:
        members[(row["assigned_chr_name"], row["dataset_name"])].add(
            (row["seq_name"], sources[(row["dataset_name"], row["seq_name"])])
        )
    for card in cards:
        if card["placement_mode"] in {"grt_promoted", "cross_chr_grt_usage"}:
            key = (str(card["dataset_name"]), str(card["contig_name"]))
            members[(str(card["target_chr"]), str(card["dataset_name"]))].add(
                (key[1], sources[key])
            )
    return {key: sorted(values) for key, values in members.items()}


def cleanup_stale_display_dirs(server_dir: Path, cards: list[dict[str, object]]) -> None:
    root = server_dir / "grt/evidence/display/by_card"
    if not root.is_dir():
        return
    expected = {
        stable_id("card", card["source_card_key"], 20)
        for card in cards
        if card["placement_mode"] in {"grt_promoted", "cross_chr_grt_usage"}
    }
    for child in root.iterdir():
        if child.name in expected:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def execute(args: argparse.Namespace) -> None:
    server_dir = args.server_dir.resolve()
    package = read_single(server_dir / "metadata/package.tsv")
    if (
        package.get("workflow") != WORKFLOW
        or package.get("schema_version") != "1"
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; evidence packaging has no legacy fallback")

    dataset_rows = read_tsv(server_dir / "metadata/datasets.tsv", DATASET_FIELDS)
    datasets = {row["dataset_name"]: row for row in dataset_rows}
    reference = read_single(
        server_dir / "metadata/reference.tsv",
        ["reference_name", "species_name", "assembly_label", "fasta_relpath", "fai_relpath"],
    )
    assignment_rows = read_tsv(
        server_dir / "metadata/chr_assignments.tsv", CHR_ASSIGNMENT_FIELDS
    )
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in assignment_rows:
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    sources = source_catalog(server_dir)
    events = read_events(server_dir / "metadata/grt_events.jsonl")
    final_path = json.loads(
        (server_dir / "metadata/grt_final_path.json").read_text(encoding="utf-8")
    )
    cards = accepted_source_cards(events, assignments, final_segment_anchors(final_path))
    visible = visible_members(cards, assignment_rows, sources)
    cleanup_stale_display_dirs(server_dir, cards)

    evidence_rows = [
        row
        for row in read_tsv(server_dir / "metadata/grt_evidence_registry.tsv", EVIDENCE_FIELDS)
        if row["evidence_type"] not in {"grt_usage_ref_profile", "grt_usage_display_pairwise"}
    ]
    needs_supplement = any(
        card["placement_mode"] in {"grt_promoted", "cross_chr_grt_usage"}
        for card in cards
    )
    minimap = executable_identity(args.minimap2) if needs_supplement else None
    output_cards: list[dict[str, object]] = []
    for card in cards:
        source_key = (str(card["dataset_name"]), str(card["contig_name"]))
        source_sequence = sources[source_key]
        ref_row, ref_status, anchor = build_ref_evidence(
            server_dir,
            card,
            source_sequence,
            datasets[source_key[0]],
            reference,
        )
        evidence_rows.append(ref_row)
        if card["placement_mode"] == "normal":
            pairwise_rows = existing_display_evidence(
                server_dir, card, source_sequence, dataset_rows
            )
        else:
            assert minimap is not None
            pairwise_rows = supplemental_display_evidence(
                server_dir,
                card,
                source_sequence,
                dataset_rows,
                visible,
                minimap,
                args.threads,
            )
        if not pairwise_rows:
            fail(
                f"used source {card['source_card_key']} has no display-pairwise target; "
                "the main-view alignment set is incomplete"
            )
        evidence_rows.extend(pairwise_rows)
        output_cards.append(
            {
                "source_card_key": card["source_card_key"],
                "dataset_name": card["dataset_name"],
                "contig_name": card["contig_name"],
                "original_assignment": card["original_assignment"],
                "target_chr": card["target_chr"],
                "placement_mode": card["placement_mode"],
                "ref_alignment_status": ref_status,
                "anchor_start": anchor,
                "orientation": card["orientation"],
                "ref_evidence_ids_json": json_list([str(ref_row["evidence_id"])]),
                "accepted_event_ids_json": json_list(card["event_ids"]),
                "final_path_segment_ids_json": json_list(card["segment_ids"]),
                "pairwise_evidence_ids_json": json_list(
                    [str(row["evidence_id"]) for row in pairwise_rows]
                ),
            }
        )

    metadata = server_dir / "metadata"
    atomic_write_tsv(metadata / "grt_evidence_registry.tsv", EVIDENCE_FIELDS, evidence_rows)
    atomic_write_tsv(metadata / "grt_used_contigs.tsv", USED_CONTIG_FIELDS, output_cards)
    tool_rows = [
        row
        for row in read_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS)
        if row["tool"] not in {"grt_evidence_package", "display_minimap2"}
    ]
    tool_rows.append(
        {
            "tool": "grt_evidence_package",
            "version": str(ENGINE_VERSION),
            "executable": ".prepare_lib/tools/grt_evidence_package.py",
        }
    )
    if minimap is not None:
        tool_rows.append(
            {
                "tool": "display_minimap2",
                "version": minimap["version"],
                "executable": minimap["resolved"],
            }
        )
    atomic_write_tsv(metadata / "grt_tool_versions.tsv", TOOL_FIELDS, tool_rows)
    try:
        summary = validate_contract(server_dir)
    except ContractError as exc:
        fail(str(exc))
    summary["used_contigs"] = len(output_cards)
    summary["supplemented_contigs"] = sum(
        card["placement_mode"] in {"grt_promoted", "cross_chr_grt_usage"}
        for card in cards
    )
    atomic_write_json(metadata / "grt_contract_summary.json", summary)
    print(canonical_json(summary))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, type=Path)
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--threads", type=int, default=10)
    args = parser.parse_args()
    if args.threads < 1:
        fail("threads must be a positive integer")
    execute(args)


if __name__ == "__main__":
    main()
