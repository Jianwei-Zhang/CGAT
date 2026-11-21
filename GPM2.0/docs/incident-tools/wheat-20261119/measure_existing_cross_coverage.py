"""Read-only residual sizing from completed cross-source PAFs, not admission.

Never changes a runtime, checkpoint or scientific policy. It measures whether
actual paired M/= blocks already cover the >=100bp strict-reference holes.
Coverage is not unique placement, a candidate-location list or cache acceptance.
"""
import argparse
from bisect import bisect_left
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import time

CIGAR = re.compile(r"([1-9][0-9]*)([MIDN=X])")


def paired_geometry(fields):
    """Validate every CIGAR operation, returning exact forward M/= intervals."""
    qlen, qs, qe = map(int, fields[1:4])
    tlen, ts, te = map(int, fields[6:9])
    matches, span, mapq = map(int, fields[9:12])
    strand = fields[4]
    if not (0 <= qs < qe <= qlen and 0 <= ts < te <= tlen
            and strand in ("+", "-") and span > 0
            and 0 <= matches <= min(span, qe-qs, te-ts) and 0 <= mapq <= 255):
        raise ValueError("invalid PAF coordinates/statistics")
    tags = [tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")]
    if len(tags) != 1:
        raise ValueError("exactly one CIGAR required")
    cigar = tags[0]
    q, t, cursor = (qs if strand == "+" else qe), ts, 0
    paired = []
    for match in CIGAR.finditer(cigar):
        if match.start() != cursor:
            raise ValueError("invalid CIGAR")
        cursor = match.end()
        n, op = int(match[1]), match[2]
        q1 = q + (n if strand == "+" else -n) if op in "MI=X" else q
        t1 = t + n if op in "MDN=X" else t
        if op in "M=":
            paired.append((min(q, q1), max(q, q1), t, t1))
        q, t = q1, t1
    if not cursor or cursor != len(cigar) or q != (qe if strand == "+" else qs) or t != te:
        raise ValueError("CIGAR span mismatch")
    return paired


def subtract(holes, start, end, minimum=100):
    """Remove exact covered bases; omit only residuals below report threshold.

    Discarded short residuals cannot grow when more coverage is subtracted.
    No bridging of a >=minimum gap and no interval hull approximation.
    """
    lo = bisect_left(holes, [start])
    if lo and holes[lo-1][1] > start:
        lo -= 1
    hi, replacements = lo, []
    while hi < len(holes) and holes[hi][0] < end:
        a, b = holes[hi]
        if min(start, b)-a >= minimum:
            replacements.append([a, min(start, b)])
        if b-max(end, a) >= minimum:
            replacements.append([max(end, a), b])
        hi += 1
    if hi > lo:
        holes[lo:hi] = replacements


def stats(rows):
    out = defaultdict(lambda: dict(source_count=0, whole_source_bp=0, residual_bp=0,
                                   intervals=0, max_interval_bp=0))
    for (dataset, _), row in rows.items():
        holes = row["holes"]
        if not holes:
            continue
        d = out[dataset]
        d["source_count"] += 1
        d["whole_source_bp"] += row["length"]
        d["residual_bp"] += sum(b-a for a, b in holes)
        d["intervals"] += len(holes)
        d["max_interval_bp"] = max(d["max_interval_bp"], max(b-a for a, b in holes))
    return dict(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--lookup-dir", type=Path, required=True)
    p.add_argument("--coverage-dir", type=Path, required=True)
    p.add_argument("--completed-supplement", required=True)
    a = p.parse_args()
    started = time.monotonic()
    root = a.workspace.resolve(strict=True)
    metadata = {}

    def load(path):
        raw = path.read_bytes()
        metadata[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    parts = load(a.lookup_dir / "source-part-lookup.json")
    proof = load(a.lookup_dir / "receipt.json")
    if metadata[str(a.lookup_dir / "source-part-lookup.json")] != proof["lookup_sha256"]:
        raise ValueError("lookup changed")
    lengths = {(v["dataset"], v["contig"]): v["length"] for v in parts.values()}
    if len(lengths) != len(parts):
        raise ValueError("ambiguous full-source lookup")
    baseline = load(a.coverage_dir / "summary.json")
    if "minimum_reference_mapq" in baseline:
        if baseline["minimum_reference_mapq"] != 20 or baseline["include_unavailable_mapq"]:
            raise ValueError("strict baseline required")
    else:
        # The first strict probe predates configurable MAPQ fields. Accept only
        # that exact inspected producer, never an unlabelled report by default.
        producer = a.coverage_dir / "coverage.py"
        sha = hashlib.sha256(producer.read_bytes()).hexdigest()
        if sha != "f63d361d9e2c3371d0e40915df8193a808b78c7986a861744274b54d4c7a13f3":
            raise ValueError("unknown legacy strict-coverage producer")
        metadata[str(producer)] = sha
    rows = {}
    for row in load(a.coverage_dir / "partial-coverage.json"):
        key = row["dataset"], row["contig"]
        holes = row["uncovered"]
        if key in rows or lengths[key] != row["length"]:
            raise ValueError("source mismatch")
        last = -1
        for start, end in holes:
            if not (0 <= start < end <= row["length"] and end-start >= 100 and start > last):
                raise ValueError("invalid baseline holes")
            last = end
        rows[key] = dict(length=row["length"], holes=holes)
    before = stats(rows)
    for source in baseline["datasets"]:
        d = before[source["dataset"]]
        if (d["source_count"] != source["partial_query_count"]
                or d["residual_bp"] != source["window_total_bp_by_flank"]["0"]):
            raise ValueError("baseline summary mismatch")
    checkpoint_outputs = {}
    for path in sorted((root / ".run_all/checkpoints").glob("q0-chr-*.json")):
        receipt = load(path)
        if receipt.get("status") == "success":
            for output in receipt["outputs"]:
                previous = checkpoint_outputs.setdefault(output["path"], output)
                if previous != output:
                    raise ValueError("conflicting successful output identities")
    jobs = []
    for path in sorted((root / "runs").glob("chr_*/q0_alignment_inputs.json")):
        for row in load(path)["alignments"]:
            if row["query_dataset"] != row["target_dataset"]:
                output = checkpoint_outputs[row["paf"]]
                jobs.append((output, row["query_dataset"], row["target_dataset"]))
    supplement = load(root / a.completed_supplement / "success.json")
    relpaf = a.completed_supplement + "/result.paf"
    jobs.append((next(r for r in supplement["outputs"] if r["path"] == relpaf), None, None))
    scans = []
    for output, qdataset, tdataset in jobs:
        path = root / output["path"]
        original = path.stat()
        if original.st_size != output["size"]:
            raise ValueError("completed PAF size changed")
        digest, count, qualified, bp = hashlib.sha256(), 0, 0, 0
        with path.open("rb") as stream:
            for raw in stream:
                digest.update(raw)
                if not raw.strip() or raw.startswith(b"#"):
                    continue
                f = raw.decode("ascii").rstrip("\r\n").split("\t")
                if len(f) < 12:
                    raise ValueError("incomplete PAF")
                if qdataset is None:
                    q, t = parts[f[0]], parts[f[5]]
                    qkey, tkey = (q["dataset"], q["contig"]), (t["dataset"], t["contig"])
                else:
                    qkey, tkey = (qdataset, f[0]), (tdataset, f[5])
                if int(f[1]) != lengths[qkey] or int(f[6]) != lengths[tkey]:
                    raise ValueError("PAF source length changed")
                geometry = paired_geometry(f)  # validate even non-qualifying/later duplicate rows
                count += 1
                aligned = sum(qe-qs for qs, qe, _, _ in geometry)
                if qkey[0] != tkey[0] and int(f[9])/int(f[10]) >= .95 and aligned >= 100:
                    qualified += 1
                    bp += aligned
                    qholes = rows.get(qkey, {}).get("holes", [])
                    tholes = rows.get(tkey, {}).get("holes", [])
                    for qs, qe, ts, te in geometry:
                        subtract(qholes, qs, qe)
                        subtract(tholes, ts, te)
                if count % 100000 == 0:
                    print(json.dumps(dict(path=output["path"], rows=count)), flush=True)
        after = path.stat()
        fence = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if fence(original) != fence(after) or digest.hexdigest() != output["sha256"]:
            raise ValueError("completed PAF changed; no summary published")
        row = dict(path=output["path"], sha256=digest.hexdigest(), rows=count,
                   qualified_cross_rows=qualified, paired_bp_with_multiplicity=bp, residual=stats(rows))
        scans.append(row)
        print(json.dumps(row), flush=True)
    for path, sha in metadata.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError("input metadata changed")
    residual = [{"dataset": d, "contig": c, "length": row["length"], "uncovered": row["holes"]}
                for (d, c), row in sorted(rows.items()) if row["holes"]]
    Path("residual-coverage.json").write_text(json.dumps(residual)+"\n")
    report = dict(status="read_only_residual_sizing", before=before, after=stats(rows), scans=scans,
                  input_metadata_sha256=metadata, seconds=time.monotonic()-started,
                  policy="cross datasets only, identity>=0.95, >=100 M/= paired bp per hit, no MAPQ filter; residual holes>=100bp",
                  scientific_acceptance=False, production_policy_changed=False,
                  limitations="coverage not uniqueness/placement; baseline derived from previous reference scan, no source DNA revalidation")
    Path("summary.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
