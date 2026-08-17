#!/usr/bin/env python3

"""Run the two canonical AssembleFill rounds against one frozen GRT donor set."""

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
from typing import Iterable

try:
    from grt_core import *
except ModuleNotFoundError:  # Imported as server.tools.grt_step1.
    from .grt_core import *


def round_artifact_relpath(stage: str) -> str:
    return "grt/evidence/step1/round1" if stage == "step1_round1" else "grt/evidence/step1/round2"


def run_round_stage(
    server_dir: Path,
    run_id: str,
    stage: str,
    q_input_version: str,
    q_output_version: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    donor_set: dict[str, str],
    donor_members: list[dict[str, str]],
    assignments: dict[tuple[str, str], str],
    sources: dict[tuple[str, str], str],
    consumed: list[dict[str, object]],
    minimap: dict[str, str],
    threads: int,
) -> tuple[dict[str, object], bool]:
    q_input_path = server_dir / f"grt/q/{q_input_version}.fa"
    q_input_sha256 = sha256_file(q_input_path)
    flank_records, gaps, query_map = build_flanks(q_input_version, chromosome_order, input_records)
    flank_payload = fasta_bytes(flank_records)
    flank_sha256 = sha256_bytes(flank_payload)
    parameters = {
        "preset": PRESET,
        "cigar": True,
        "threads": threads,
        "flank_length": FLANK_LENGTH,
        "min_gap_length": MIN_GAP_LENGTH,
        "min_alignment_length": MIN_ALIGNMENT_LENGTH,
        "min_identity": MIN_IDENTITY,
        "max_fill_length": MAX_FILL_LENGTH,
        "arbitration": "identity,aligned_length,mapq,fragment,same_orientation_distinct_target_reuse",
    }
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "q_version": q_input_version,
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "flank_query_sha256": flank_sha256,
        "donor_set_id": donor_set["donor_set_id"],
        "donor_target_sha256": donor_set["fasta_sha256"],
        "donor_fragment_index_sha256": sha256_file(
            server_dir / "metadata/grt_donor_fragments.tsv"
        ),
        "tool": minimap,
        "parameters": parameters,
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT {stage} cache hit: {fingerprint}")
        return cached, True

    invalidate_step1_from(server_dir, stage)

    artifact_relpath = round_artifact_relpath(stage)
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage}.", dir=artifact_dir.parent))
    try:
        flank_path = temporary / "flanks.fa"
        flank_path.write_bytes(flank_payload)
        paf_path = temporary / "result.paf"
        donor_path = server_dir / donor_set["fasta_relpath"]
        donor_records = dict(read_fasta_allow_empty(donor_path))
        members_by_record = {row["fasta_record_name"]: row for row in donor_members}
        if set(donor_records) != set(members_by_record):
            fail("ordinary D0 FASTA records differ from its frozen member manifest")
        donor_fragments = read_donor_fragments(
            server_dir, donor_set, donor_members, donor_records
        )
        fragments_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
        for fragment in donor_fragments:
            fragments_by_record[fragment["fasta_record_name"]].append(fragment)
        artifact_identity_by_chr: dict[str, dict[str, str]] = {}
        chromosome_task_rows: list[dict[str, object]] = []
        paf_parts: list[bytes] = []
        paf_rows: list[dict[str, object]] = []
        for chromosome in chromosome_order:
            chromosome_flanks = [
                (name, sequence)
                for name, sequence in flank_records
                if query_map[name][0]["chr"] == chromosome
            ]
            chromosome_q_rows = [
                row for row in input_q_rows if row["chr"] == chromosome
            ]
            chromosome_query_map = {
                name: query_map[name] for name, _sequence in chromosome_flanks
            }
            target_lengths = {
                name: len(sequence) for name, sequence in donor_records.items()
            }
            cache_dir, cache_hit, chromosome_key = cached_chromosome_alignment(
                server_dir,
                stage,
                chromosome,
                q_input_sha256,
                sha256_bytes(input_records[chromosome].encode("ascii")),
                chromosome_q_rows,
                chromosome_flanks,
                chromosome_query_map,
                donor_set,
                bool(donor_records),
                target_lengths,
                minimap,
                parameters,
                threads,
            )
            print(
                f"GRT {stage} chromosome {chromosome}: "
                f"{'cache hit' if cache_hit else 'computed'}"
            )
            chromosome_artifact = temporary / "by_chr" / chromosome_key
            chromosome_artifact.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache_dir, chromosome_artifact)
            chromosome_paf = chromosome_artifact / "result.paf"
            paf_parts.append(chromosome_paf.read_bytes())
            paf_rows.extend(
                parse_paf(chromosome_paf, chromosome_query_map, target_lengths)
            )
            query_relpath = f"{artifact_relpath}/by_chr/{chromosome_key}/flanks.fa"
            raw_relpath = f"{artifact_relpath}/by_chr/{chromosome_key}/result.paf"
            artifact_identity_by_chr[chromosome] = {
                "query_relpath": query_relpath,
                "query_sha256": sha256_file(chromosome_artifact / "flanks.fa"),
                "raw_relpath": raw_relpath,
                "raw_sha256": sha256_file(chromosome_paf),
            }
            chromosome_task_rows.append(
                {
                    "chr": chromosome,
                    "chromosome_key": chromosome_key,
                    "cache_key": cache_dir.name,
                    "query_relpath": query_relpath,
                    "query_sha256": artifact_identity_by_chr[chromosome]["query_sha256"],
                    "raw_relpath": raw_relpath,
                    "raw_sha256": artifact_identity_by_chr[chromosome]["raw_sha256"],
                }
            )
        paf_path.write_bytes(b"".join(paf_parts))
        write_tsv(
            temporary / "chromosome_tasks.tsv",
            [
                "chr",
                "chromosome_key",
                "cache_key",
                "query_relpath",
                "query_sha256",
                "raw_relpath",
                "raw_sha256",
            ],
            chromosome_task_rows,
        )
        candidates, rejections = build_candidates(
            stage,
            paf_rows,
            gaps,
            members_by_record,
            donor_records,
            fragments_by_record,
        )
        candidates = arbitrate_candidates(candidates, consumed)
        query_relpath = f"{artifact_relpath}/flanks.fa"
        raw_relpath = f"{artifact_relpath}/result.paf"
        evidence_rows = stage_evidence_rows(
            stage,
            q_input_version,
            q_input_sha256,
            donor_set,
            minimap,
            artifact_identity_by_chr,
            candidates,
        )
        output_paths, output_records, events, usage_rows, attempts = apply_round(
            run_id,
            stage,
            q_input_version,
            q_output_version,
            chromosome_order,
            input_paths,
            input_records,
            gaps,
            candidates,
            assignments,
            q_input_sha256,
            sources,
        )
        for row in usage_rows:
            row["donor_set_id"] = donor_set["donor_set_id"]
        q_rows = q_rows_for_paths(q_output_version, chromosome_order, output_paths)
        q_output_temporary = server_dir / f"grt/q/.{q_output_version}.fa.tmp.{os.getpid()}"
        write_fasta(
            q_output_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail(f"internal {stage} q output hash disagreement")
        write_tsv(temporary / "candidates.tsv", CANDIDATE_FIELDS, [candidate_public_row(row) for row in candidates])
        write_tsv(temporary / "rejections.tsv", REJECTION_FIELDS, rejections)
        write_tsv(
            temporary / "arbitration.tsv",
            ARBITRATION_FIELDS,
            [
                {
                    **candidate_public_row(row),
                    "outcome": row["outcome"],
                    "reason": row["reason"],
                    "event_id": row.get("event_id", ""),
                    "final_path_segment_id": row.get("final_path_segment_id", ""),
                }
                for row in candidates
            ],
        )
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_tsv(temporary / "evidence.tsv", EVIDENCE_FIELDS, evidence_rows)
        write_tsv(temporary / "usage.tsv", USAGE_FIELDS, usage_rows)
        write_tsv(temporary / "gap_attempts.tsv", ATTEMPT_FIELDS, attempts)
        write_jsonl(temporary / "events.jsonl", events)
        accepted_intervals = [
            {
                "candidate_id": row["candidate_id"],
                "object_id": row["object_id"],
                "chr": row["chr"],
                "source_dataset": row["source_dataset"],
                "source_contig": row["source_contig"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "orientation": row["orientation"],
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
            "q_input_version": q_input_version,
            "q_input_sha256": q_input_sha256,
            "q_output_version": q_output_version,
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set["donor_set_id"],
            "query_sha256": flank_sha256,
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
        (server_dir / "grt/q").mkdir(parents=True, exist_ok=True)
        os.replace(q_output_temporary, server_dir / f"grt/q/{q_output_version}.fa")
        output_relpaths = [
            path.relative_to(server_dir).as_posix()
            for path in artifact_dir.rglob("*")
            if path.is_file()
        ] + [f"grt/q/{q_output_version}.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        print(
            f"GRT {stage} complete: gaps={len(gaps)}, candidates={len(candidates)}, "
            f"accepted={len(accepted_intervals)}"
        )
        return result, False
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise


def run_filter_stage(
    server_dir: Path,
    run_id: str,
    chromosome_order: list[str],
    input_paths: dict[str, list[dict[str, object]]],
    input_records: dict[str, str],
    input_q_rows: list[dict[str, object]],
    sources: dict[tuple[str, str], str],
    donor_set_id: str,
) -> tuple[dict[str, object], bool]:
    stage = "step1_filter"
    q_input_sha256 = sha256_file(server_dir / "grt/q/q0r1.fa")
    fingerprint_payload = {
        "workflow": WORKFLOW,
        "engine_version": ENGINE_VERSION,
        "stage": stage,
        "q_version": "q0r1",
        "q_source_sha256": q_input_sha256,
        "q_segments_sha256": json_hash(input_q_rows),
        "min_component_length": MIN_COMPONENT_LENGTH,
        "connector_length": FILTER_CONNECTOR_LENGTH,
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"GRT {stage} cache hit: {fingerprint}")
        return cached, True
    invalidate_step1_from(server_dir, stage)
    artifact_relpath = "grt/evidence/step1/filter"
    artifact_dir = server_dir / artifact_relpath
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage}.", dir=artifact_dir.parent))
    try:
        output_paths, output_records, events = apply_filter(
            run_id,
            chromosome_order,
            input_paths,
            input_records,
            q_input_sha256,
            sources,
        )
        q_rows = q_rows_for_paths("q0f", chromosome_order, output_paths)
        q_output_temporary = server_dir / f"grt/q/.q0f.fa.tmp.{os.getpid()}"
        write_fasta(
            q_output_temporary,
            [(chromosome, output_records[chromosome]) for chromosome in chromosome_order],
        )
        q_output_sha256 = sha256_file(q_output_temporary)
        if any(event["q_after"]["sha256"] != q_output_sha256 for event in events):
            fail("internal step1_filter q output hash disagreement")
        write_tsv(temporary / "q_segments.tsv", Q_SEGMENT_FIELDS, q_rows)
        write_jsonl(temporary / "events.jsonl", events)
        write_tsv(
            temporary / "components.tsv",
            ["chr", "status", "reason", "kept_intervals_json", "removed_intervals_json"],
            [
                {
                    "chr": event["chr"],
                    "status": event["status"],
                    "reason": event["reason"],
                    "kept_intervals_json": canonical_json(event["edit"]["kept_intervals"]),
                    "removed_intervals_json": canonical_json(event["edit"]["removed_intervals"]),
                }
                for event in events
            ],
        )
        result: dict[str, object] = {
            "workflow": WORKFLOW,
            "engine_version": ENGINE_VERSION,
            "stage": stage,
            "input_fingerprint": fingerprint,
            "q_input_version": "q0r1",
            "q_input_sha256": q_input_sha256,
            "q_output_version": "q0f",
            "q_output_sha256": q_output_sha256,
            "donor_set_id": donor_set_id,
            "q_rows": q_rows,
            "evidence_rows": [],
            "usage_rows": [],
            "events": events,
            "attempts": [],
            "accepted_intervals": [],
        }
        (temporary / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="",
        )
        commit_stage_directory(temporary, artifact_dir)
        os.replace(q_output_temporary, server_dir / "grt/q/q0f.fa")
        output_relpaths = [
            f"{artifact_relpath}/{path.name}" for path in artifact_dir.iterdir() if path.is_file()
        ] + ["grt/q/q0f.fa"]
        write_checkpoint(
            server_dir,
            stage,
            fingerprint,
            fingerprint_payload,
            f"{artifact_relpath}/result.json",
            output_relpaths,
        )
        removed = sum(len(event["edit"]["removed_intervals"]) for event in events if event["status"] == "accepted")
        print(f"GRT step1_filter complete: removed_components={removed}")
        return result, False
    except BaseException:
        if temporary.exists():
            failed_root = server_dir / "grt/failed"
            failed_root.mkdir(parents=True, exist_ok=True)
            failed_dir = failed_root / f"{stage}-{os.getpid()}"
            if failed_dir.exists():
                shutil.rmtree(failed_dir)
            os.replace(temporary, failed_dir)
        raise




def publish_step1_metadata(
    server_dir: Path,
    base_q_rows: list[dict[str, str]],
    base_evidence_rows: list[dict[str, str]],
    donor_freeze_row: dict[str, str],
    base_tool_rows: list[dict[str, str]],
    minimap: dict[str, str],
    results: list[dict[str, object]],
) -> None:
    metadata = server_dir / "metadata"
    q_rows: list[dict[str, object]] = list(base_q_rows)
    evidence_rows: list[dict[str, object]] = list(base_evidence_rows)
    usage_rows: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    stage_rows: list[dict[str, object]] = [donor_freeze_row]
    for result in results:
        q_rows.extend(result["q_rows"])
        evidence_rows.extend(result["evidence_rows"])
        usage_rows.extend(result["usage_rows"])
        events.extend(result["events"])
        attempts.extend(result["attempts"])
        stage_rows.append(stage_status_row(server_dir, result))
    tool_rows = [
        row
        for row in base_tool_rows
        if row["tool"] not in {"grt_step1", "step1_minimap2"}
    ]
    if results:
        tool_rows.extend(
            [
                {
                    "tool": "grt_step1",
                    "version": str(ENGINE_VERSION),
                    "executable": ".prepare_lib/tools/grt_step1.py",
                },
                {
                    "tool": "step1_minimap2",
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
        or package.get("schema_version") != SCHEMA_VERSION
        or package.get("grt_precompute_enabled") != "true"
        or package.get("recipe_locked") != "true"
    ):
        fail("unsupported package workflow/schema; Step1 has no legacy fallback")
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
    donor_set, donor_members, donor_freeze_row = verify_donor_freeze(server_dir, recipe)
    sources = source_catalog(server_dir)
    all_q_rows = read_tsv(server_dir / "metadata/grt_q_segments.tsv", Q_SEGMENT_FIELDS)
    base_q_rows = [row for row in all_q_rows if row["q_version"] == "q0"]
    all_evidence_rows = read_tsv(server_dir / "metadata/grt_evidence_registry.tsv", EVIDENCE_FIELDS)
    base_evidence_rows = [row for row in all_evidence_rows if row["stage"] == "assignment"]
    base_tool_rows = read_tsv(server_dir / "metadata/grt_tool_versions.tsv", TOOL_FIELDS)
    minimap = executable_identity(args.minimap2)
    assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in read_tsv(
        server_dir / "metadata/chr_assignments.tsv",
        CHR_ASSIGNMENT_FIELDS,
    ):
        assignments[(row["dataset_name"], row["seq_name"])].add(
            row["assigned_chr_name"]
        )
    chromosome_order, q0_paths, q0_records = load_q_paths(
        server_dir, "q0", base_q_rows, sources
    )
    run_id = stable_id(
        "grt-run",
        {
            "recipe_id": recipe["recipe_id"],
            "donor_set_id": donor_set["donor_set_id"],
            "q0_sha256": sha256_file(server_dir / "grt/q/q0.fa"),
            "engine_version": ENGINE_VERSION,
            "minimap": minimap,
        },
        24,
    )
    results: list[dict[str, object]] = []
    round1, _round1_cached = run_round_stage(
        server_dir,
        run_id,
        "step1_round1",
        "q0",
        "q0r1",
        chromosome_order,
        q0_paths,
        q0_records,
        base_q_rows,
        donor_set,
        donor_members,
        assignments,
        sources,
        [],
        minimap,
        args.threads,
    )
    results.append(round1)
    publish_step1_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    _, q0r1_paths, q0r1_records = load_q_paths(
        server_dir, "q0r1", round1["q_rows"], sources
    )
    filter_result, _filter_cached = run_filter_stage(
        server_dir,
        run_id,
        chromosome_order,
        q0r1_paths,
        q0r1_records,
        round1["q_rows"],
        sources,
        donor_set["donor_set_id"],
    )
    reconcile_filtered_round1_events(round1, filter_result)
    results.append(filter_result)
    publish_step1_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    _, q0f_paths, q0f_records = load_q_paths(
        server_dir, "q0f", filter_result["q_rows"], sources
    )
    round2, _round2_cached = run_round_stage(
        server_dir,
        run_id,
        "step1_round2",
        "q0f",
        "q1",
        chromosome_order,
        q0f_paths,
        q0f_records,
        filter_result["q_rows"],
        donor_set,
        donor_members,
        assignments,
        sources,
        round1["accepted_intervals"],
        minimap,
        args.threads,
    )
    results.append(round2)
    publish_step1_metadata(
        server_dir,
        base_q_rows,
        base_evidence_rows,
        donor_freeze_row,
        base_tool_rows,
        minimap,
        results,
    )
    q1_records = dict(read_fasta(server_dir / "grt/q/q1.fa"))
    replayed_round1 = replay_round_records(q0_records, round1["events"], sources)
    replayed_filter = replay_filter_records(replayed_round1, filter_result["events"])
    replayed_round2 = replay_round_records(replayed_filter, round2["events"], sources)
    if replayed_round2 != q1_records:
        fail("recorded Step1 events do not deterministically reconstruct q1")
    if donor_set["donor_set_id"] != round1["donor_set_id"] or donor_set["donor_set_id"] != round2["donor_set_id"]:
        fail("Step1 rounds do not reference the same frozen donor set")
    print(
        f"GRT Step1 complete: run={run_id}, donor_set={donor_set['donor_set_id']}, "
        f"q1_sha256={sha256_file(server_dir / 'grt/q/q1.fa')}"
    )


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
