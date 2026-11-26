"""Local q0 geometry from the exact selection already verified at the reported stage.

All coordinates here are 0-based half-open. No alignment, filesystem discovery,
FASTA synthesis or re-use of coordinates from an unrelated stage is permitted.
"""
from __future__ import annotations

import json

from report_inventory import SHA, physical
from run_orchestration import file_signature, sha256_file
from lgz_core.q0_publication import SELECTION, SELECTION_SCHEMA


def label(value):
    if not isinstance(value, str) or not 0 < len(value) <= 255 or any(c in value for c in "/\\\r\t\n\0"):
        raise ValueError("invalid path track label")
    return value


def interval(row):
    a, b = row["start"], row["end"]
    if type(a) is not int or type(b) is not int or not 0 <= a < b:
        raise ValueError("invalid path interval")
    return a, b


def references(stats):
    result = {}
    for row in stats.get("sequences", []):
        chrom = label(row["sequence"])
        length = row["length_bp"]
        if chrom in result or type(length) is not int or length < 0:
            raise ValueError("invalid reference length or duplicate name")
        gaps = row.get("gap_intervals", [] if row.get("gap_count") == 0 else None)
        if gaps is not None:
            end, total = -1, 0
            for a, b in gaps:
                if not (type(a) is int and type(b) is int and end < a and b - a >= 100 and b <= length):
                    raise ValueError("invalid reference gap positions")
                end, total = b, total + b - a
            if total != row["gap_bp"] or len(gaps) != row["gap_count"]:
                raise ValueError("reference gap inventory mismatch")
        result[chrom] = {"length_bp": length, "gaps": gaps}
    return result


def project(construction, refs, sizes=None):
    if construction["schema"] != "lgz_q0_construction_v1":
        raise ValueError("unknown q0 construction")
    placements = {p["placement_id"]: p for p in construction["placements"]}
    if len(placements) != len(construction["placements"]):
        raise ValueError("duplicate q0 placement")
    by_chr = {r["chromosome"]: r["status"] for r in construction["chromosomes"]}
    if len(by_chr) != len(construction["chromosomes"]) or by_chr.keys() != construction["searches"].keys():
        raise ValueError("incomplete q0 chromosome inventory")
    result = []
    for chrom in dict.fromkeys([*refs, *by_chr]):
        label(chrom)
        ref = refs.get(chrom)
        status = by_chr.get(chrom)
        path = construction["searches"][chrom]["path"] if status else None
        if status not in (None, "partial_path", "not_constructed") or (status == "partial_path") != (path is not None):
            raise ValueError("inconsistent q0 path status")
        track = {"chr": chrom, "ref": ref, "status": status, "length_bp": None, "parts": [], "bands": []}
        result.append(track)
        if path is None:
            if sizes and chrom in sizes:
                raise ValueError("unexpected q0 FASTA record")
            continue
        slices, joins = path["slices"], path["joins"]
        if path["chromosome"] != chrom or not slices or len(joins) + 1 != len(slices):
            raise ValueError("invalid q0 slice order")
        cursor = 0
        for i, piece in enumerate(slices):
            p = placements[piece["placement_id"]]
            lo, hi = interval(piece["interval"])
            start, end = interval(p["interval"])
            strand = piece["orientation"]
            if (p["chromosome"] != chrom or p["source"] != piece["source"] or p["orientation"] != strand
                    or strand not in ("+", "-") or not start <= lo < hi <= end):
                raise ValueError("selected slice disagrees with q0 placement")
            dataset, name = (label(p["source"][k]) for k in ("dataset", "contig"))
            track["parts"].append({"start": cursor, "end": cursor + hi-lo, "kind": "source", "dataset": dataset,
                                   "name": name, "source_start": lo, "source_end": hi, "strand": strand})
            for anchor in p["reference_blocks"]:
                a, b = interval(anchor["source"])
                x, y = interval(anchor["reference"])
                if b-a != y-x or anchor["evidence_id"] not in construction["evidence"] or (ref and y > ref["length_bp"]):
                    raise ValueError("unbound or out-of-range q0 anchor")
                l, r = max(lo, a), min(hi, b)
                if l >= r or not ref:
                    continue
                # On the negative strand both mappings reverse. The assembled q0 slice is already oriented.
                q = cursor + (l-lo if strand == "+" else hi-r)
                v = x + (l-a if strand == "+" else b-r)
                track["bands"].append({"q": q, "ref": v, "bp": r-l, "via": label(p["localization_kind"])})
            cursor += hi-lo
            if i < len(joins):
                join = joins[i]
                n, kind = join["n_bp"], join["kind"]
                if (type(n) is not int or n < 0 or kind not in ("sequence_overlap", "input_assembly_gap", "reference_unknown")
                        or (n == 0) != (kind == "sequence_overlap") or join["left_id"] != piece["placement_id"]
                        or join["right_id"] != slices[i+1]["placement_id"]):
                    raise ValueError("invalid q0 join")
                if n:
                    track["parts"].append({"start": cursor, "end": cursor+n, "kind": kind})
                    cursor += n
        if sizes is not None and sizes.get(chrom) != cursor:
            raise ValueError("q0 plot differs from recorded FASTA length")
        track["length_bp"] = cursor
    return result


