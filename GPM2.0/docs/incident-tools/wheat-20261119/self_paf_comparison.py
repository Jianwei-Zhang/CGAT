"""All-hit self evidence comparison, not a primary-only accuracy oracle.

Sample CIGAR-projected placements without filtering MAPQ or tp. At each query
position, target and strand, match distinct placements one-to-one, so a single
remaining placement cannot hide losses of other repeat placements. Identical
coordinate duplicates are coalesced and counted separately. Also compare exact
unions of aligned query/target intervals per oriented pair. Sampling can miss
short coordinate changes; agreement with a baseline is not biological accuracy.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import re


@dataclass
class Evidence:
    sampling_step: int
    anchors: dict
    query_intervals: dict
    target_intervals: dict
    lengths: dict
    rows: int
    hit_types: dict
    sampled_placement_observations: int


def union(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def length(intervals):
    return sum(hi - lo for lo, hi in intervals)


def intersection_length(left, right):
    i = j = total = 0
    while i < len(left) and j < len(right):
        a, b = left[i]; c, d = right[j]
        total += max(0, min(b, d) - max(a, c))
        if b <= d: i += 1
        else: j += 1
    return total


def one_to_one_support(left, right, tolerance):
    if tolerance < 0:
        raise ValueError("negative positional tolerance")
    left, right = sorted(set(left)), sorted(set(right))
    i = j = matched = 0
    while i < len(left) and j < len(right):
        if left[i] < right[j] - tolerance: i += 1
        elif right[j] < left[i] - tolerance: j += 1
        else:
            matched += 1; i += 1; j += 1
    return matched


def read_evidence(path, step=1000):
    if type(step) is not int or step < 1:
        raise ValueError("positive integer sampling step required")
    anchors = defaultdict(set)
    qi, ti = defaultdict(list), defaultdict(list)
    lengths, kinds = {}, Counter()
    count = observations = 0
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) < 12 or fields[4] not in ("+", "-"):
                raise ValueError(f"malformed PAF row {number}")
            qname, tname, strand = fields[0], fields[5], fields[4]
            qlen, qs, qe = map(int, fields[1:4])
            tlen, ts, te = map(int, fields[6:9])
            if not (0 <= qs < qe <= qlen and 0 <= ts < te <= tlen):
                raise ValueError(f"invalid PAF coordinates at row {number}")
            for role, name, size in (("query", qname, qlen), ("target", tname, tlen)):
                if lengths.setdefault((role, name), size) != size:
                    raise ValueError("inconsistent sequence length")
            cigars = [tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")]
            if len(cigars) != 1:
                raise ValueError("exactly one CIGAR required for every hit")
            cigar = cigars[0]
            operations = re.findall(r"([1-9][0-9]*)([MIDN=X])", cigar)
            if not operations or "".join(n + op for n, op in operations) != cigar:
                raise ValueError("malformed CIGAR in all-hit comparison")
            pair = (qname, tname, strand)
            qdone, target = 0, ts
            for size, op in operations:
                size = int(size)
                if op in "M=X":
                    lo, hi = ((qs + qdone, qs + qdone + size) if strand == "+"
                              else (qe - qdone - size, qe - qdone))
                    qi[pair].append((lo, hi)); ti[pair].append((target, target + size))
                    for q in range(((lo + step - 1) // step) * step, hi, step):
                        position = target + (q - lo if strand == "+" else hi - 1 - q)
                        anchors[(*pair, q)].add(position)
                        observations += 1
                if op in "MI=X": qdone += size
                if op in "MDN=X": target += size
            if qdone != qe - qs or target != te:
                raise ValueError("CIGAR span mismatch")
            kind = [tag[5:] for tag in fields[12:] if tag.startswith("tp:A:")]
            kinds[kind[0] if len(kind) == 1 else "missing_or_ambiguous"] += 1
            count += 1
    return Evidence(step, dict(anchors), {k: union(v) for k, v in qi.items()},
                    {k: union(v) for k, v in ti.items()}, lengths, count, dict(kinds), observations)


def inventory(evidence):
    distinct = sum(map(len, evidence.anchors.values()))
    return {"paf_rows": evidence.rows, "hit_types": evidence.hit_types,
        "oriented_pairs": len(evidence.query_intervals), "sampled_distinct_placements": distinct,
        "duplicate_sampled_placement_observations": evidence.sampled_placement_observations - distinct,
        "pair_query_aligned_bases": sum(length(v) for v in evidence.query_intervals.values()),
        "pair_target_aligned_bases": sum(length(v) for v in evidence.target_intervals.values())}


def compare_evidence(left, right, step=1000, tolerances=(0, 100, 1000)):
    if left.sampling_step != step or right.sampling_step != step:
        raise ValueError("sampling steps disagree")
    if any(left.lengths[k] != right.lengths[k] for k in left.lengths.keys() & right.lengths.keys()):
        raise ValueError("baseline/candidate sequence lengths disagree")
    report = {"scope": "all_hits_sampled_positions_and_exact_oriented_pair_aligned_coverage",
        "query_sampling_step_bases": step, "primary_or_mapq_filter_applied": False,
        "accuracy_claim": "baseline agreement only; sampled positions are not exhaustive",
        "placement_matching": "distinct_positions_one_to_one_within_each_query_target_strand_grid_key",
        "baseline": inventory(left), "candidate": inventory(right), "position_support": {}, "pairs": []}
    keys = left.anchors.keys() | right.anchors.keys()
    for tolerance in tolerances:
        matched = sum(one_to_one_support(left.anchors.get(k, ()), right.anchors.get(k, ()), tolerance)
                      for k in keys)
        total_left = report["baseline"]["sampled_distinct_placements"]
        total_right = report["candidate"]["sampled_distinct_placements"]
        report["position_support"][str(tolerance)] = {"matched": matched,
            "missing_baseline_placements": total_left - matched,
            "extra_candidate_placements": total_right - matched,
            "missing_fraction": (total_left - matched) / total_left if total_left else None,
            "extra_fraction": (total_right - matched) / total_right if total_right else None}
    for pair in sorted(left.query_intervals.keys() | right.query_intervals.keys()):
        row = {"query": pair[0], "target": pair[1], "strand": pair[2],
            "baseline_present": pair in left.query_intervals, "candidate_present": pair in right.query_intervals}
        for name, first, second in (("query", left.query_intervals, right.query_intervals),
                                     ("target", left.target_intervals, right.target_intervals)):
            a, b = first.get(pair, ()), second.get(pair, ())
            common = intersection_length(a, b)
            row[name + "_aligned_coverage"] = {"baseline": length(a), "candidate": length(b),
                "intersection": common, "missing": length(a) - common, "extra": length(b) - common}
        report["pairs"].append(row)
    report["missing_pairs"] = sum(not row["candidate_present"] for row in report["pairs"])
    report["extra_pairs"] = sum(not row["baseline_present"] for row in report["pairs"])
    return report


def compare(baseline, candidate, step=1000):
    return compare_evidence(read_evidence(baseline, step), read_evidence(candidate, step), step)
