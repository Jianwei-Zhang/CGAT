"""LGZ Step3 classification, correction, refill and Q3 publication."""

from __future__ import annotations

from .repair_common import *
from .refill_batch import RefillBatchAlignment
from .repair_mummer import (
    collect_mummer,
    grt_mummer_parameters,
)
from .repair_runtime import (
    execution_context,
    publish_repair_metadata,
)
from .repair_structural import (
    apply_corrections,
    build_correction_candidates,
    correction_usage_rows,
    promote_direct_primary_overlap_merges,
)


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
    gaps_by_chr: dict[str, list[dict[str, object]]] = defaultdict(list)
    for gap in gaps:
        gaps_by_chr[str(gap["chr"])].append(gap)
    for chromosome, path in paths.items():
        # Sequence gaps can lie inside a source contig or span several path
        # segments. Split at the actual N-run boundaries without changing the
        # source coordinates, sequence, or segment kind.
        annotated: list[dict[str, object]] = []
        cursor = 0
        for gap in sorted(gaps_by_chr[chromosome], key=lambda row: int(row["start0"])):
            start, end = int(gap["start0"]), int(gap["end0"])
            annotated.extend(slice_path(path, cursor, start))
            gap_segments = slice_path(path, start, end)
            if gap.get("origin"):
                origin_ids = [
                    str(gap["origin"]["object_id"]),
                    *map(str, gap["origin"].get("coalesced_object_ids", [])),
                ]
                for segment in gap_segments:
                    segment["origin_object_ids"] = list(dict.fromkeys(origin_ids))
            annotated.extend(gap_segments)
            cursor = end
        annotated.extend(slice_path(path, cursor, sum(int(segment["length"]) for segment in path)))
        paths[chromosome] = annotated



def attach_gap_origins_from_paths(
    paths: dict[str, list[dict[str, object]]],
    gaps: list[dict[str, object]],
    original_gaps: list[dict[str, object]],
) -> None:
    originals = {str(gap["object_id"]): gap for gap in original_gaps}
    for gap in gaps:
        key = (str(gap["chr"]), int(gap["start0"]), int(gap["end0"]))
        segments = slice_path(paths[key[0]], key[1], key[2])
        if not segments or any(not segment.get("origin_object_ids") for segment in segments):
            fail(f"cannot map filtered Step3 gap back to q2: {key}")
        origin_ids = list(dict.fromkeys(
            str(value)
            for segment in segments
            for value in segment["origin_object_ids"]
        ))
        if any(object_id not in originals for object_id in origin_ids):
            fail(f"filtered Step3 gap references unknown q2 origins: {key}")
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