def bound_tracks(layout, q0, refs, q0_stats):
    expected = q0.get("source_sha256")
    if not expected or q0.get("source") != SELECTION:
        return None
    if not SHA.fullmatch(expected) or (q0_stats.get("sha256") and q0["q0_sha256"] != q0_stats["sha256"]):
        raise ValueError("q0 evidence identity mismatch")
    file = physical(layout.root, layout.relative(SELECTION))
    if not file.is_file():
        return None
    before = file_signature(file)
    if sha256_file(file) != expected:
        raise ValueError("q0 selection no longer belongs to this report")
    with file.open(encoding="utf-8") as stream:
        envelope = json.load(stream)
    if file_signature(file) != before or envelope["schema"] != SELECTION_SCHEMA:
        raise ValueError("q0 selection changed or is unsupported")
    sizes = ({r["sequence"]: r["length_bp"] for r in q0_stats["sequences"]} if "sequences" in q0_stats else None)
    return project(envelope["construction"], refs, sizes)


def snapshot_tracks(table, refs, q0_stats, version="q0"):
    """Older run-scoped snapshots can prove sequence layout without proving ref alignments."""
    if (not isinstance(table, dict) or not table.get("available") or table.get("preview_only")
            or not isinstance(table.get("rows"), list) or table.get("row_count", len(table["rows"])) != len(table["rows"])
            or not q0_stats.get("sequences")):
        return None
    sizes = {label(r["sequence"]): r["length_bp"] for r in q0_stats["sequences"]}
    parts = {}
    for row in table["rows"]:
        if row.get("q_version") != version:
            continue
        name, a, b = label(row["chr"]), int(row["q_start"])-1, int(row["q_end"])
        if not 0 <= a < b <= sizes[name]:
            raise ValueError("snapshot segment outside q0")
        seg = {"start": a, "end": b}
        if row["segment_kind"] == "gap":
            seg.update(kind="unspecified_gap")
        elif row["segment_kind"] in ("source", "telomere", "patch"):
            lo, hi = int(row["source_start"])-1, int(row["source_end"])
            if row["orientation"] not in ("+", "-") or lo < 0 or hi-lo != b-a:
                raise ValueError("unusable source interval in q0 snapshot")
            seg.update(kind="source", dataset=label(row["dataset_name"]), name=label(row["contig_name"]),
                       source_start=lo, source_end=hi, strand=row["orientation"])
        else:
            return None
        parts.setdefault(name, []).append(seg)
    if parts.keys() != sizes.keys():
        return None
    tracks = []
    for name in dict.fromkeys([*refs, *sizes]):
        ordered = sorted(parts.get(name, []), key=lambda p: p["start"])
        cursor = 0
        for seg in ordered:
            if seg["start"] != cursor:
                return None
            cursor = seg["end"]
        if cursor != sizes.get(name, 0):
            return None
        tracks.append({"chr": name, "length_bp": sizes.get(name), "ref": refs.get(name), "parts": ordered,
                       "bands": [], "status": "layout_only" if ordered else None})
    return tracks
