"""Profile a bounded prefix, never validate/adopt a whole mapping cache.

Uses the real strict parser, observed-pair/coverage consumer and query projection.
The reference-anchor catalog/fanout, DNA loading, full-file hashing and mapper are
NOT exercised. This is diagnostic evidence, not a whole-job speed comparison.
Pass a complete Server tools package: lgz_core.__init__ imports stage resources.
"""
import argparse
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import resource
import socket
import sys
import time

LOOKUP_SHA = "2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def consume_prefix(path, parse, query_lengths, target_lengths, consume, *, artifact,
                   max_records, max_bytes, max_line_bytes):
    """Stop before parsing a truncated/over-budget line; never claim tail validity."""
    if not (0 < max_records <= 20_000 and 0 < max_line_bytes <= max_bytes <= 64*1024**2):
        raise ValueError("invalid bounded diagnostic limits")
    prefix = hashlib.sha256(); records = hashlib.sha256()
    count = used = lines = 0; reason = "eof"
    with Path(path).open(encoding="utf-8", newline="") as stream:
        while True:
            if count >= max_records:
                reason = "record_limit"; break
            remaining = max_bytes-used
            if remaining <= 0:
                reason = "byte_limit"; break
            cap = min(max_line_bytes, remaining)+1
            line = stream.readline(cap)
            if not line:
                break
            raw = line.encode("utf-8")
            if len(raw) > remaining:
                reason = "byte_limit_before_record"; break
            if len(raw) > max_line_bytes or (len(line) == cap and not line.endswith(("\n", "\r"))):
                reason = "line_limit_before_record"; break
            lines += 1; used += len(raw); prefix.update(raw)
            if not line.strip() or line.startswith("#"):
                continue
            hit = parse(line, artifact=artifact, line_number=lines)
            if (query_lengths.get(hit.query_name) != hit.query_length
                    or target_lengths.get(hit.target_name) != hit.target_length):
                raise ValueError("prefix PAF names/lengths differ from declared inputs")
            consume(hit); records.update(hit.record_sha256.encode("ascii")); count += 1
    return {"records":count, "processed_bytes":used, "processed_lines":lines,
            "stop_reason":reason, "prefix_sha256":prefix.hexdigest(),
            "ordered_record_digest":records.hexdigest(), "whole_cache_validated":False}


def profile_rows(profile, key):
    rows = []
    for (filename, line, function), (primitive, calls, own, cumulative, _callers) in pstats.Stats(profile).stats.items():
        rows.append({"file":filename, "line":line, "function":function,
                     "primitive_calls":primitive, "calls":calls,
                     "self_seconds":own, "cumulative_seconds":cumulative})
    return sorted(rows, key=lambda row:row[key], reverse=True)[:35]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "package-dir", "lookup"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--task-id", default="q0-map-8024dde83cbf20e7ffa6d8ee")
    p.add_argument("--max-records", type=int, default=5000)
    p.add_argument("--max-bytes", type=int, default=16*1024**2)
    p.add_argument("--max-line-bytes", type=int, default=4*1024**2)
    a = p.parse_args()
    root = a.workspace.resolve(strict=True)
    if Path.cwd().resolve().is_relative_to(root):
        raise ValueError("diagnostic output must be outside primary workspace")
    if "/" in a.task_id or not a.task_id.startswith("q0-map-"):
        raise ValueError("unsafe task ID")
    sys.path.insert(0, str(a.package_dir.resolve(strict=True)))
    from lgz_core.common import stable_id
    from lgz_core.q0_alignments import parse_paf_line
    from lgz_core.q0_catalog import ObservedSourcePairs
    from lgz_core.q0_sources import SourceKey
    relative = "grt/evidence/q0_prepare/tasks/"+a.task_id
    directory = root/relative; marker = directory/"success.json"; paf = directory/"result.paf"
    for path in (directory, marker, paf):
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("linked/escaped diagnostic input")
    receipt = json.loads(marker.read_text()); spec = receipt["spec"]
    if (receipt.get("status") != "success" or spec.get("schema") != "lgz_q0_mapping_v1"
            or stable_id("q0-map", spec) != a.task_id):
        raise ValueError("not a declared complete mapping task")
    if digest(a.lookup) != LOOKUP_SHA:
        raise ValueError("source-part metadata changed")
    lookup = json.loads(a.lookup.read_text()); parts = {}
    for key in set(spec["query_ids"]+spec["target_ids"]):
        row = lookup[key]; source = SourceKey(row["dataset"],row["contig"])
        n = row["length"]; identity = row["sequence_sha256"]
        if stable_id("q0-source-part",[source.dataset,source.contig,0,n,identity]) != key:
            raise ValueError("diagnostic supports canonical whole-source parts only")
        parts[key] = (source,n)
    observed = ObservedSourcePairs({s:n for s,n in parts.values()})
    query_lengths = {key:parts[key][1] for key in spec["query_ids"]}
    target_lengths = {key:parts[key][1] for key in spec["target_ids"]}
    intervals = paired_bases = 0
    def consume(hit):
        nonlocal intervals, paired_bases
        observed.observe_alignment(hit,parts[hit.query_name][0],parts[hit.target_name][0])
        values = tuple(hit.paired_query_intervals())
        intervals += len(values); paired_bases += sum(i.length for i in values)
    paths = (marker,paf,a.lookup)
    before = [stamp(path) for path in paths]; marker_sha = digest(marker)
    profiler = cProfile.Profile(); started = time.monotonic(); profiler.enable()
    try:
        result = consume_prefix(paf,parse_paf_line,query_lengths,target_lengths,consume,
            artifact=relative+"/result.paf",max_records=a.max_records,
            max_bytes=a.max_bytes,max_line_bytes=a.max_line_bytes)
    finally:
        profiler.disable()
    seconds = time.monotonic()-started
    if not result["records"]:
        raise ValueError("no complete record fits the diagnostic bounds")
    if before != [stamp(path) for path in paths] or digest(marker) != marker_sha:
        raise ValueError("diagnostic inputs changed")
    coverage = stable_id("prefix-coverage",[[s.dataset,s.contig,[[i.start,i.end] for i in values]]
                        for s,values in sorted(observed.cross_coverage.items())])
    report = {"status":"bounded_prefix_profile_only", **result,
        "hostname":socket.gethostname(), "python":sys.version, "task_id":a.task_id,
        "paf_total_bytes":paf.stat().st_size, "task_success_marker_sha256":marker_sha,
        "alignment_flags":spec.get("alignment_flags"),
        "lookup_sha256":LOOKUP_SHA, "limits":{"records":a.max_records,"bytes":a.max_bytes,"line_bytes":a.max_line_bytes},
        "profiled_seconds":seconds, "profiling_overhead_included":True,
        "peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        "observed_relations":len(observed), "coverage_digest":coverage,
        "projected_intervals":intervals, "projected_paired_bases":paired_bases,
        "top_cumulative":profile_rows(profiler,"cumulative_seconds"),
        "top_self":profile_rows(profiler,"self_seconds"),
        "source_sha256":{path.name:digest(path) for path in (a.package_dir/"lgz_core").glob("*.py")},
        "anchor_catalog_fanout_profiled":False, "whole_dna_heap_loaded":False,
        "mapper_executed":False, "primary_workspace_modified":False,
        "whole_wheat_speedup_claimed":False}
    with Path("profile.json").open("x") as f:
        json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("source_sha256","top_cumulative","top_self")}),flush=True)


if __name__ == "__main__":
    main()
