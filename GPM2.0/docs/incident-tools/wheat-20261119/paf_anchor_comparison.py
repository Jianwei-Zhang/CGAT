"""Sample exact CIGAR-projected primary positions; not a full accuracy oracle."""
import collections
import re


def anchors(path, step=10_000):
    if step < 1:
        raise ValueError("positive sampling step required")
    result = collections.defaultdict(set)
    for line in path.read_text().splitlines():
        f = line.split("\t")
        if "tp:A:P" not in f[12:]:
            continue
        cigar = next((v[5:] for v in f[12:] if v.startswith("cg:Z:")), "")
        ops = re.findall(r"([1-9][0-9]*)([MIDN=X])", cigar)
        if not ops or "".join(n + op for n, op in ops) != cigar:
            raise ValueError("missing or malformed primary CIGAR")
        qs, qe, ts, te = int(f[2]), int(f[3]), int(f[7]), int(f[8])
        qdone, target = 0, ts
        for text, op in ops:
            n = int(text)
            if op in "M=X":
                lo, hi = ((qs + qdone, qs + qdone + n) if f[4] == "+"
                          else (qe - qdone - n, qe - qdone))
                for q in range(((lo + step - 1) // step) * step, hi, step):
                    pos = target + (q - lo if f[4] == "+" else hi - 1 - q)
                    result[(f[0], q)].add((f[5], f[4], pos))
            if op in "MI=X":
                qdone += n
            if op in "MDN=X":
                target += n
        if qdone != qe - qs or target != te:
            raise ValueError("primary CIGAR span mismatch")
    return result


def compare(baseline, candidate, step=10_000):
    left, right = anchors(baseline, step), anchors(candidate, step)
    report = {"query_sampling_step_bases": step, "baseline_anchor_count": len(left),
              "candidate_anchor_count": len(right),
              "missing_candidate_anchors": len(left.keys() - right.keys()),
              "extra_candidate_anchors": len(right.keys() - left.keys()),
              "ambiguous_baseline_anchors": sum(len(v) > 1 for v in left.values()),
              "ambiguous_candidate_anchors": sum(len(v) > 1 for v in right.values())}
    for tolerance in (0, 100, 1000):
        def agrees(a, b):
            return a[:2] == b[:2] and abs(a[2] - b[2]) <= tolerance
        report[f"baseline_anchors_supported_within_{tolerance}bp"] = sum(
            any(agrees(a, b) for a in positions for b in right.get(key, ()))
            for key, positions in left.items())
        report[f"candidate_anchors_with_extra_positions_beyond_{tolerance}bp"] = sum(
            any(not any(agrees(a, b) for a in left.get(key, ())) for b in positions)
            for key, positions in right.items())
    return report