def write_refill_projection(
    destination: Path,
    chromosome: str,
    sequence: str,
    q_rows: list[dict[str, object]],
    flank_records: list[tuple[str, str]],
    query_map: dict[str, tuple[dict[str, object], str]],
) -> Path:
    """Freeze the real pre-edit path used by these flank queries, not q2/q3."""
    queries = {}
    for name, flank in flank_records:
        gap, side = query_map[name]
        start = int(gap["start0"]) - len(flank) + 1 if side == "L" else int(gap["end0"]) + 1
        end = start + len(flank) - 1
        if gap["chr"] != chromosome or start < 1 or sequence[start - 1:end] != flank:
            fail(f"refill flank {name} disagrees with its working query path")
        queries[name] = {"q_start": start, "q_end": end}
    payload = {
        "schema_version": "grt_refill_flank_projection_v1",
        "chr": chromosome,
        "query_sha256": sha256_file(destination / "flanks.fa"),
        "q_chromosome_sha256": sha256_bytes(sequence.encode("ascii")),
        "q_length": len(sequence),
        "queries": queries,
        "working_q_rows": q_rows,
    }
    path = destination / "flank_projection.json"
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8", newline="")
    return path


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
    max_fill_length: int = REFILL_MAX_LENGTH,
    execution_profile: str = DEFAULT_EXECUTION_PROFILE,
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
        "max_fill_length": max_fill_length,
        "q_source": working_q_version,
    }
    artifact_identities: dict[str, dict[str, str]] = {}
    paf_rows: list[dict[str, object]] = []
    paf_parts: list[bytes] = []
    batch = (RefillBatchAlignment(
        server_dir, f"step3_refill_{round_name}", donor_set, minimap, threads,
        flank_records, query_map, target_lengths,
        temporary / "refill" / round_name / "batch",
    ) if execution_profile == "optimized" else None)
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
            alignment_runner=batch,
        )
        print(
            f"LGZ step3 refill {round_name} {chromosome}: "
            f"{'cache hit' if cache_hit else 'computed'}"
        )
        destination = temporary / "refill" / round_name / "by_chr" / chromosome_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cache_dir, destination)
        projection = write_refill_projection(
            destination, chromosome, records[chromosome], chromosome_rows,
            chromosome_flanks, chromosome_query_map,
        )
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
            "flank_projection_relpath": (
                f"{artifact_relpath}/refill/{round_name}/by_chr/"
                f"{chromosome_key}/flank_projection.json"
            ),
            "flank_projection_sha256": sha256_file(projection),
        }
    (temporary / "refill" / round_name / "flanks.fa").write_bytes(
        fasta_bytes(flank_records)
    )
    (temporary / "refill" / round_name / "result.paf").write_bytes(
        b"".join(paf_parts)
    )
    candidates, rejections = build_candidates(
        "step3", paf_rows, gaps, members_by_record, donor_records,
        max_fill_length=max_fill_length,
    )
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
    refill_max_length: int = REFILL_MAX_LENGTH,
    mummer_scope: str = DEFAULT_MUMMER_SCOPE,
    execution_profile: str = DEFAULT_EXECUTION_PROFILE,
) -> tuple[dict[str, object], bool]:
    stage = "step3"
    if refill_max_length < 1:
        fail("max-fill must be a positive integer")
    if repair_mode not in REPAIR_MODES:
        fail(f"unsupported Step3 repair mode: {repair_mode}")
    if mummer_scope not in MUMMER_SCOPES:
        fail(f"unsupported MUMmer scope: {mummer_scope}")
    q_input_sha256 = sha256_file(server_dir / "grt/q/q2.fa")
    if execution_profile not in EXECUTION_PROFILES:
        fail(f"unsupported execution profile: {execution_profile}")
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
        "mummer_scope": mummer_scope,
        "execution_profile": execution_profile,
        "execution_helper_sha256": EXECUTION_HELPER_SHA256 if execution_profile == "optimized" else None,
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
            "max_fill_length": refill_max_length,
            "rounds": 2,
            "post_round1_filter_min_component_length": MIN_COMPONENT_LENGTH,
            "post_round1_filter_connector_length": FILTER_CONNECTOR_LENGTH,
        },
        "consumed_intervals_sha256": json_hash(consumed),
    }
    fingerprint = json_hash(fingerprint_payload)
    cached = checkpoint_result(server_dir, stage, fingerprint)
    if cached is not None:
        print(f"LGZ step3 cache hit: {fingerprint}")
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
            mummer_scope=mummer_scope,
            execution_profile=execution_profile,
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
            use_index=execution_profile == "optimized",
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
            max_fill_length=refill_max_length,
            execution_profile=execution_profile,
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
                    "flank_projection_relpath": refill_artifacts[str(candidate["chr"])]["flank_projection_relpath"],
                    "flank_projection_sha256": refill_artifacts[str(candidate["chr"])]["flank_projection_sha256"],
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
            max_fill_length=refill_max_length,
            execution_profile=execution_profile,
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
                    "flank_projection_relpath": round2_artifacts[str(candidate["chr"])]["flank_projection_relpath"],
                    "flank_projection_sha256": round2_artifacts[str(candidate["chr"])]["flank_projection_sha256"],
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
        retained_events = reconcile_refill_rounds(
            chromosome_order, round1_paths, output_paths, q_output_sha256,
            refill_events, refill_usage, refill_evidence, round2_events, round2_usage,
        )
        events = [
            *correction_events,
            *refill_events,
            *filter_events,
            *round2_events,
            *retained_events,
        ]
        flatten_event_supersession(events)
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
            f"LGZ step3 complete: gaps={len(gaps)}, corrections="
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



