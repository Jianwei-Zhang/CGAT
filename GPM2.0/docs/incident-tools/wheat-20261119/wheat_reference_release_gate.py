"""Read-only wheat release gates. Coordinates are source-forward, zero-based and half-open."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import json
from types import SimpleNamespace

PRIMARY = {str(i) + sub for i in range(1, 8) for sub in "ABD"}
UNPLACED = {"Un", "chrUn"}
POLICY = "local_chain_intact_slice_ng50_v1"


def classify(row, new_bp, old_bp):
    a, b = row["current_group"], row["old_group"]
    if a == b or {a, b} - PRIMARY - UNPLACED:
        raise ValueError("unexpected chromosome conflict")
    if {a, b} & UNPLACED:
        return "unplaced_comparator"
    if not all(type(x) is int and 0 <= x <= row["bp"] for x in (new_bp, old_bp)):
        raise ValueError("invalid local reference support")
    return "locally_supported_split" if new_bp >= 100_000 and new_bp >= 10 * old_bp else "unsupported_primary"


def cross_audit(base, rows):
    """Never use inherited placement blocks as independent reference evidence."""
    output = [dict(row) for row in rows]
    primary = []
    for row in output:
        if UNPLACED.intersection((row["current_group"], row["old_group"])):
            row["verdict"] = classify(row, None, None)
        else:
            primary.append(row)
    def compare(row, support):
        new = support(row["current_group"],row["current_orientation"])
        old = max(support(row["old_group"], strand) for strand in ("+", "-"))
        row.update(new_direct_chain_bp=new, old_best_direct_chain_bp=old, verdict=classify(row, new, old))
    measure_rows(base, primary, compare)
    return output


def measure_rows(base, rows, consume):
    """Measure actual screened high-MAPQ collinear blocks on each source interval."""
    from lgz_core import q0_admission as A, q0_collinear as C
    from lgz_core.q0_retained_hits import _checked_line, retained_names, retained_geometry_cache
    from lgz_core.q0_sources import SourceKey, Interval
    import wheat_production22_cached as whole
    disputes = defaultdict(list)
    for row in rows:
        disputes[SourceKey(*row["source"])].append(row)
    if not disputes:
        return
    snap, root, index, ordered, _ = whole.frozen.bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",
                                                       base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    files = {r["path"]: r for r in snap["files"]}
    lookup = {ordered[rank]: (part, n, digest) for part, (rank, n, digest) in index.items()}
    def fai(rel):
        data = whole.frozen.bounded(root/rel, 16 << 20, files[rel]["sha256"])
        return {k: tuple(map(int, f[:4])) for k, *f in (line.split("\t") for line in data.decode().splitlines())}
    ref, = whole.frozen.prep.table(root, "metadata/reference.tsv", ("fai_relpath",))
    targets = retained_names({k: v[0] for k, v in fai(ref["fai_relpath"]).items()})
    policy = A.AdmissionPolicy()
    for ds in sorted({k.dataset for k in disputes}):
        fa = "data/datasets/" + ds + ".fa"; ix = fai(fa + ".fai")
        names = retained_names({k: v[0] for k, v in ix.items()})
        rel = "runs/" + ds + "_vs_ref/result.paf"; prefix = b"[" + json.dumps(rel).encode() + b","; digest = sha256()
        wanted = {k.contig: [] for k in disputes if k.dataset == ds}; cache = retained_geometry_cache()
        with (root/rel).open("rb") as stream:
            for number, line in enumerate(stream, 1):
                digest.update(line); name = line.split(b"\t", 1)[0].decode()
                if name in wanted:
                    wanted[name].append(_checked_line(line.decode(), root/rel, rel, number, prefix, names, targets, cache))
        whole.require(digest.hexdigest() == files[rel]["sha256"], "reference PAF changed: " + ds)
        with (root/fa).open("rb") as stream:
            for contig, hits in wanted.items():
                key = SourceKey(ds, contig); pid, n, dna_sha = lookup[key]; length, offset, bases, width = ix[contig]
                whole.require(length == n, "source length changed")
                stream.seek(offset); dna = stream.read((n-1)//bases*width + (n-1)%bases + 1).replace(b"\n", b"").replace(b"\r", b"").upper()
                whole.require(sha256(dna).hexdigest() == dna_sha, "source DNA changed")
                part = SimpleNamespace(source=key, segment_id=pid, interval=Interval(0,n))
                data = SimpleNamespace(sources={key:dna.decode()}, reference_hits={key:hits})
                groups, _, _, _ = A._request_reference_screen(data, part, policy)
                high = {h.evidence_id for h in hits if h.mapping_quality is not None and h.mapping_quality >= policy.minimum_reference_mapq}
                def measure(chrom, strand, iv):
                    anchors = (a for a in groups.get((chrom,strand), ()) if a.evidence_id in high)
                    return C.size(a.source for a in C.chain(C.clipped(anchors, iv, strand), strand))
                for row in disputes[key]:
                    iv = Interval(*row["interval"]); whole.require(part.interval.contains(iv) and iv.length == row["bp"], "invalid disputed interval")
                    consume(row, lambda chrom, strand: measure(chrom, strand, iv))


def slices(path):
    return [(p.source.dataset, p.source.contig, p.orientation, p.interval.start, p.interval.end) for p in path.slices] if path else []


def ng50(lengths, reference_length):
    if type(reference_length) is not int or reference_length <= 0:
        raise ValueError("invalid chromosome length")
    total = 0
    for bp in sorted(lengths, reverse=True):
        total += bp
        if 2*total >= reference_length:
            return bp
    return 0


def control_group(old, new, before, after, reference_length):
    def contains(a, b):
        return a[:3] == b[:3] and a[3] <= b[3] < b[4] <= a[4]
    def summary(rows, m):
        lengths = [b-a for _,_,_,a,b in rows]
        if not rows or not m["has_path"] or sum(lengths) != m["selected_source_bp"] or len(rows) != m["slices"]:
            raise ValueError("control slice/metric mismatch")
        return {**{k:m[k] for k in ("selected_source_bp", "selected_reference_bp", "slices", "source_slice_n50")},
                "ng50":ng50(lengths, reference_length)}
    a, b = summary(old,before), summary(new,after)
    missing = [o for o in old if not any(contains(n,o) for n in new)]
    added = [n for n in new if not any(contains(n,o) for o in old)]
    return dict(baseline=a, candidate=b, reference_length_bp=reference_length, missing_baseline_slices=missing,
                added_slices=added, added_slice_lengths_bp=sorted((n[4]-n[3] for n in added),reverse=True),
                passed=not missing and all(b[k]>=a[k] for k in ("selected_source_bp","selected_reference_bp","ng50")))


CARRIER_BP = 100_000
CARRIER_POLICY = "local_chain_carrier_100kb_supported_debris_ng50_v2"


def carrier_group(old, new, before, after, reference_length):
    result = control_group(old, new, before, after, reference_length)
    missing = set(map(tuple, result.pop("missing_baseline_slices")))
    carriers = [r for r in old if r[4]-r[3] >= CARRIER_BP]
    result.update(baseline_carriers=len(carriers), missing_carriers=[r for r in carriers if tuple(r) in missing],
                  short_slices=[dict(source=[ds,ctg], orientation=strand, interval=[a,b], bp=b-a,
                                     intact=(ds,ctg,strand,a,b) not in missing)
                                for ds,ctg,strand,a,b in old if b-a < CARRIER_BP])
    del result["passed"]  # No verdict until missing short intervals are independently audited.
    return result


def assess_carriers(base, groups, *, measure=measure_rows):
    pending = []
    for chrom, row in groups.items():
        for piece in row["short_slices"]:
            if not piece["intact"]:
                piece["baseline_group"] = chrom
                pending.append(piece)
    def record(piece, support):
        counts = {st:support(piece["baseline_group"], st) for st in ("+", "-")}
        if not all(type(n) is int and 0 <= n <= piece["bp"] for n in counts.values()):
            raise ValueError("invalid short-slice support")
        piece["local_high_mapq_chain_bp"] = counts
        piece["unsupported_at_old_locus"] = max(counts.values()) == 0
    measure(base, pending, record)
    for row in groups.values():
        row["passed"] = (not row["missing_carriers"] and all(p["intact"] or p["unsupported_at_old_locus"] for p in row["short_slices"])
                         and all(row["candidate"][k] >= row["baseline"][k] for k in ("selected_source_bp","selected_reference_bp","ng50")))
    return all(r["passed"] for r in groups.values())


def carrier_controls(owner, candidate, paths):
    # Reuse the frozen checkpoint and FAI readers, never the producer's pass/fail bit.
    import wheat_source_collision_controls as frozen
    whole = frozen.whole
    old = Path((owner/"baseline-owner").read_text().strip())
    whole.require(old == owner.parent/frozen.OLD_OWNER and old.resolve() == old, "wrong control owner")
    before = frozen.metrics(old, frozen.OLD_KIT, geometry=True)["groups"]
    # Read the same pinned reference FAI in the validator and independent relay.
    base = owner.parent
    snap, root, _, _, _ = whole.frozen.bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    ref, = whole.frozen.prep.table(root, "metadata/reference.tsv", ("fai_relpath",))
    f, = [r for r in snap["files"] if r["path"] == ref["fai_relpath"]]
    lengths = {k:int(n) for k,n,*_ in (l.split("\t") for l in whole.frozen.bounded(root/f["path"], 16<<20, f["sha256"]).decode().splitlines())}
    groups = {k:carrier_group(before[k]["geometry"], slices(paths[k]), before[k], candidate[k], lengths[k]) for k in frozen.CONTROLS}
    return dict(policy=CARRIER_POLICY, minimum_carrier_bp=CARRIER_BP, baseline_job=43225037,
                baseline_group_009=frozen.OLD_GROUP_009, groups=groups, passed=assess_carriers(base, groups))
