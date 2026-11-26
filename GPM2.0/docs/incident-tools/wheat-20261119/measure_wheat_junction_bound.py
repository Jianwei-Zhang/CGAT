"""Read only the sealed wheat admissions, selected paths and residual questions. No mapper."""
from collections import Counter, defaultdict
from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path
import sys

from lgz_core.q0_junction_review import covering_alternatives, possible_window
from lgz_core.q0_paths import PathPolicy, Placement
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import decode, need

SUMMARY = "ef67a79f96a87adb9cd13d86c652b0fe4c6b769a717d5ddadda9196414eabffa"


def frozen(folder, result):
    summary = checked(result / "summary.json", SUMMARY)
    detail = checked(result / "updated-questions.json.gz", summary["questions"])
    binding = ["whole-wheat-updated-supplement-v1", *(summary[k] for k in
               ("inputs", "first_request", "regional_inventory", "kit_sha256", "evidence_digest")), 32]
    previous = ""

    def walk(name):
        nonlocal previous
        with (folder/name).open("rb") as f:
            raw = f.readline(); header = json.loads(raw)
            need(header[:3] == ["wheat_first_request_checkpoint_v1", binding, name]
                 and header[-1] == previous, "wrong frozen prefix")
            digest = sha256(raw); n = 0
            while True:
                pos = f.tell(); raw = f.readline(); obj = json.loads(raw)
                if isinstance(obj, list):
                    need(obj == ["end", n, digest.hexdigest()] and not f.read(1), "incomplete checkpoint")
                    previous = obj[-1]; return
                digest.update(raw); n += 1
                yield pos, obj

    positions = defaultdict(list)
    chrom = [f.name for f in fields(Placement)].index("chromosome")
    for pos, row in walk("admission.jsonl"):
        positions[row["Placement"][chrom]].append(pos)
    paths = []
    for i in range(1, 23):
        (_, row), = walk(f"group-{i:03}.jsonl")
        paths.append(decode(row).path)
    need(previous == summary["selection_chain"], "wrong final path digest")
    return summary, detail, positions, paths


def measure(folder, result):
    summary, detail, positions, paths = frozen(folder, result)
    issues = detail["issues"]
    weak = {x["id"] for x in issues if x["kind"] == "weak_placement"}
    unknown = {x["id"] for x in issues if x["kind"] == "unproven_join"}
    occupied = defaultdict(list)
    for path in paths:
        for s in path.slices: occupied[s.source].append(s.interval)
        for j in path.joins:
            if j.gap_source is not None: occupied[j.gap_source].append(j.gap_interval)
    minimum = PathPolicy().minimum_anchor_bp
    windows = set(); counts = Counter(); by_chr = {}
    with (folder/"admission.jsonl").open("rb") as f:
        for path in paths:
            ps = {}; sites = {}; where = {}; previous = len(windows)
            for pos in positions[path.chromosome]:
                f.seek(pos); p = decode(json.loads(f.readline())); ps[p.placement_id] = p
            for i, s in enumerate(path.slices):
                if s.placement_id not in weak and any(j.join_id in unknown for j in path.joins[max(i-1,0):i+1]):
                    sites[s.placement_id] = ps[s.placement_id], s; where[s.placement_id] = i
            counts["supported_at_unproven_join"] += len(sites)
            for pid, alt in covering_alternatives(sites, ps.values(), set(path.nodes), minimum):
                counts["two_end_candidates"] += 1
                if any(alt.interval.intersection(s) for s in occupied[alt.source]): continue
                i = where[pid]; neighbors = []
                if i: neighbors.append((ps[path.nodes[i-1]], alt, path.joins[i-1]))
                if i+1 < len(path.nodes): neighbors.append((alt, ps[path.nodes[i+1]], path.joins[i]))
                possible = {possible_window(l, r, minimum) for l, r, j in neighbors if j.join_id in unknown} - {None}
                if possible:
                    windows.update(possible); counts["geometry_pairs_with_possible_local_probe"] += 1
            by_chr[path.chromosome] = len(windows) - previous
    return dict(counts=counts, unknown_joins=len(unknown), eligible_local_windows_upper=len(windows),
                query_bp_upper=sum(k.query_span.length for k in windows),
                target_bp_upper=sum(k.target_span.length for k in windows), first_seen_group_counts=by_chr,
                selection_chain=summary["selection_chain"], questions=summary["questions"], mapper_starts=0)


if __name__ == "__main__":
    folder, result = map(Path, sys.argv[1:]); print(json.dumps(measure(folder, result), sort_keys=True, indent=2))