def step2_gap_survives_step3(
    event: dict[str, object],
    q2_rows: list[dict[str, object]],
    step3: dict[str, object],
) -> bool:
    """Return true only for a provenance-verified explicit gap retained in q3."""
    edit = event.get("edit")
    if not isinstance(edit, dict) or edit.get("replacement_kind") != "gap":
        return False
    chromosome = str(event["chr"])
    after = event["q_after"]
    after_start = int(after["start"])
    after_end = int(after["end"])
    if (
        after.get("version") != step3.get("q_input_version")
        or after.get("sha256") != step3.get("q_input_sha256")
    ):
        return False
    if not any(
        row.get("segment_kind") == "gap"
        and row.get("q_version") == after.get("version")
        and int(row["q_start"]) == after_start
        and int(row["q_end"]) == after_end
        and not json.loads(str(row["evidence_ids_json"]))
        for row in q2_rows
    ):
        return False

    q3_rows = [
        row for row in step3["q_rows"] if str(row["chr"]) == chromosome
    ]
    for candidate in step3["events"]:
        if (
            str(candidate["chr"]) != chromosome
            or candidate.get("q_after_projection") != "surviving_origin_gap"
        ):
            continue
        q_before = candidate.get("q_before")
        q_after = candidate.get("q_after")
        if not isinstance(q_before, dict) or not isinstance(q_after, dict):
            continue
        if (
            q_before.get("version") != step3.get("q_input_version")
            or q_before.get("sha256") != step3.get("q_input_sha256")
            or int(q_before["start"]) != after_start
            or int(q_before["end"]) != after_end
            or q_after.get("version") != step3.get("q_output_version")
            or q_after.get("sha256") != step3.get("q_output_sha256")
        ):
            continue
        if any(
            row.get("segment_kind") == "gap"
            and row.get("q_version") == q_after.get("version")
            and int(row["q_start"]) == int(q_after["start"])
            and int(row["q_end"]) == int(q_after["end"])
            for row in q3_rows
        ):
            return True
    return False



