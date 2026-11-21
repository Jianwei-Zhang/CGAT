"""Composition of native, coordinate-explicit changes against one LGZ baseline.

A trace is checked against the actual native FASTA before any proposal is admitted.
Retained ranges remain LGZ sources, including negative-strand source fragments.
Every newly introduced range has a native job/source description; final FASTA is
still reconstructed by refinement_path, never copied from the native chromosome.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import re

try:
    from refinement_path import BLOCK, Edit, PathError, identity, slice_source, source_blocks
except ModuleNotFoundError:
    from .refinement_path import BLOCK, Edit, PathError, identity, slice_source, source_blocks


class TraceError(PathError):
    pass


def retained(start, end, evidence=None):
    if not 0 <= start < end:
        raise TraceError("invalid retained native range")
    return {"kind": "baseline", "start": start, "length": end - start, "evidence": evidence or {}}


def inserted(source, evidence):
    return {"kind": "source", "length": source["end"] - source["start"] + 1,
            "source": source, "evidence": evidence}


def trace_slice(trace, start, end):
    rows, cursor = [], 0
    for piece in trace:
        stop = cursor + piece["length"]
        a, b = max(start, cursor), min(end, stop)
        if a < b:
            row = copy.deepcopy(piece)
            row["length"] = b - a
            if row["kind"] == "baseline":
                row["start"] += a - cursor
            elif row["kind"] == "source":
                row["source"] = slice_source(piece["source"], a - cursor, b - cursor)
            rows.append(row)
        cursor = stop
        if cursor >= end:
            break
    if sum(row["length"] for row in rows) != end - start:
        raise TraceError("native edit exceeds its preceding iteration")
    return rows


def apply_changes(trace, changes):
    """Each change is (start,end,replacement_pieces), in the preceding iteration."""
    length = sum(row["length"] for row in trace)
    result, cursor = [], 0
    for start, end, replacement in sorted(changes, key=lambda row: (row[0], row[1])):
        if not cursor <= start < end <= length:
            raise TraceError("native replacement coordinates overlap or exceed the input")
        result += trace_slice(trace, cursor, start)
        result += replacement
        cursor = end
    return result + trace_slice(trace, cursor, length)


def trace_blocks(trace, chromosome, baseline, catalog):
    for row in trace:
        if row["length"] <= 0:
            raise TraceError("zero-length native trace component")
        if row["kind"] == "baseline":
            yield from baseline.blocks(chromosome, row["start"], row["start"] + row["length"])
        elif row["kind"] == "source":
            yield from source_blocks(row["source"], catalog)
        elif row["kind"] == "gap":
            for offset in range(0, row["length"], BLOCK):
                yield b"N" * min(BLOCK, row["length"] - offset)
        else:
            raise TraceError("unknown native trace component")


def verify_trace(trace, chromosome, baseline, catalog, native):
    if sum(row["length"] for row in trace) != native.records[chromosome][0]:
        raise TraceError(f"native trace length does not reconstruct {chromosome}")
    cursor = 0
    for block in trace_blocks(trace, chromosome, baseline, catalog):
        expected = native.fetch(chromosome, cursor, cursor + len(block)).upper()
        if block.upper() != expected:
            raise TraceError(f"native trace sequence does not reconstruct {chromosome}:{cursor}")
        cursor += len(block)
    if cursor != native.records[chromosome][0]:
        raise TraceError("native trace source lengths are inconsistent")


def equal_regions(left, name, a, right, b, length):
    for offset in range(0, length, BLOCK):
        count = min(BLOCK, length - offset)
        if left.fetch(name, a + offset, a + offset + count).upper() != right.fetch(name, b + offset, b + offset + count).upper():
            return False
    return True


def trim_equal_ends(baseline, native, chromosome, a, b, x, y):
    """Retain unchanged flanks, even when a native replacement includes them."""
    while min(b - a, y - x) > 0:
        size = min(BLOCK, b - a, y - x)
        left = baseline.fetch(chromosome, a, a + size).upper()
        right = native.fetch(chromosome, x, x + size).upper()
        if left == right:
            a, x = a + size, x + size
            continue
        equal = next(i for i in range(size) if left[i] != right[i])
        a, x = a + equal, x + equal
        break
    while min(b - a, y - x) > 0:
        size = min(BLOCK, b - a, y - x)
        left = baseline.fetch(chromosome, b - size, b).upper()
        right = native.fetch(chromosome, y - size, y).upper()
        if left == right:
            b, y = b - size, y - size
            continue
        equal = next(i for i in range(size) if left[-1 - i] != right[-1 - i])
        b, y = b - equal, y - equal
        break
    return a, b, x, y


def unique_occurrence(genome, chromosome, start, end, pattern):
    """Search in bounded input blocks; memory is bounded by an internal island."""
    carry, found = b"", None
    for offset in range(start, end, BLOCK):
        block = genome.fetch(chromosome, offset, min(end, offset + BLOCK)).upper()
        data = carry + block
        origin, at = offset - len(carry), 0
        while True:
            at = data.find(pattern, at)
            if at < 0:
                break
            position = origin + at
            if found is not None and position != found:
                return "ambiguous"
            found = position
            at += 1
        carry = data[-(len(pattern) - 1):] if len(pattern) > 1 else b""
    return found


def split_retained_islands(baseline, native, chromosome, interval, gaps):
    a, b, x, y = interval
    affected = [gap for gap in gaps if gap.chromosome == chromosome and a < gap.end and gap.start < b]
    anchors = []
    for left, right in zip(affected, affected[1:]):
        start, end = left.end, right.start
        if not a <= start < end <= b or end - start > y - x:
            continue
        pattern = b"".join(baseline.blocks(chromosome, start, end)).upper()
        position = unique_occurrence(native, chromosome, x, y, pattern)
        if position == "ambiguous":
            raise TraceError("ambiguous unchanged internal island in joint native edit")
        if position is not None:
            if anchors and position < anchors[-1][3]:
                raise TraceError("native internal islands are reordered")
            anchors.append((start, end, position, position + len(pattern)))
    result, old, new = [], a, x
    for start, end, new_start, new_end in anchors:
        result.append((old, start, new, new_start))
        old, new = end, new_end
    result.append((old, b, new, y))
    return result


def normalized_edits(tool, traces, baseline, native, gaps, *, native_dataset, native_names, job):
    edits, rejected = [], []
    for chromosome, trace in traces.items():
        old_cursor, new_cursor, window_start, evidence = 0, 0, 0, []
        windows = []
        previous_anchor = None
        for row in trace:
            if row["kind"] == "baseline":
                if row["start"] < old_cursor:
                    raise TraceError("native retained baseline intervals are reordered or duplicated")
                if row["start"] != old_cursor or new_cursor != window_start:
                    windows.append(((old_cursor, row["start"], window_start, new_cursor),
                                    {"pieces": evidence, "left_anchor": previous_anchor, "right_anchor": row}))
                old_cursor = row["start"] + row["length"]
                new_cursor += row["length"]
                window_start, evidence, previous_anchor = new_cursor, [], row
            else:
                evidence.append(copy.deepcopy(row))
                new_cursor += row["length"]
        if old_cursor != baseline.records[chromosome][0] or window_start != new_cursor:
            windows.append(((old_cursor, baseline.records[chromosome][0], window_start, new_cursor),
                            {"pieces": evidence, "left_anchor": previous_anchor, "right_anchor": None}))
        for initial, proof in windows:
            a, b, x, y = trim_equal_ends(baseline, native, chromosome, *initial)
            if a == b and x == y:
                continue
            affected = [gap.gap_id for gap in gaps if gap.chromosome == chromosome and a < gap.end and gap.start < b]
            try:
                parts = split_retained_islands(baseline, native, chromosome, (a, b, x, y), gaps)
            except TraceError as error:
                rejected.append({"gap_ids": affected, "native_job": job, "reason": str(error),
                                 "chromosome": chromosome, "baseline_interval": [a, b], "native_interval": [x, y]})
                continue
            for part in parts:
                left, right, begin, end = trim_equal_ends(baseline, native, chromosome, *part)
                if left == right and begin == end:
                    continue
                if left == right and begin < end:
                    # A partial native extension can insert before/after retained
                    # Ns. Anchor it to one unchanged N so the existing replacement
                    # contract can represent it without losing the original gap.
                    for gap in gaps:
                        if gap.chromosome != chromosome or not gap.start <= left <= gap.end:
                            continue
                        if left < gap.end and end < native.records[chromosome][0] and native.fetch(chromosome, end, end + 1).upper() == b"N":
                            right, end = right + 1, end + 1
                            break
                        if left > gap.start and begin > 0 and native.fetch(chromosome, begin - 1, begin).upper() == b"N":
                            left, begin = left - 1, begin - 1
                            break
                gap_ids = tuple(gap.gap_id for gap in gaps if gap.chromosome == chromosome and left < gap.end and gap.start < right)
                if not gap_ids or left >= right:
                    rejected.append({"gap_ids": list(gap_ids), "native_job": job, "chromosome": chromosome,
                                     "baseline_interval": [left, right], "native_interval": [begin, end],
                                     "reason": "native_change_not_bound_to_an_original_gap"})
                    continue
                replacement = None if begin == end else {"dataset": native_dataset, "contig": native_names[chromosome],
                                                          "start": begin + 1, "end": end, "orientation": "+"}
                eid = tool + "-" + identity([job, chromosome, left, right, begin, end])[:24]
                edits.append(Edit(eid, tool, chromosome, left, right, replacement, gap_ids, job,
                                  {"method": "validated_native_trace", "native_interval": [begin, end],
                                   "native_trace": proof, "original_native_window": list(initial),
                                   "unchanged_internal_islands_retained": len(parts) > 1,
                                   "claim": "traceable native modification; not independent biological validation"}))
    merged = []
    for edit in sorted(edits, key=lambda e: (e.chromosome, e.start, e.end)):
        if merged and merged[-1].chromosome == edit.chromosome and edit.start < merged[-1].end:
            previous = merged.pop()
            left, right = min(previous.start, edit.start), max(previous.end, edit.end)
            begin = min(previous.evidence["native_interval"][0], edit.evidence["native_interval"][0])
            end = max(previous.evidence["native_interval"][1], edit.evidence["native_interval"][1])
            source = None if begin == end else {"dataset": native_dataset, "contig": native_names[edit.chromosome],
                                               "start": begin + 1, "end": end, "orientation": "+"}
            evidence = {"method": "composed_native_trace_insertions", "native_interval": [begin, end],
                        "parents": [previous.evidence, edit.evidence]}
            merged.append(replace(previous, edit_id=tool + "-" + identity([job, edit.chromosome, left, right, begin, end])[:24],
                                  start=left, end=right, replacement=source,
                                  gap_ids=tuple(dict.fromkeys(previous.gap_ids + edit.gap_ids)), evidence=evidence))
        else:
            merged.append(edit)
    return merged, rejected
