#!/usr/bin/env python3
"""Project accepted LGZ local alignments into App display coordinates.

The Server audit package keeps synthetic q/flank records and donor-member
coordinates.  This module converts only the exact MUMmer/PAF rows selected by
accepted Final Path operations into original dataset/contig coordinates.  The
desktop App therefore never needs to parse internal LGZ record identities.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


DISPLAY_EVIDENCE_TOOLS = {"mummer", "minimap2"}
DISPLAY_EVIDENCE_ROLES = {"left_anchor", "right_anchor", "spanning_anchor"}
DISPLAY_EVIDENCE_ASSOCIATIONS = {"accepted", "supporting_precursor"}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_events(path: Path) -> dict[str, dict]:
    events: dict[str, dict] = {}
    if not path.is_file():
        return events
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        event = json.loads(raw)
        event_id = str(event.get("event_id", "")).strip()
        if not event_id or event_id in events:
            raise ValueError(f"invalid or duplicate LGZ event at {path}:{line_number}")
        events[event_id] = event
    return events


def _positive_int(value: object, label: str) -> int:
    try:
        result = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _bounded_float(value: object, label: str, minimum: float, maximum: float) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def _flip_orientation(value: str) -> str:
    return "-" if value == "+" else "+"


def _member_source_endpoint(
    member: dict[str, str],
    local_start: int,
    local_end: int,
) -> dict[str, object]:
    member_start = _positive_int(member.get("source_start"), "donor member source_start")
    member_end = _positive_int(member.get("source_end"), "donor member source_end")
    orientation = str(member.get("orientation", ""))
    if orientation not in {"+", "-"} or member_end < member_start:
        raise ValueError("donor member has an invalid interval/orientation")
    member_length = member_end - member_start + 1
    if local_start <= 0 or local_end < local_start or local_end > member_length:
        raise ValueError("selected LGZ alignment exceeds its donor member")
    if orientation == "+":
        source_start = member_start + local_start - 1
        source_end = member_start + local_end - 1
    else:
        source_start = member_end - local_end + 1
        source_end = member_end - local_start + 1
    return {
        "dataset": str(member.get("dataset_name", "")),
        "contig": str(member.get("contig_name", "")),
        "start": source_start,
        "end": source_end,
        "orientation": orientation,
    }


def _project_q_endpoint(
    q_rows: list[dict[str, str]],
    query_start: int,
    query_end: int,
    alignment_orientation: str,
) -> dict[str, object] | None:
    query_min = min(query_start, query_end)
    query_max = max(query_start, query_end)
    candidates = []
    for row in q_rows:
        if row.get("segment_kind") == "gap":
            continue
        q_start = _positive_int(row.get("q_start"), "q segment start")
        q_end = _positive_int(row.get("q_end"), "q segment end")
        if q_start <= query_min and q_end >= query_max:
            candidates.append((row, q_start))
    if len(candidates) != 1:
        return None
    row, q_start = candidates[0]
    source_start = _positive_int(row.get("source_start"), "q source start")
    source_end = _positive_int(row.get("source_end"), "q source end")
    source_orientation = str(row.get("orientation", ""))
    if source_orientation not in {"+", "-"} or source_end < source_start:
        raise ValueError("q segment has an invalid source interval/orientation")
    left_offset = query_min - q_start
    right_offset = query_max - q_start
    if source_orientation == "+":
        projected_start = source_start + left_offset
        projected_end = source_start + right_offset
    else:
        projected_start = source_end - right_offset
        projected_end = source_end - left_offset
    orientation = source_orientation
    if alignment_orientation == "-":
        orientation = _flip_orientation(orientation)
    return {
        "dataset": str(row.get("dataset_name", "")),
        "contig": str(row.get("contig_name", "")),
        "start": projected_start,
        "end": projected_end,
        "orientation": orientation,
    }


def _adjacent_source_endpoint(
    segments: list[dict],
    segment_index: int,
    side: str,
    aligned_span: int,
    alignment_orientation: str,
) -> dict[str, object] | None:
    step = -1 if side == "left" else 1
    index = segment_index + step
    while 0 <= index < len(segments):
        segment = segments[index]
        if segment.get("kind") != "gap" and isinstance(segment.get("source"), dict):
            source = segment["source"]
            source_start = _positive_int(source.get("start"), "Final Path source start")
            source_end = _positive_int(source.get("end"), "Final Path source end")
            source_orientation = str(source.get("orientation", segment.get("orientation", "")))
            if source_orientation not in {"+", "-"} or source_end < source_start:
                raise ValueError("Final Path source has an invalid interval/orientation")
            if source_end - source_start + 1 < aligned_span:
                return None
            if side == "left":
                if source_orientation == "+":
                    projected_start = source_end - aligned_span + 1
                    projected_end = source_end
                else:
                    projected_start = source_start
                    projected_end = source_start + aligned_span - 1
            elif source_orientation == "+":
                projected_start = source_start
                projected_end = source_start + aligned_span - 1
            else:
                projected_start = source_end - aligned_span + 1
                projected_end = source_end
            orientation = source_orientation
            if alignment_orientation == "-":
                orientation = _flip_orientation(orientation)
            return {
                "dataset": str(source.get("dataset", "")),
                "contig": str(source.get("contig", "")),
                "start": projected_start,
                "end": projected_end,
                "orientation": orientation,
            }
        index += step
    return None


def _stable_evidence_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "grt-display-local-" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def _evidence_profile(
    event: dict,
    registry: dict[str, dict[str, str]],
    evidence_types: set[str],
    candidate: dict[str, str],
) -> dict[str, str] | None:
    matches = []
    for evidence_id in event.get("evidence_ids", []):
        row = registry.get(str(evidence_id))
        if row is None or row.get("evidence_type") not in evidence_types:
            continue
        if row.get("source_dataset") != candidate.get("source_dataset"):
            continue
        if row.get("source_contig") != candidate.get("source_contig"):
            continue
        matches.append(row)
    accepted = [row for row in matches if row.get("status") in {"accepted", "superseded"}]
    return (accepted or matches or [None])[0]


def _alignment_payload(
    *,
    final_event: dict,
    supporting_event: dict,
    final_segment_id: str,
    tool: str,
    preset: str,
    role: str,
    aligned_length: int,
    identity: float,
    mapq: int | None,
    source: dict[str, object],
    target: dict[str, object],
) -> dict[str, object]:
    association = (
        "accepted"
        if supporting_event.get("event_id") == final_event.get("event_id")
        else "supporting_precursor"
    )
    payload: dict[str, object] = {
        "event_id": str(final_event.get("event_id", "")),
        "final_path_segment_id": final_segment_id,
        "stage": str(supporting_event.get("stage", "")),
        "action": str(final_event.get("action", "")),
        "association": association,
        "tool": tool,
        "preset": preset,
        "role": role,
        "aligned_length": aligned_length,
        "identity": round(identity, 9),
        "mapq": mapq,
        "source": source,
        "target": target,
    }
    if association == "supporting_precursor":
        payload["supporting_event_id"] = str(supporting_event.get("event_id", ""))
    payload["evidence_id"] = _stable_evidence_id(payload)
    return payload


def _mummer_alignments_for_event(
    *,
    final_event: dict,
    supporting_event: dict,
    final_segment_id: str,
    candidates_by_stage: dict[str, dict[str, dict[str, str]]],
    alignments_by_stage: dict[str, dict[tuple[str, int], dict[str, str]]],
    q_rows: dict[tuple[str, str], list[dict[str, str]]],
    members: dict[str, dict[str, str]],
    registry: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    stage = str(supporting_event.get("stage", ""))
    candidate = candidates_by_stage.get(stage, {}).get(str(supporting_event.get("event_id", "")))
    if candidate is None:
        return []
    if candidate.get("outcome") != "accepted":
        raise ValueError(f"Final Path event {supporting_event.get('event_id')} lacks an accepted candidate")
    member = members.get(str(candidate.get("member_id", "")))
    if member is None:
        raise ValueError(f"LGZ candidate {candidate.get('candidate_id')} references an unknown donor member")
    profile = _evidence_profile(
        supporting_event,
        registry,
        {"mummer_gap_anchor_pair", "mummer_structural_correction"},
        candidate,
    )
    if profile is None:
        raise ValueError(f"LGZ candidate {candidate.get('candidate_id')} lacks linked MUMmer evidence")
    preset = str(profile.get("preset", ""))
    q_version = str(profile.get("q_version", "")) or ("q1" if stage == "step2" else "q2")
    chromosome = str(candidate.get("chr", ""))
    line_roles = [
        (_positive_int(candidate.get("left_line"), "MUMmer left_line"), "left_anchor"),
        (_positive_int(candidate.get("right_line"), "MUMmer right_line"), "right_anchor"),
    ]
    if line_roles[0][0] == line_roles[1][0]:
        line_roles = [(line_roles[0][0], "spanning_anchor")]
    results = []
    for line_number, role in line_roles:
        row = alignments_by_stage.get(stage, {}).get((chromosome, line_number))
        if row is None:
            raise ValueError(
                f"LGZ candidate {candidate.get('candidate_id')} references missing MUMmer line {line_number}"
            )
        if str(row.get("member_id", "")) != str(candidate.get("member_id", "")):
            raise ValueError(
                f"LGZ candidate {candidate.get('candidate_id')} MUMmer line uses another donor member"
            )
        alignment_orientation = str(row.get("orientation", ""))
        if alignment_orientation not in {"+", "-"}:
            raise ValueError("selected MUMmer alignment has an invalid orientation")
        ref_start = _positive_int(row.get("ref_start"), "MUMmer ref_start")
        ref_end = _positive_int(row.get("ref_end"), "MUMmer ref_end")
        query_start = _positive_int(row.get("query_start"), "MUMmer query_start")
        query_end = _positive_int(row.get("query_end"), "MUMmer query_end")
        target = _project_q_endpoint(
            q_rows.get((q_version, chromosome), []),
            query_start,
            query_end,
            alignment_orientation,
        )
        if target is None:
            continue
        source = _member_source_endpoint(member, min(ref_start, ref_end), max(ref_start, ref_end))
        results.append(
            _alignment_payload(
                final_event=final_event,
                supporting_event=supporting_event,
                final_segment_id=final_segment_id,
                tool="mummer",
                preset=preset,
                role=role,
                aligned_length=abs(query_end - query_start) + 1,
                identity=_bounded_float(row.get("identity"), "MUMmer identity", 0.0, 1.0),
                mapq=None,
                source=source,
                target=target,
            )
        )
    return results


def _parse_paf_line(path: Path, line_number: int) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"selected LGZ local PAF is missing: {path}")
    selected = None
    with path.open(encoding="utf-8") as handle:
        for current, raw in enumerate(handle, 1):
            if current == line_number:
                selected = raw.rstrip("\n").split("\t")
                break
    if selected is None or len(selected) < 12:
        raise ValueError(f"selected LGZ local PAF line is invalid: {path}:{line_number}")
    return {
        "query_name": selected[0],
        "query_length": int(selected[1]),
        "query_start0": int(selected[2]),
        "query_end0": int(selected[3]),
        "strand": selected[4],
        "target_name": selected[5],
        "target_start0": int(selected[7]),
        "target_end0": int(selected[8]),
        "matches": int(selected[9]),
        "block_length": int(selected[10]),
        "mapq": int(selected[11]),
    }


def _retained_ancestors(event: dict, events: dict[str, dict]) -> list[dict]:
    """Follow actual retention, which is not the one-to-one supersession edge."""
    ancestors = []
    seen = {str(event.get("event_id", ""))}
    child = event
    while "retained_from_event_id" in child:
        parent_id = child["retained_from_event_id"]
        if not isinstance(parent_id, str) or not parent_id or parent_id in seen:
            raise ValueError("invalid or cyclic retained-source lineage")
        seen.add(parent_id)
        parent = events.get(parent_id)
        if parent is None or parent.get("status") != "superseded":
            raise ValueError(f"retained source has a missing/non-superseded parent: {parent_id}")
        source, original = child.get("source"), parent.get("source")
        if (
            not isinstance(source, dict) or not isinstance(original, dict)
            or child.get("chr") != parent.get("chr")
            or not child.get("source_card_key")
            or child.get("source_card_key") != parent.get("source_card_key")
            or source.get("orientation") not in {"+", "-"}
            or not source.get("dataset") or not source.get("contig")
            or any(source.get(k) != original.get(k) for k in ("dataset", "contig", "orientation"))
            or not (_positive_int(original.get("start"), "retained parent start")
                    <= _positive_int(source.get("start"), "retained child start")
                    <= _positive_int(source.get("end"), "retained child end")
                    <= _positive_int(original.get("end"), "retained parent end"))
            or not isinstance(parent.get("retained_event_ids"), list)
            or child.get("event_id") not in parent["retained_event_ids"]
        ):
            raise ValueError(f"retained source disagrees with its original parent: {parent_id}")
        ancestors.append(parent)
        child = parent
    return ancestors


def _verified_display_artifact(source_root: Path, relative: object, digest: object, cache: dict) -> Path:
    if not isinstance(relative, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("local evidence has an incomplete artifact identity")
    path = (source_root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(source_root.resolve()):
        raise ValueError("display evidence artifact escapes the Server workspace")
    stat = path.stat()
    key = ("verified", path, digest, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if key not in cache:
        actual = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                actual.update(chunk)
        if actual.hexdigest() != digest:
            raise ValueError("display evidence artifact checksum mismatch")
        cache[key] = True
    return path


def _flank_projection(source_root: Path, profile: dict, cache: dict) -> dict | None:
    parameters = json.loads(profile.get("parameters_json") or "{}")
    if not isinstance(parameters, dict):
        raise ValueError("local evidence parameters must be an object")
    relative = parameters.get("flank_projection_relpath")
    digest = parameters.get("flank_projection_sha256")
    if relative is None and digest is None:
        return None  # Legacy accepted events can still use their current neighbours.
    path = _verified_display_artifact(source_root, relative, digest, cache)
    for path_field, hash_field in (("query_artifact_relpath", "query_sha256"),
                                   ("raw_artifact_relpath", "raw_artifact_sha256")):
        _verified_display_artifact(source_root, profile.get(path_field), profile.get(hash_field), cache)
    key = ("projection", path, digest)
    if key not in cache:
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, dict) or payload.get("schema_version") != "grt_refill_flank_projection_v1":
            raise ValueError("unsupported refill flank projection")
        q_length = _positive_int(payload.get("q_length"), "working query length")
        rows = payload.get("working_q_rows")
        queries = payload.get("queries")
        if not isinstance(rows, list) or not isinstance(queries, dict):
            raise ValueError("flank projection lacks working path/queries")
        cursor = 1
        for row in rows:
            if not isinstance(row, dict) or row.get("chr") != payload.get("chr"):
                raise ValueError("flank projection chromosome disagrees with its path")
            start = _positive_int(row.get("q_start"), "working segment start")
            end = _positive_int(row.get("q_end"), "working segment end")
            if start != cursor or end < start:
                raise ValueError("flank projection path is not contiguous")
            if row.get("segment_kind") not in {"source", "gap"}:
                raise ValueError("flank projection has an invalid segment kind")
            if row.get("segment_kind") != "gap":
                source_start = _positive_int(row.get("source_start"), "working source start")
                source_end = _positive_int(row.get("source_end"), "working source end")
                if source_end - source_start != end - start or row.get("orientation") not in {"+", "-"}:
                    raise ValueError("flank projection has inconsistent source interval/orientation")
            cursor = end + 1
        if cursor != q_length + 1:
            raise ValueError("flank projection path length mismatch")
        for name, query in queries.items():
            if not isinstance(query, dict) or not name:
                raise ValueError("invalid flank query projection")
            start = _positive_int(query.get("q_start"), "flank query start")
            end = _positive_int(query.get("q_end"), "flank query end")
            if not start <= end <= q_length:
                raise ValueError("flank query exceeds its working path")
        cache[key] = payload
    payload = cache[key]
    if not profile.get("query_sha256") or payload.get("query_sha256") != profile["query_sha256"]:
        raise ValueError("flank projection belongs to another query artifact")
    return payload


def _local_alignments_for_event(
    *,
    source_root: Path,
    final_event: dict,
    supporting_event: dict,
    projection_cache: dict,
    final_segment_id: str,
    segments: list[dict],
    segment_index: int,
    refill_candidates: dict[str, dict[str, str]],
    members: dict[str, dict[str, str]],
    registry: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    historical = supporting_event.get("event_id") != final_event.get("event_id")
    candidate = refill_candidates.get(str(supporting_event.get("event_id", "")))
    if candidate is None:
        if historical:
            raise ValueError("retained refill lacks its original candidate; rerun run_all.sh to regenerate Step3 evidence")
        return []
    if candidate.get("outcome") != "accepted":
        raise ValueError(f"Final Path event {final_event.get('event_id')} lacks an accepted refill candidate")
    member = members.get(str(candidate.get("member_id", "")))
    if member is None:
        raise ValueError(f"LGZ refill {candidate.get('candidate_id')} references an unknown donor member")
    profile = _evidence_profile(
        supporting_event,
        registry,
        {"corrected_gap_flank_refill", "post_filter_gap_flank_refill"},
        candidate,
    )
    if profile is None:
        raise ValueError(f"LGZ refill {candidate.get('candidate_id')} lacks accepted local evidence")
    projection = _flank_projection(source_root, profile, projection_cache)
    if historical and projection is None:
        raise ValueError("retained refill lacks immutable flank projection; rerun run_all.sh to regenerate Step3 evidence")
    if projection is not None and projection.get("chr") != candidate.get("chr"):
        raise ValueError("refill flank projection belongs to another chromosome")
    paf_path = source_root / str(profile.get("raw_artifact_relpath", ""))
    results = []
    for side, role, field in (
        ("left", "left_anchor", "left_line"),
        ("right", "right_anchor", "right_line"),
    ):
        line_number = _positive_int(candidate.get(field), f"refill {field}")
        paf = _parse_paf_line(paf_path, line_number)
        strand = str(paf["strand"])
        if strand not in {"+", "-"}:
            raise ValueError("selected LGZ local PAF has an invalid strand")
        query_name = str(paf["query_name"])
        expected_name = f"flank__{candidate.get('object_id', '')}__{'L' if side == 'left' else 'R'}"
        if query_name != expected_name:
            raise ValueError(
                f"LGZ refill {candidate.get('candidate_id')} {field} does not reference the {side} flank"
            )
        if str(paf["target_name"]) != str(member.get("fasta_record_name", "")):
            raise ValueError(
                f"LGZ refill {candidate.get('candidate_id')} {field} uses another donor member"
            )
        aligned_span = int(paf["query_end0"]) - int(paf["query_start0"])
        block_length = int(paf["block_length"])
        matches = int(paf["matches"])
        if aligned_span <= 0 or block_length <= 0 or matches < 0 or matches > block_length:
            raise ValueError("selected LGZ local PAF has invalid alignment lengths")
        if not (0 <= int(paf["query_start0"]) < int(paf["query_end0"]) <= int(paf["query_length"])):
            raise ValueError("selected LGZ local PAF exceeds its query")
        if projection is None:
            target = _adjacent_source_endpoint(
                segments, segment_index, side, aligned_span, strand,
            )
        else:
            query = projection["queries"].get(query_name)
            if query is None or int(query["q_end"]) - int(query["q_start"]) + 1 != int(paf["query_length"]):
                raise ValueError("selected refill PAF disagrees with its frozen flank query")
            target = _project_q_endpoint(
                projection["working_q_rows"],
                int(query["q_start"]) + int(paf["query_start0"]),
                int(query["q_start"]) + int(paf["query_end0"]) - 1,
                strand,
            )
        if target is None:
            continue
        source = _member_source_endpoint(
            member,
            int(paf["target_start0"]) + 1,
            int(paf["target_end0"]),
        )
        results.append(
            _alignment_payload(
                final_event=final_event,
                supporting_event=supporting_event,
                final_segment_id=final_segment_id,
                tool="minimap2",
                preset=str(profile.get("preset", "")),
                role=role,
                aligned_length=block_length,
                identity=matches / block_length,
                mapq=int(paf["mapq"]),
                source=source,
                target=target,
            )
        )
    return results


def _endpoint_source_card(
    endpoint: object,
    label: str,
    chromosome: str,
    source_lengths: dict[tuple[str, str], int],
) -> tuple[str, str, str]:
    if not isinstance(endpoint, dict):
        raise ValueError(f"{label} must be an object")
    dataset = str(endpoint.get("dataset", "")).strip()
    contig = str(endpoint.get("contig", "")).strip()
    start = _positive_int(endpoint.get("start"), f"{label}.start")
    end = _positive_int(endpoint.get("end"), f"{label}.end")
    orientation = str(endpoint.get("orientation", ""))
    source_length = source_lengths.get((dataset, contig))
    if (
        not dataset
        or not contig
        or end < start
        or source_length is None
        or end > source_length
        or orientation not in {"+", "-"}
    ):
        raise ValueError(f"{label} has an invalid display source interval")
    return dataset, contig, chromosome


def _validate_endpoint(
    endpoint: object,
    label: str,
    chromosome: str,
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> None:
    card = _endpoint_source_card(endpoint, label, chromosome, source_lengths)
    if card not in display_source_cards:
        dataset, contig, _chromosome = card
        raise ValueError(f"{label} has no App display source card for {dataset}:{contig}:{chromosome}")


def _renderable_supporting_evidence(
    item: dict[str, object],
    chromosome: str,
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> bool:
    """Return whether an optional precursor has both App endpoint cards."""
    evidence_id = str(item.get("evidence_id", "")).strip() or "<empty>"
    source_card = _endpoint_source_card(
        item.get("source"),
        f"display evidence {evidence_id}.source",
        chromosome,
        source_lengths,
    )
    target_card = _endpoint_source_card(
        item.get("target"),
        f"display evidence {evidence_id}.target",
        chromosome,
        source_lengths,
    )
    return source_card in display_source_cards and target_card in display_source_cards


def validate_display_evidence(
    *,
    chromosome: str,
    evidence: list[dict[str, object]],
    final_segment_events: dict[str, str],
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> None:
    evidence_ids: set[str] = set()
    for item in evidence:
        evidence_id = str(item.get("evidence_id", "")).strip()
        event_id = str(item.get("event_id", "")).strip()
        segment_id = str(item.get("final_path_segment_id", "")).strip()
        if not evidence_id or evidence_id in evidence_ids:
            raise ValueError(f"invalid or duplicate display evidence_id: {evidence_id or '<empty>'}")
        evidence_ids.add(evidence_id)
        if not event_id or final_segment_events.get(segment_id) != event_id:
            raise ValueError(f"display evidence {evidence_id} has a dangling Final Path event/segment")
        if item.get("tool") not in DISPLAY_EVIDENCE_TOOLS:
            raise ValueError(f"display evidence {evidence_id} has an invalid tool")
        if item.get("role") not in DISPLAY_EVIDENCE_ROLES:
            raise ValueError(f"display evidence {evidence_id} has an invalid role")
        if item.get("association") not in DISPLAY_EVIDENCE_ASSOCIATIONS:
            raise ValueError(f"display evidence {evidence_id} has an invalid association")
        _positive_int(item.get("aligned_length"), f"display evidence {evidence_id}.aligned_length")
        _bounded_float(item.get("identity"), f"display evidence {evidence_id}.identity", 0.0, 1.0)
        mapq = item.get("mapq")
        if mapq is not None and (not isinstance(mapq, int) or isinstance(mapq, bool) or not 0 <= mapq <= 255):
            raise ValueError(f"display evidence {evidence_id}.mapq must be null or 0..255")
        _validate_endpoint(
            item.get("source"),
            f"display evidence {evidence_id}.source",
            chromosome,
            source_lengths,
            display_source_cards,
        )
        _validate_endpoint(
            item.get("target"),
            f"display evidence {evidence_id}.target",
            chromosome,
            source_lengths,
            display_source_cards,
        )


def _candidates_by_event(path: Path) -> dict[str, dict[str, str]]:
    """Select the accepted candidate when an event has competing candidates."""
    result: dict[str, dict[str, str]] = {}
    for row in _read_tsv(path):
        event_id = row.get("event_id", "")
        if not event_id:
            continue
        previous = result.get(event_id)
        if previous is None:
            result[event_id] = row
        elif row.get("outcome") == "accepted":
            if previous.get("outcome") == "accepted":
                raise ValueError(f"LGZ event {event_id} has multiple accepted candidates in {path}")
            result[event_id] = row
    return result


def build_display_evidence(
    source_root: Path,
    final_path: dict,
    source_lengths: dict[tuple[str, str], int],
    display_source_cards: set[tuple[str, str, str]],
) -> dict[str, list[dict[str, object]]]:
    """Return accepted, display-ready local evidence grouped by chromosome."""

    events = _read_events(source_root / "metadata/grt_events.jsonl")
    members = {
        row["member_id"]: row
        for row in _read_tsv(source_root / "metadata/grt_donor_members.tsv")
    }
    registry = {
        row["evidence_id"]: row
        for row in _read_tsv(source_root / "metadata/grt_evidence_registry.tsv")
    }
    q_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in _read_tsv(source_root / "metadata/grt_q_segments.tsv"):
        q_rows[(row.get("q_version", ""), row.get("chr", ""))].append(row)

    candidates_by_stage: dict[str, dict[str, dict[str, str]]] = {}
    for stage, relpath in (
        ("step2", "grt/evidence/step2/candidates.tsv"),
        ("step3", "grt/evidence/step3/correction_candidates.tsv"),
    ):
        candidates_by_stage[stage] = _candidates_by_event(source_root / relpath)
    refill_candidates = _candidates_by_event(
        source_root / "grt/evidence/step3/refill_candidates.tsv"
    )
    alignments_by_stage: dict[str, dict[tuple[str, int], dict[str, str]]] = {}
    for stage in ("step2", "step3"):
        alignments_by_stage[stage] = {
            (row.get("chr", ""), int(row["line_number"])): row
            for row in _read_tsv(source_root / f"grt/evidence/{stage}/mummer/alignments.tsv")
        }

    result: dict[str, list[dict[str, object]]] = {}
    projection_cache: dict = {}
    for chromosome in final_path.get("chromosomes", []):
        chromosome_name = str(chromosome.get("chr", ""))
        segments = chromosome.get("segments", [])
        if not chromosome_name or not isinstance(segments, list):
            continue
        final_segment_events = {
            str(segment.get("segment_id", "")): str(segment.get("event_id", ""))
            for segment in segments
            if isinstance(segment, dict) and segment.get("event_id") not in {None, ""}
        }
        projected: list[dict[str, object]] = []
        for segment_index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            final_segment_id = str(segment.get("segment_id", ""))
            raw_final_event_id = segment.get("event_id")
            if raw_final_event_id in {None, ""}:
                continue
            final_event_id = str(raw_final_event_id)
            final_event = events.get(final_event_id)
            if final_event is None or final_event.get("status") != "accepted":
                raise ValueError(f"Final Path segment {final_segment_id} references a non-accepted event")
            if str(final_event.get("chr", "")) != chromosome_name:
                raise ValueError(f"Final Path event {final_event_id} chromosome does not match")

            retained_ancestors = _retained_ancestors(final_event, events)
            supporting_events = [final_event, *retained_ancestors]
            supporting_ids = {event["event_id"] for event in supporting_events}
            for supporting_id in final_event.get("superseded_event_ids", []):
                supporting = events.get(str(supporting_id))
                if supporting is None:
                    raise ValueError(f"Final Path event {final_event_id} has a dangling precursor event")
                if supporting_id not in supporting_ids:
                    supporting_events.append(supporting)
                    supporting_ids.add(supporting_id)
            for supporting_event in supporting_events:
                if str(supporting_event.get("stage", "")) in {"step2", "step3"}:
                    projected.extend(
                        _mummer_alignments_for_event(
                            final_event=final_event,
                            supporting_event=supporting_event,
                            final_segment_id=final_segment_id,
                            candidates_by_stage=candidates_by_stage,
                            alignments_by_stage=alignments_by_stage,
                            q_rows=q_rows,
                            members=members,
                            registry=registry,
                        )
                    )
            for local_event in [final_event, *retained_ancestors]:
                if local_event.get("stage") == "step3" and local_event.get("action") == "refill":
                    projected.extend(
                        _local_alignments_for_event(
                            source_root=source_root,
                            final_event=final_event,
                            supporting_event=local_event,
                            projection_cache=projection_cache,
                            final_segment_id=final_segment_id,
                            segments=segments,
                            segment_index=segment_index,
                            refill_candidates=refill_candidates,
                            members=members,
                            registry=registry,
                        )
                    )
        projected.sort(key=lambda item: str(item["evidence_id"]))
        validation_cards = set(display_source_cards)
        for item in projected:
            if item.get("association") != "supporting_precursor":
                continue
            evidence_id = str(item.get("evidence_id", "")).strip() or "<empty>"
            validation_cards.add(
                _endpoint_source_card(
                    item.get("source"),
                    f"display evidence {evidence_id}.source",
                    chromosome_name,
                    source_lengths,
                )
            )
            validation_cards.add(
                _endpoint_source_card(
                    item.get("target"),
                    f"display evidence {evidence_id}.target",
                    chromosome_name,
                    source_lengths,
                )
            )
        validate_display_evidence(
            chromosome=chromosome_name,
            evidence=projected,
            final_segment_events=final_segment_events,
            source_lengths=source_lengths,
            display_source_cards=validation_cards,
        )
        projected = [
            item
            for item in projected
            if item.get("association") != "supporting_precursor"
            or _renderable_supporting_evidence(
                item,
                chromosome_name,
                source_lengths,
                display_source_cards,
            )
        ]
        validate_display_evidence(
            chromosome=chromosome_name,
            evidence=projected,
            final_segment_events=final_segment_events,
            source_lengths=source_lengths,
            display_source_cards=display_source_cards,
        )
        result[chromosome_name] = projected
    return result