def retain_source_fragments(
    event: dict[str, object],
    q2_rows: list[dict[str, object]],
    step2: dict[str, object],
    step3: dict[str, object],
    *,
    preserve_input_locus: bool = False,
) -> bool:
    """Materialize proven surviving fragments without rewriting the original edit.

    A correction or refill may trim a Step2 patch or an earlier Step3 refill.
    Exact removed-source slices prove trims even in shifted query coordinates.
    Remaining evidence is
    not proof that the *whole* source interval survived. Keep the historical
    event for q1 -> q2 replay and give each retained q3 fragment its own exact
    path event/usage. These lineage events describe retained sequence, not new
    sequence edits, so deliberately have no ``edit`` payload.
    """
    source = event.get("source")
    if not isinstance(source, dict) or not event.get("final_path_segment_id"):
        return False

    def same_source(row: dict[str, object]) -> bool:
        return (
            row.get("segment_kind") == "source"
            and row.get("dataset_name") == source["dataset"]
            and row.get("contig_name") == source["contig"]
            and row.get("orientation") == source["orientation"]
            and row.get("source_card_key") == event["source_card_key"]
            and bool(set(json.loads(str(row["evidence_ids_json"])))
                     & set(event["evidence_ids"]))
        )

    retained = [
        row for row in step3["q_rows"]
        if row["chr"] == event["chr"] and same_source(row)
    ]
    if (
        len(retained) == 1
        and int(retained[0]["source_start"]) == int(source["start"])
        and int(retained[0]["source_end"]) == int(source["end"])
    ):
        return False
    originals = [
        row for row in q2_rows if same_source(row)
        and int(row["source_start"]) == int(source["start"])
        and int(row["source_end"]) == int(source["end"])
        and int(row["q_start"]) == int(event["q_after"]["start"])
        and int(row["q_end"]) == int(event["q_after"]["end"])
    ]
    if len(originals) != 1:
        if not retained:
            return False
        fail(f"partially retained source event lacks one exact input segment: {event['event_id']}")
    original = originals[0]
    if (
        event["q_after"].get("version") != step3.get("q_input_version")
        or event["q_after"].get("sha256") != step3.get("q_input_sha256")
    ):
        fail(f"partially retained source event has stale input identity: {event['event_id']}")
    original_evidence = set(json.loads(str(original["evidence_ids_json"])))
    intervals = []
    for row in retained:
        start, end = int(row["source_start"]), int(row["source_end"])
        if (
            not int(source["start"]) <= start <= end <= int(source["end"])
            or end - start != int(row["q_end"]) - int(row["q_start"])
            or not original_evidence.intersection(json.loads(str(row["evidence_ids_json"])))
        ):
            fail(f"invalid retained source projection for event: {event['event_id']}")
        offset = (start - int(source["start"]) if source["orientation"] == "+"
                  else int(source["end"]) - end)
        input_start = int(original["q_start"]) + offset
        intervals.append((input_start, input_start + end - start, row))
    intervals.sort(key=lambda item: item[0])
    missing = []
    cursor = int(original["q_start"])
    for start, end, _row in intervals:
        if start < cursor:
            fail(f"overlapping retained source fragments for event: {event['event_id']}")
        if cursor < start:
            missing.append((cursor, start - 1))
        cursor = end + 1
    if cursor <= int(original["q_end"]):
        missing.append((cursor, int(original["q_end"])))
    if not missing:
        fail(f"unexplained source segmentation for event: {event['event_id']}")

    # A shifted refill's public q_before identifies an origin gap, not its
    # entire trim. Accept either a verified q2 edit or exact source slices
    # captured from the real working path by apply_round, never a broad locus.
    step3_events = {str(item["event_id"]): item for item in step3["events"]}
    cuts = []
    for candidate in step3["events"]:
        edit = candidate.get("edit", {})
        replacement = candidate
        if candidate["status"] == "superseded":
            replacement = step3_events.get(str(candidate.get("superseded_by_event_id")), {})
        if (
            candidate["chr"] != event["chr"]
            or replacement.get("status") != "accepted"
            or replacement.get("chr") != event["chr"]
            or edit.get("operation") != "replace_interval"
        ):
            continue
        if (
            not preserve_input_locus
            and edit.get("input_coordinate_space") == "q2_1_based_closed"
            and candidate["q_before"].get("version") == step3["q_input_version"]
            and candidate["q_before"].get("sha256") == step3["q_input_sha256"]
            and int(edit["input_start"]) == int(candidate["q_before"]["start"])
            and int(edit["input_end"]) == int(candidate["q_before"]["end"])
        ):
            cuts.append((int(edit["input_start"]), int(edit["input_end"]), replacement["event_id"]))
        for removed in edit.get("replaced_source_segments", []):
            if (
                removed.get("segment_kind") != "source"
                or removed.get("dataset_name") != source["dataset"]
                or removed.get("contig_name") != source["contig"]
                or removed.get("orientation") != source["orientation"]
                or removed.get("source_card_key") != event["source_card_key"]
                or not original_evidence.intersection(removed.get("evidence_ids", []))
            ):
                continue
            start, end = int(removed["source_start"]), int(removed["source_end"])
            if not int(source["start"]) <= start <= end <= int(source["end"]):
                fail(f"removed source trace exceeds its original event: {event['event_id']}")
            if end - start + 1 != int(removed["length"]):
                fail(f"removed source trace has invalid length: {event['event_id']}")
            offset = (start - int(source["start"]) if source["orientation"] == "+"
                      else int(source["end"]) - end)
            input_start = int(original["q_start"]) + offset
            cuts.append((input_start, input_start + end - start, replacement["event_id"]))
    replacing_ids = set()
    for start, end in missing:
        cursor = start
        for cut_start, cut_end, replacing_id in sorted(cuts):
            if cut_end < cursor or cut_start > end:
                continue
            if cut_start > cursor:
                break
            cursor = max(cursor, cut_end + 1)
            replacing_ids.add(str(replacing_id))
            if cursor > end:
                break
        if cursor <= end:
            if not retained:
                return False
            fail(f"source fragment disappeared without a proven edit: {event['event_id']}")

    consumed = [row for row in step2["usage_rows"]
                if row["event_id"] == event["event_id"]
                and row["status"] in {"accepted", "consumed"}]
    if not retained:
        replacement_id = sorted(replacing_ids)[0]
        event["status"] = "superseded"
        event["reason"] = "fully_replaced_by_step3"
        event["final_path_segment_id"] = ""
        event["superseded_by_event_id"] = replacement_id
        step3_events[replacement_id].setdefault("superseded_event_ids", []).append(event["event_id"])
        for usage in consumed:
            usage.update(status="superseded", final_path_segment_id="", reason="fully_replaced_by_step3")
        for row in step2["evidence_rows"]:
            if row["evidence_id"] in original_evidence and row["status"] == "accepted":
                row["status"] = "superseded"
        return True
    children = []
    for start, end, row in intervals:
        identity = [event["event_id"], row["segment_id"], start, end]
        child_id = stable_id("event-retained", identity, 24)
        segment_id = stable_id("grt-segment", identity, 24)
        child = {
            "run_id": event["run_id"], "event_id": child_id, "stage": "step3",
            "chr": event["chr"], "object_id": event["object_id"],
            "action": "patch", "status": "accepted",
            "reason": "retained_source_fragment",
            "q_before": (dict(event["q_before"]) if preserve_input_locus else {
                "version": step3["q_input_version"], "start": start,
                "end": end, "sha256": step3["q_input_sha256"]}),
            "q_after": {"version": step3["q_output_version"],
                        "start": int(row["q_start"]), "end": int(row["q_end"]),
                        "sha256": step3["q_output_sha256"]},
            "source": {**source, "start": int(row["source_start"]),
                       "end": int(row["source_end"])},
            "source_card_key": event["source_card_key"],
            "final_path_segment_id": segment_id,
            "evidence_ids": sorted(original_evidence.intersection(
                json.loads(str(row["evidence_ids_json"])))),
            "usage_ids": [], "retained_from_event_id": event["event_id"],
            "retained_after_event_ids": sorted(replacing_ids),
        }
        for usage in consumed:
            if (usage["source_dataset"] != source["dataset"]
                or usage["source_contig"] != source["contig"]
                or int(usage["source_start"]) > int(row["source_start"])
                or int(usage["source_end"]) < int(row["source_end"])):
                continue
            usage_id = stable_id("usage-retained", [usage["usage_id"], child_id], 24)
            child["usage_ids"].append(usage_id)
            step3["usage_rows"].append({
                **usage, "usage_id": usage_id, "stage": "step3", "event_id": child_id,
                "source_start": int(row["source_start"]),
                "source_end": int(row["source_end"]),
                "final_path_segment_id": segment_id,
                "reason": "retained_source_fragment",
            })
        if consumed and not child["usage_ids"]:
            fail(f"retained source fragment lacks matching donor usage: {event['event_id']}")
        children.append(child)
    event["status"] = "superseded"
    event["reason"] = "partially_replaced_by_step3"
    event["final_path_segment_id"] = ""
    event["superseded_by_event_id"] = children[0]["event_id"]
    event["retained_event_ids"] = [child["event_id"] for child in children]
    children[0]["superseded_event_ids"] = [event["event_id"]]
    for usage in consumed:
        usage["status"] = "superseded"
        usage["final_path_segment_id"] = ""
        usage["reason"] = "partially_replaced_by_step3"
    step3["events"].extend(children)
    return True


