"""Source-domain annotation measurements projected through actual accepted slices."""
from __future__ import annotations

import csv
import json
from pathlib import Path

try:
    from workspace_layout import WorkspaceLayout
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout

SLICE_FIELDS = ("chromosome", "segment_id", "dataset", "contig", "source_start", "source_end",
                "source_orientation", "final_start", "final_end", "segment_kind")
MARK_FIELDS = ("kind", "annotation_id", "dataset", "contig", "source_start", "source_end", "source_strand",
               "chromosome", "segment_id", "final_start", "final_end", "final_strand", "projection", "origin", "provenance")


def table(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def annotation_inputs(root, chromosomes):
    layout = WorkspaceLayout.detect(root)
    result = []
    for chromosome in chromosomes:
        for path in sorted(layout.path("tel/chr_" + chromosome).glob("*.tsv")):
            result.append({"kind": "tel", "chromosome": chromosome, "path": path, "origin": "lgz_source"})
        path = layout.path("cen/chr_" + chromosome + "/marks.tsv")
        if path.exists() or path.is_symlink():
            result.append({"kind": "cen", "chromosome": chromosome, "path": path, "origin": "lgz_source"})
    return result


def slices(final):
    for chromosome in final["chromosomes"]:
        for segment in chromosome["segments"]:
            source = segment.get("source") if segment["kind"] != "gap" else segment.get("refinement_source")
            if source is None:
                continue
            start, end = source["start"], source["end"]
            if not 1 <= start <= end or end - start + 1 != segment["length"] or source["orientation"] not in {"+", "-"}:
                raise ValueError("invalid accepted source slice for annotation projection")
            yield {"chromosome": chromosome["chr"], "segment_id": segment["segment_id"], "dataset": source["dataset"],
                   "contig": source["contig"], "source_start": start, "source_end": end,
                   "source_orientation": source["orientation"], "final_start": segment["output_start"],
                   "final_end": segment["output_start"] + segment["length"], "segment_kind": segment["kind"]}


def project(final, source_lengths, inputs, *, origins=None):
    """Half-open final coordinates; clipped source support is not a final rescan."""
    source_slices = list(slices(final))
    by_key = {}
    for row in source_slices:
        key = row["dataset"], row["contig"], row["chromosome"]
        if row["source_end"] > source_lengths[key[:2]]:
            raise ValueError("annotation projection slice exceeds source length")
        by_key.setdefault(key, []).append(row)
    projected, seen = [], set()
    for spec in inputs:
        for mark in table(spec["path"]):
            kind = spec["kind"]
            dataset = mark.get("dataset_name", "")
            contig = mark.get("seq_name" if kind == "tel" else "ctg_name", "")
            key = dataset, contig, spec["chromosome"]
            if key not in by_key:
                continue
            declared = mark.get("assigned_chr_name" if kind == "tel" else "chr_name")
            if declared != spec["chromosome"]:
                raise ValueError("source annotation chromosome differs from its scan")
            start, end = int(mark["start_bp" if kind == "tel" else "ctg_start"]), int(mark["end_bp" if kind == "tel" else "ctg_end"])
            strand = mark["strand"]
            if not 1 <= start <= end <= source_lengths[key[:2]] or strand not in {"+", "-"}:
                raise ValueError("invalid measured source annotation interval/strand")
            provenance = mark.get("provenance") or "[]"
            json.loads(provenance)
            annotation_id = mark["rule_id" if kind == "tel" else "cen_id"]
            for source in by_key[key]:
                a, b = max(start, source["source_start"]), min(end, source["source_end"])
                if a > b:
                    continue
                reverse = source["source_orientation"] == "-"
                final_start = source["final_start"] + (source["source_end"] - b if reverse else a - source["source_start"])
                final_end = source["final_start"] + (source["source_end"] - a + 1 if reverse else b - source["source_start"] + 1)
                row = {"kind": kind, "annotation_id": annotation_id, "dataset": dataset, "contig": contig,
                       "source_start": a, "source_end": b, "source_strand": strand, "chromosome": source["chromosome"],
                       "segment_id": source["segment_id"], "final_start": final_start, "final_end": final_end,
                       "final_strand": ("-" if strand == "+" else "+") if reverse else strand,
                       "projection": "complete_source_mark" if (a, b) == (start, end) else "clipped_source_support_not_rescanned",
                       "origin": (origins or {}).get(key[:2], spec["origin"]), "provenance": provenance}
                identity = tuple(str(row[name]) for name in MARK_FIELDS)
                if identity not in seen:
                    seen.add(identity)
                    projected.append(row)
    return source_slices, projected
