"""Source-aware support for structural edits, independent of dataset order.

MUMmer hulls classify candidates; they do not establish that self context is
independent evidence or that identical repeats occupy the same reference locus.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re

from .common import reverse_complement, sha256_bytes
from .q0_sources import Interval, SourceKey
from .source_intervals import source_spans
from .stage_io import path_sequence

POLICY = {
    "version": "source_structural_support_v1", "flank_bp": 100,
    "guide_identity": .95, "kmer_size": 15,
    "minimum_distinct_kmer_fraction": .5, "minimum_base_entropy": 1.2,
    "left_trim": "never_without_independent_variant_evidence",
    "self_guide": "same_source_or_equivalent_sequence_context_is_not_an_edit",
}


def self_context_lines(alignments, paths, members, *, identity_only=True):
    """Identify alignments whose mapped DNA is already the identical source.

    Coordinates are checked at every live source segment, not only the row's
    endpoints. N gaps are not DNA support. Exact identity requires matching
    original orientation/offsets. Structural eligibility uses identity_only=False:
    another repeat or reordered region of the SAME original source is not an
    independent assembly observation either.
    """
    spans, _ = source_spans(paths)
    by_chr = defaultdict(list)
    for span in spans:
        by_chr[span.chromosome].append(span)
    result = set()
    for row in alignments:
        member = members[str(row["ref_record"])]
        query = Interval(int(row["query_min"]) - 1, int(row["query_max"]))
        if identity_only and query.length != int(row["ref_max"]) - int(row["ref_min"]) + 1:
            continue
        ref_at_start = int(row["ref_min"] if row["orientation"] == "+" else row["ref_max"])
        member_forward = member.get("orientation", "+") == "+"
        source_start = (int(member["source_start"]) + ref_at_start - 2 if member_forward
                        else int(member["source_end"]) - ref_at_start)
        direction = (1 if row["orientation"] == "+" else -1) * (1 if member_forward else -1)
        source = SourceKey(member["dataset_name"], member["contig_name"])
        seen, identical = False, True
        for span in by_chr[str(row["chr"])]:
            shared = span.query.intersection(query)
            if shared is None:
                continue
            seen = True
            projected = span.project(shared)
            actual_start = projected.start if span.orientation == "+" else projected.end - 1
            if (span.source != source or (identity_only and (
                    (1 if span.orientation == "+" else -1) != direction
                    or actual_start != source_start + direction * (shared.start - query.start)))):
                identical = False
                break
        if seen and identical:
            result.add((str(row["chr"]), int(row["line_number"])))
    return result


def equivalent_sequence_context(left, right, member, source_start, source_end, records, sources, cache):
    """Agreement, including differences only in N padding, is not a repair.

    A renamed/copied assembly must not gain editing authority merely by having
    another SourceKey. Compare real oriented sequence context, not hull lengths
    or a similarity percentage. Cache repeated crossing rows used by many gaps.
    """
    rows = [left] if right is None else [left, right]
    chromosome = str(left["chr"])
    start = min(int(row["query_min"]) for row in rows) - 1
    end = max(int(row["query_max"]) for row in rows)
    key = (member["dataset_name"], member["contig_name"])
    orientation = left["orientation"]
    if member.get("orientation", "+") == "-":
        orientation = "+" if orientation == "-" else "-"
    identity = (chromosome, start, end, key, source_start, source_end, orientation)
    if identity not in cache:
        query = records[chromosome][start:end]
        guide = sources[key][source_start - 1:source_end]
        if orientation == "-":
            guide = reverse_complement(guide)
        cache[identity] = re.sub(r"N+", "N", query) == re.sub(r"N+", "N", guide)
    return cache[identity]


class ReferenceSupport:
    """Exact paired reference blocks frozen by the q0 selection, not ref hulls."""
    def __init__(self, placements=(), *, authority=""):
        self.authority = authority
        self.anchors = defaultdict(list)
        for placement in placements:
            source = SourceKey(**placement["source"])
            for block in placement["reference_blocks"]:
                self.anchors[source].append((Interval(**block["source"]), Interval(**block["reference"]),
                                             placement["chromosome"], placement["orientation"], block["evidence_id"]))

    def _local_blocks(self, segment, size, *, tail):
        forward = segment["orientation"] == "+"
        start, end = int(segment["source_start"]) - 1, int(segment["source_end"])
        if tail == forward:
            matched = Interval(end - size, end)
        else:
            matched = Interval(start, start + size)
        origin = matched.start if forward else matched.end - 1
        source = SourceKey(segment["dataset_name"], segment["contig_name"])
        result = []
        for interval, reference, chromosome, orientation, evidence_id in self.anchors[source]:
            shared = matched.intersection(interval)
            if shared is None:
                continue
            offset = shared.start - matched.start if forward else matched.end - shared.end
            ref_direction = 1 if orientation == "+" else -1
            ref_origin = reference.start if orientation == "+" else reference.end - 1
            slope = ref_direction * (1 if forward else -1)
            intercept = ref_origin + ref_direction * (origin - interval.start)
            result.append((Interval(offset, offset + shared.length), chromosome, slope, intercept, evidence_id))
        return result

    def compare(self, left, right, overlap):
        evidence = set()
        for li, lc, ls, lo, le in self._local_blocks(left, overlap, tail=True):
            for ri, rc, rs, ro, re in self._local_blocks(right, overlap, tail=False):
                shared = li.intersection(ri)
                if shared is None:
                    continue
                evidence.update((le, re))
                if lc != rc or ls != rs or ls * shared.start + lo != rs * shared.start + ro:
                    return False, sorted(evidence)
        return True, sorted(evidence)


def _complex(sequence):
    if len(sequence) < POLICY["kmer_size"] or set(sequence) - set("ACGT"):
        return False
    entropy = -sum((count / len(sequence)) * math.log2(count / len(sequence)) for count in Counter(sequence).values())
    k = POLICY["kmer_size"]
    distinct = len({sequence[i:i+k] for i in range(len(sequence)-k+1)}) / (len(sequence)-k+1)
    return entropy >= POLICY["minimum_base_entropy"] and distinct >= POLICY["minimum_distinct_kmer_fraction"]


def _unique_position(text, needle):
    position = text.find(needle)
    if position < 0 or text.find(needle, position + 1) >= 0 or reverse_complement(needle) in text:
        return None
    return position


class OverlapSupport:
    def __init__(self, sources, reference=None):
        self.sources = sources
        self.reference = reference or ReferenceSupport()
        self.oriented = {}

    def sequence(self, key, orientation):
        cache_key = (*key, orientation)
        if cache_key not in self.oriented:
            text = self.sources[key]
            self.oriented[cache_key] = text if orientation == "+" else reverse_complement(text)
        return self.oriented[cache_key]

    def prove(self, left, right, overlap, candidate):
        proof = {"policy": POLICY, "overlap_bp": overlap, "status": "rejected"}
        def reject(reason):
            proof["reason"] = reason
            return proof
        left_seq = path_sequence([left], self.sources)
        right_seq = path_sequence([right], self.sources)
        flank = POLICY["flank_bp"]
        if len(left_seq) < overlap + flank or len(right_seq) < overlap + flank:
            return reject("missing_outer_flanks")
        common = right_seq[:overlap]
        before, after = left_seq[-overlap-flank:-overlap], right_seq[overlap:overlap+flank]
        if not all(_complex(sequence) for sequence in (common, before, after)):
            return reject("low_complexity_overlap_or_flank")
        expected = defaultdict(set)
        for segment, tail in ((left, True), (right, False)):
            forward = segment["orientation"] == "+"
            start, end = int(segment["source_start"]) - 1, int(segment["source_end"])
            match_start = end - overlap if tail == forward else start
            expected[(segment["dataset_name"], segment["contig_name"])].add((match_start, segment["orientation"]))
        for key, expected_hits in expected.items():
            # Two disjoint N-split fragments of ONE input ctg are still two
            # candidate components. Permit exactly those nominated copies,
            # not arbitrary extra occurrences elsewhere in the original source.
            actual = set()
            for orientation, needle in (("+", common), ("-", reverse_complement(common))):
                position = self.sources[key].find(needle)
                while position >= 0:
                    actual.add((position, orientation))
                    if len(actual) > len(expected_hits):
                        return reject("repeated_overlap_in_original_source")
                    position = self.sources[key].find(needle, position + 1)
            if actual != expected_hits:
                return reject("repeated_overlap_in_original_source")
        consistent, evidence = self.reference.compare(left, right, overlap)
        proof["reference_evidence_namespace"] = "q0_selection_placement_blocks"
        proof["reference_authorization_id"] = self.reference.authority
        proof["reference_evidence_ids"] = evidence
        if not consistent:
            return reject("different_reference_loci")
        guide_key = (str(candidate.get("source_dataset", "")), str(candidate.get("source_contig", "")))
        if guide_key not in self.sources:
            return reject("missing_sequence_guide")
        orientation = str(candidate.get("orientation", "+"))
        guide = self.sequence(guide_key, orientation)
        left_pos, right_pos = _unique_position(guide, before), _unique_position(guide, after)
        if left_pos is None or right_pos is None:
            return reject("nonunique_or_missing_guide_flanks")
        if right_pos != left_pos + flank + overlap:
            return reject("guide_flank_geometry_disagrees")
        middle = guide[left_pos+flank:right_pos]
        if set(middle) - set("ACGT") or sum(a == b for a, b in zip(middle, common)) / overlap < POLICY["guide_identity"]:
            return reject("guide_does_not_support_shared_overlap")
        start, end = left_pos, right_pos + flank
        if orientation == "-":
            start, end = len(guide) - end, len(guide) - start
        if start < int(candidate.get("source_start", 0)) - 1 or end > int(candidate.get("source_end", 0)):
            return reject("guide_support_outside_alignment_evidence")
        proof.update(status="supported", guide_source={"dataset": guide_key[0], "contig": guide_key[1]},
                     guide_interval={"start": start, "end": end}, guide_orientation=orientation,
                     guide_sequence_sha256=sha256_bytes(guide[left_pos:right_pos+flank].encode("ascii")),
                     overlap_sequence_sha256=sha256_bytes(common.encode("ascii")))
        return proof