def reconcile_refill_rounds(
    chromosome_order: list[str],
    round1_paths: dict[str, list[dict[str, object]]],
    output_paths: dict[str, list[dict[str, object]]],
    q_output_sha256: str,
    refill_events: list[dict[str, object]],
    refill_usage: list[dict[str, object]],
    refill_evidence: list[dict[str, object]],
    round2_events: list[dict[str, object]],
    round2_usage: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Reconcile round1 donor sequence trimmed/replaced by round2 flank edits."""
    rows = q_rows_for_paths("q3", chromosome_order, round1_paths)
    final_rows = q_rows_for_paths("q3", chromosome_order, output_paths)
    prior = {"events": refill_events, "usage_rows": refill_usage,
             "evidence_rows": refill_evidence}
    following = {
        "events": list(round2_events), "usage_rows": round2_usage, "q_rows": final_rows,
        "q_input_version": "q3", "q_output_version": "q3",
        "q_output_sha256": q_output_sha256,
    }
    for event in refill_events:
        if event["status"] != "accepted" or not event.get("final_path_segment_id"):
            continue
        following["q_input_sha256"] = event["q_after"]["sha256"]
        retain_source_fragments(
            event, [row for row in rows if row["chr"] == event["chr"]], prior,
            following, preserve_input_locus=True,
        )
    return following["events"][len(round2_events):]


def reconcile_step2_events_with_step3(
    step2: dict[str, object],
    step3: dict[str, object],
) -> None:
    """Reconcile accepted Step2 path segments with the finalized q3 path."""
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
        if retain_source_fragments(
            event, q2_rows_by_chr.get(chromosome, []), step2, step3
        ):
            continue
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
            if step2_gap_survives_step3(
                event, q2_rows_by_chr.get(chromosome, []), step3
            ):
                continue
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
    flatten_event_supersession([*step2["events"], *step3["events"]])
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



def execute_step3(args: argparse.Namespace) -> dict[str, object]:
    context = execution_context(args)
    server_dir = context["server_dir"]
    step2 = completed_stage_result(server_dir, "step2")
    if (
        step2.get("engine_version") != ENGINE_VERSION
        or step2.get("engine_sha256") != ENGINE_SHA256
    ):
        fail("Step2 was produced by a different staged engine; rerun Step2 first")
    _, q2_paths, q2_records = load_q_paths(
        server_dir, "q2", step2["q_rows"], context["sources"]
    )
    step3_consumed = [
        *context["initial_consumed"],
        *step2["accepted_intervals"],
    ]
    step3, _step3_cached = run_step3(
        server_dir,
        context["run_id"],
        context["chromosome_order"],
        q2_paths,
        q2_records,
        step2["q_rows"],
        context["donor_set"],
        context["donor_members"],
        context["assignments"],
        context["sources"],
        context["recipe"]["primary_dataset"],
        step3_consumed,
        context["tools"],
        context["minimap"],
        args.threads,
        args.repair_mode,
        refill_max_length=args.refill_max_length,
        mummer_scope=args.step3_mummer_scope,
        execution_profile=getattr(args, "execution_profile", DEFAULT_EXECUTION_PROFILE),
    )
    reconcile_step2_events_with_step3(step2, step3)
    publish_repair_metadata(
        server_dir, [step2, step3], context["tools"], context["minimap"]
    )
    donor_set = context["donor_set"]
    if step2["donor_set_id"] != donor_set["donor_set_id"] or step3["donor_set_id"] != donor_set["donor_set_id"]:
        fail("Step2/3 do not reference the same frozen donor set as Step1")
    if step2["target_sha256"] != donor_set["fasta_sha256"] or step3["target_sha256"] != donor_set["fasta_sha256"]:
        fail("Step2/3 donor FASTA hash drifted from frozen D0")
    print(
        f"LGZ Step3 complete: run={context['run_id']}, donor_set={donor_set['donor_set_id']}, "
        f"q3_sha256={sha256_file(server_dir / 'grt/q/q3.fa')}"
    )
    return step3
