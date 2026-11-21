"""Build a sourced Final Path from normalized, admitted post-LGZ edits.

This module is the sequence/provenance boundary, not a native-tool admission
policy. Adapters must first explain candidate edits against the frozen baseline.
Coordinates for edits and output placement are 0-based half-open; source intervals
retain the App/Server convention (1-based inclusive). Sequence access is bounded.
No native whole-genome FASTA is substituted for a reconstructed Final Path.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Protocol

BLOCK = 1024 * 1024
SCHEMA = "cgat.refined-final-path"
VERSION = 1
COMPLEMENT = bytes.maketrans(b"ACGTRYSWKMBDHVN", b"TGCAYRSWMKVHDBN")
TOOLS = {"degap", "tgsgapcloser", "quartet", "lrgapcloser"}


class PathError(ValueError):
    pass


class Catalog(Protocol):
    def length(self, dataset: str, contig: str) -> int: ...
    def fetch(self, dataset: str, contig: str, start: int, end: int) -> bytes: ...


@dataclass(frozen=True)
class Gap:
    gap_id: str
    chromosome: str
    start: int
    end: int


@dataclass(frozen=True)
class Edit:
    edit_id: str
    tool: str
    chromosome: str
    start: int
    end: int
    replacement: dict | None
    gap_ids: tuple[str, ...]
    native_job: str
    evidence: dict


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def integer(value, *, minimum=0) -> bool:
    return type(value) is int and value >= minimum


def checked_source(source: dict, catalog: Catalog) -> int:
    if not isinstance(source, dict):
        raise PathError("missing segment source")
    dataset, contig = source.get("dataset"), source.get("contig")
    start, end = source.get("start"), source.get("end")
    if (not isinstance(dataset, str) or not dataset or not isinstance(contig, str) or not contig
            or not integer(start, minimum=1) or not integer(end, minimum=1) or end < start
            or source.get("orientation") not in {"+", "-"}):
        raise PathError("invalid source interval")
    if end > catalog.length(dataset, contig):
        raise PathError(f"source interval outside {dataset}:{contig}")
    return end - start + 1


def source_blocks(source: dict, catalog: Catalog) -> Iterable[bytes]:
    checked_source(source, catalog)
    start, end = source["start"] - 1, source["end"]
    if source["orientation"] == "+":
        intervals = ((left, min(end, left + BLOCK)) for left in range(start, end, BLOCK))
    else:
        intervals = ((max(start, right - BLOCK), right) for right in range(end, start, -BLOCK))
    for left, right in intervals:
        sequence = catalog.fetch(source["dataset"], source["contig"], left, right).upper()
        if len(sequence) != right - left or re.search(br"[^ACGTRYSWKMBDHVN]", sequence):
            raise PathError("source sequence is incomplete or not IUPAC DNA")
        yield sequence if source["orientation"] == "+" else sequence.translate(COMPLEMENT)[::-1]


def segment_blocks(segment: dict, catalog: Catalog) -> Iterable[bytes]:
    length = segment.get("length")
    if not integer(length, minimum=1):
        raise PathError("invalid path segment length")
    if segment.get("kind") == "gap":
        # New partially filled segments retain the native N sequence as origin.
        origin = segment.get("refinement_source")
        if origin is not None:
            if checked_source(origin, catalog) != length:
                raise PathError("gap origin length mismatch")
            for block in source_blocks(origin, catalog):
                if block.strip(b"N"):
                    raise PathError("gap origin contains non-N bases")
                yield block
        else:
            for offset in range(0, length, BLOCK):
                yield b"N" * min(BLOCK, length - offset)
        return
    if segment.get("kind") not in {"source", "patch", "telomere"}:
        raise PathError("unsupported path segment kind")
    source = segment.get("source")
    if checked_source(source, catalog) != length or segment.get("orientation") != source["orientation"]:
        raise PathError("path/source length or orientation mismatch")
    yield from source_blocks(source, catalog)


def slice_source(source: dict, left: int, right: int) -> dict:
    result = copy.deepcopy(source)
    if source["orientation"] == "+":
        result["start"], result["end"] = source["start"] + left, source["start"] + right - 1
    else:
        result["start"], result["end"] = source["end"] - right + 1, source["end"] - left
    return result


def slice_segment(segment: dict, left: int, right: int) -> dict:
    if not 0 <= left < right <= segment["length"]:
        raise PathError("invalid path slice")
    result = copy.deepcopy(segment)
    result.pop("output_start", None)
    result.pop("output_end", None)
    if left == 0 and right == segment["length"]:
        return result
    parent = segment["segment_id"]
    result["segment_id"] = "retained-" + identity([parent, left, right])[:24]
    result["parent_segment_id"] = parent
    result["parent_interval"] = [left, right]
    result["length"] = right - left
    if segment.get("kind") != "gap":
        result["source"] = slice_source(segment["source"], left, right)
    if segment.get("refinement_source"):
        result["refinement_source"] = slice_source(segment["refinement_source"], left, right)
    return result


def path_slice(segments: list[dict], start: int, end: int) -> list[dict]:
    result, cursor = [], 0
    for segment in segments:
        stop = cursor + segment["length"]
        left, right = max(start, cursor), min(end, stop)
        if left < right:
            result.append(slice_segment(segment, left - cursor, right - cursor))
        cursor = stop
        if cursor >= end:
            break
    if sum(row["length"] for row in result) != end - start:
        raise PathError("path slice exceeds baseline")
    return result


def inspect_baseline(payload: dict, catalog: Catalog) -> tuple[list[Gap], dict[str, dict]]:
    """Validate original path checksums; find maximal N runs across segment edges."""
    if payload.get("workflow") != "gpm_grt_precomputed_v2" or str(payload.get("schema_version")) != "1":
        raise PathError("unsupported LGZ baseline Final Path")
    chromosomes = payload.get("chromosomes")
    if not isinstance(chromosomes, list) or not chromosomes:
        raise PathError("empty LGZ baseline")
    records, gaps, seen_segments = {}, [], set()
    for chromosome in chromosomes:
        name = chromosome.get("chr")
        if not isinstance(name, str) or not name or re.search(r"\s|[\x00-\x1f\x7f]", name) or name in records:
            raise PathError("invalid or duplicate chromosome name")
        segments = chromosome.get("segments")
        if not isinstance(segments, list) or not segments:
            raise PathError("empty baseline path")
        offset, pending, digest, intervals = 0, None, hashlib.sha256(), []
        for segment in segments:
            sid = segment.get("segment_id")
            if not isinstance(sid, str) or not sid or sid in seen_segments:
                raise PathError("invalid or duplicate segment identity")
            seen_segments.add(sid)
            for block in segment_blocks(segment, catalog):
                digest.update(block)
                for match in re.finditer(br"N+", block):
                    start, end = offset + match.start(), offset + match.end()
                    if pending is not None and pending[1] == start:
                        pending = (pending[0], end)
                    else:
                        if pending is not None:
                            intervals.append(pending)
                        pending = (start, end)
                offset += len(block)
                if pending is not None and pending[1] < offset:
                    intervals.append(pending)
                    pending = None
        if pending is not None:
            intervals.append(pending)
        sha256 = digest.hexdigest()
        if (not integer(chromosome.get("q4_length"), minimum=1)
                or chromosome["q4_length"] != offset or chromosome.get("q4_sha256") != sha256):
            raise PathError(f"baseline source reconstruction mismatch: {name}")
        records[name] = {"length": offset, "sha256": sha256, "segments": segments}
        for start, end in intervals:
            gaps.append(Gap("gap-" + identity([name, sha256, start, end])[:24], name, start, end))
    return gaps, records


def replacement_segments(edit: Edit, catalog: Catalog) -> list[dict]:
    if edit.replacement is None:
        return []  # A justified overlap closure can remove sequence without a bridge.
    checked_source(edit.replacement, catalog)
    # Coalesce runs across I/O boundaries, not across original distinct edits.
    runs, cursor = [], 0
    for block in source_blocks(edit.replacement, catalog):
        for match in re.finditer(br"N+|[^N]+", block):
            kind = "gap" if match[0].startswith(b"N") else "patch"
            left, right = cursor + match.start(), cursor + match.end()
            if runs and runs[-1][0] == kind:
                runs[-1] = (kind, runs[-1][1], right)
            else:
                runs.append((kind, left, right))
        cursor += len(block)
    result = []
    for kind, left, right in runs:
        source = slice_source(edit.replacement, left, right)
        segment = {"segment_id": "refined-" + identity([edit.tool, edit.edit_id, left, right])[:24],
                   "kind": kind, "length": right - left, "orientation": source["orientation"],
                   "refinement_edit_id": edit.edit_id, "original_gap_ids": list(edit.gap_ids)}
        segment["refinement_source" if kind == "gap" else "source"] = source
        result.append(segment)
    return result


def build_final_path(baseline: dict, catalog: Catalog, edits: list[Edit], *, tool: str,
                     recipe_sha256: str, baseline_artifact_sha256: str) -> dict:
    """Project admitted replacements, preserving retained sources and direction.

    Does NOT declare biological correctness or native success. An execution receipt
    must separately attest that the chosen tool finished, including zero-edit runs.
    """
    if tool not in TOOLS or any(not re.fullmatch(r"[0-9a-f]{64}", value)
                                for value in (recipe_sha256, baseline_artifact_sha256)):
        raise PathError("invalid tool or baseline/recipe identity")
    gaps, records = inspect_baseline(baseline, catalog)
    grouped, edit_ids = {name: [] for name in records}, set()
    for edit in edits:
        if (not isinstance(edit.edit_id, str) or not edit.edit_id or edit.edit_id in edit_ids
                or edit.tool != tool or edit.chromosome not in records
                or not integer(edit.start) or not integer(edit.end) or edit.start >= edit.end
                or edit.end > records[edit.chromosome]["length"] or not edit.native_job
                or not isinstance(edit.evidence, dict) or not edit.evidence):
            raise PathError("invalid normalized refinement edit")
        affected = tuple(gap.gap_id for gap in gaps if gap.chromosome == edit.chromosome
                         and gap.start < edit.end and edit.start < gap.end)
        if not affected or len(edit.gap_ids) != len(set(edit.gap_ids)) or set(affected) != set(edit.gap_ids):
            raise PathError("edit must name every original gap it intersects")
        grouped[edit.chromosome].append(edit)
        edit_ids.add(edit.edit_id)
    final = {"schema": SCHEMA, "schema_version": VERSION, "tool": tool,
             "coordinate_system": "0-based half-open placement; 1-based inclusive sources",
             "baseline": {"final_path_sha256": identity(baseline), "assembly_sha256": baseline_artifact_sha256},
             "recipe_sha256": recipe_sha256, "original_gaps": [asdict(gap) for gap in gaps],
             "edits": [], "chromosomes": []}
    all_segment_ids = set()
    for name, record in records.items():
        cursor, output_cursor, segments, lifts = 0, 0, [], []
        for edit in sorted(grouped[name], key=lambda row: (row.start, row.end, row.edit_id)):
            if edit.start < cursor:
                raise PathError("overlapping refinement edits require explicit joint normalization")
            retained = path_slice(record["segments"], cursor, edit.start)
            segments.extend(retained)
            retained_length = edit.start - cursor
            if retained_length:
                lifts.append({"kind": "retained", "baseline_start": cursor, "baseline_end": edit.start,
                              "output_start": output_cursor, "output_end": output_cursor + retained_length})
            output_cursor += retained_length
            replacements = replacement_segments(edit, catalog)
            length = sum(row["length"] for row in replacements)
            segments.extend(replacements)
            lifts.append({"kind": "replacement", "edit_id": edit.edit_id, "baseline_start": edit.start,
                          "baseline_end": edit.end, "output_start": output_cursor, "output_end": output_cursor + length})
            final["edits"].append({**asdict(edit), "output_start": output_cursor, "output_end": output_cursor + length,
                                   "replacement_segment_ids": [row["segment_id"] for row in replacements]})
            output_cursor += length
            cursor = edit.end
        tail = path_slice(record["segments"], cursor, record["length"])
        segments.extend(tail)
        if cursor < record["length"]:
            lifts.append({"kind": "retained", "baseline_start": cursor, "baseline_end": record["length"],
                          "output_start": output_cursor, "output_end": output_cursor + record["length"] - cursor})
        if not segments:
            raise PathError("refinement cannot remove an entire chromosome")
        length, sha256 = 0, hashlib.sha256()
        for segment in segments:
            if segment["segment_id"] in all_segment_ids:
                raise PathError("duplicate output segment identity")
            all_segment_ids.add(segment["segment_id"])
            segment["output_start"] = length
            for block in segment_blocks(segment, catalog):
                sha256.update(block)
                length += len(block)
            segment["output_end"] = length
        final["chromosomes"].append({"chr": name, "length": length, "sha256": sha256.hexdigest(),
                                     "segments": segments, "coordinate_lift": lifts})
    return final


def write_assembly(final_path: dict, catalog: Catalog, destination: Path) -> None:
    """Write only reconstructed path sequence; caller atomically publishes staging."""
    if final_path.get("schema") != SCHEMA or final_path.get("schema_version") != VERSION:
        raise PathError("unsupported refined Final Path")
    # Exclusive creation ensures this function cannot overwrite a previous result.
    with destination.open("xb") as stream:
        for chromosome in final_path["chromosomes"]:
            name = chromosome["chr"]
            if not name or re.search(r"\s|[\x00-\x1f\x7f]", name):
                raise PathError("invalid chromosome name")
            stream.write(b">" + name.encode("utf-8") + b"\n")
            length, sha256 = 0, hashlib.sha256()
            for segment in chromosome["segments"]:
                if segment.get("output_start") != length:
                    raise PathError("Final Path output coordinates are not contiguous")
                for block in segment_blocks(segment, catalog):
                    stream.write(block)
                    length += len(block)
                    sha256.update(block)
                if segment.get("output_end") != length:
                    raise PathError("Final Path segment output length mismatch")
            stream.write(b"\n")
            if length != chromosome["length"] or sha256.hexdigest() != chromosome["sha256"]:
                raise PathError("Final Path changed during reconstruction")


def lift_interval(chromosome: dict, start: int, end: int) -> tuple[int, int] | None:
    """Lift unchanged coordinate evidence; return None if any changed bases intersect.

    Consumers must rebuild/invalidate crossing annotations/alignments, never ship
    old coordinates under a new assembly identity. Coordinates are half-open.
    """
    if not integer(start) or not integer(end) or end <= start:
        raise PathError("invalid interval for coordinate lift")
    for interval in chromosome["coordinate_lift"]:
        if (interval["kind"] == "retained" and interval["baseline_start"] <= start
                and end <= interval["baseline_end"]):
            delta = interval["output_start"] - interval["baseline_start"]
            return start + delta, end + delta
    return None


def remaining_gaps(final_path: dict, catalog: Catalog) -> list[dict]:
    """Scan actual final sequence, retaining the original gap denominator/identity.

    A joint edit may not identify which original gap contains residual Ns. Keep
    all associated IDs in that case rather than invent a one-to-one attribution.
    """
    results = []
    originals = final_path["original_gaps"]
    for chromosome in final_path["chromosomes"]:
        cursor, pending, intervals = 0, None, []
        for segment in chromosome["segments"]:
            for block in segment_blocks(segment, catalog):
                for match in re.finditer(br"N+", block):
                    start, end = cursor + match.start(), cursor + match.end()
                    if pending and pending[1] == start:
                        pending = (pending[0], end)
                    else:
                        if pending:
                            intervals.append(pending)
                        pending = (start, end)
                cursor += len(block)
                if pending and pending[1] < cursor:
                    intervals.append(pending)
                    pending = None
        if pending:
            intervals.append(pending)
        for start, end in intervals:
            original_ids = set()
            for lift in chromosome["coordinate_lift"]:
                if not (start < lift["output_end"] and lift["output_start"] < end):
                    continue
                if lift["kind"] == "replacement":
                    edit = next(e for e in final_path["edits"] if e["edit_id"] == lift["edit_id"])
                    original_ids.update(edit["gap_ids"])
                else:
                    delta = lift["output_start"] - lift["baseline_start"]
                    a, b = max(start, lift["output_start"]) - delta, min(end, lift["output_end"]) - delta
                    original_ids.update(gap["gap_id"] for gap in originals if gap["chromosome"] == chromosome["chr"]
                                        and a < gap["end"] and gap["start"] < b)
            results.append({"chromosome": chromosome["chr"], "start": start, "end": end,
                            "original_gap_ids": sorted(original_ids),
                            "attribution": "joint" if len(original_ids) > 1 else "single" if original_ids else "new"})
    return results
