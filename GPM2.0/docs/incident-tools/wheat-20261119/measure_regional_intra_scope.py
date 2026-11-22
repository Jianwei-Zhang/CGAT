"""Read input scopes of completed wheat windows; don't map or read sequences.

Only a pure within-assembly target list permits a mapper-level fast parameter
without first changing the mixed target context. Counts here are scope/ROI
observations from frozen cohorts, not tested placement or precision equivalence.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, TRACE_SHA, within


RAW_PATH = re.compile(r"grt/evidence/q0_prepare/regional/q0-regional-context-[0-9a-f]{24}/q0-regional-raw-[0-9a-f]{24}/success\.json")


def bound_json(path, sha, maximum, size=None):
    st = path.stat()
    if path.is_symlink() or st.st_size > maximum or (size is not None and size != st.st_size):
        raise ValueError(f"unbounded, linked or invalid input: {path}")
    raw = path.read_bytes()
    if len(raw) != st.st_size or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f"bound input bytes changed: {path}")
    return json.loads(raw)


def geometry(window, lookup):
    key = window["segment_id"]
    part = lookup[key]
    lo, hi, length = (window[f] for f in ("start", "end", "segment_length"))
    if (any(type(n) is not int for n in (lo, hi, length)) or not 0 <= lo < hi <= length
            or length != part["length"] or not isinstance(part["dataset"], str) or not part["dataset"]):
        raise ValueError("unbound regional source geometry")
    return key, part["dataset"], hi-lo


def scope(context, lookup):
    query, dataset, _ = geometry(context["query"], lookup)
    targets = context["targets"]
    if not targets or len({t["window_id"] for t in targets}) != len(targets):
        raise ValueError("empty or repeated regional window targets")
    by_scope, counts = Counter(), Counter()
    members = {query}
    for target in targets:
        key, target_dataset, bases = geometry(target, lookup)
        if key == query:
            raise ValueError("source compared to itself")
        kind = "intra" if target_dataset == dataset else "cross"
        by_scope[kind] += bases
        counts[kind] += 1
        members.add(key)
    if context["members"] != [[k, lookup[k]["sequence_sha256"]] for k in sorted(members)]:
        raise ValueError("regional member hashes not linked to original parts")
    if sum(by_scope.values()) > 100_000_000:
        raise ValueError("regional target extent outside measured bound")
    kind = "mixed" if len(by_scope) == 2 else next(iter(by_scope)) + "_only"
    return {"scope": kind, "target_bp": dict(by_scope), "target_windows": dict(counts), "query_dataset": dataset}


def measure(work, lookup, probes):
    rows, seen = [], set()
    for row in probes:
        relative, sha = row["raw_receipt"], row["raw_receipt_sha256"]
        if not RAW_PATH.fullmatch(relative) or relative in seen:
            raise ValueError("invalid or repeated raw path")
        seen.add(relative)
        p = within(work, relative)
        raw = bound_json(p, sha, 2*1024**2)
        if raw["status"] != "success" or raw["spec"]["schema"] != "lgz_q0_regional_raw_v1":
            raise ValueError("not a complete regional raw receipt")
        c = raw["spec"]["context"]
        cp = within(work, c["path"])
        if cp != p.parent.parent/"context.json":
            raise ValueError("context not bound to raw receipt directory")
        defined = bound_json(cp, c["sha256"], 4*1024**2, c["size"])["spec"]
        cpu = row.get("cpu_seconds")
        wall = row.get("real_seconds")
        if any(n is not None and (type(n) not in (float, int) or not math.isfinite(n) or n < 0) for n in (cpu, wall)):
            raise ValueError("invalid historical native timings")
        rows.append({**scope(defined, lookup), "query_segment":defined["query"]["segment_id"],
                     "raw_receipt":relative, "raw_sha256":sha, "flags":raw["spec"]["flags"],
                     "native_cpu_s":cpu, "native_wall_s":wall})
    return rows


def summarize(rows):
    groups, cpu, bases = Counter(), Counter(), Counter()
    for row in rows:
        groups[row["scope"]] += 1
        if row["native_cpu_s"] is not None:
            cpu[row["scope"]] += row["native_cpu_s"]
        bases.update(row["target_bp"])
    slow = sorted((r for r in rows if r["native_wall_s"] is not None and r["native_wall_s"] >= 30),
                  key=lambda r:(-r["native_wall_s"], r["raw_receipt"]))
    return {"windows":len(rows), "window_scopes":dict(groups), "native_cpu_seconds_by_scope":dict(cpu),
            "whole_mapper_cpu_not_intra_cost":True, "target_bp":dict(bases),
            "slow_native_ge_30s_by_scope":dict(Counter(r["scope"] for r in slow)),
            "slowest_pure_intra": [r for r in slow if r["scope"] == "intra_only"][:8],
            "slowest_mixed_majority_intra_by_target_bp": [r for r in slow if r["scope"] == "mixed" and
                r["target_bp"]["intra"] >= r["target_bp"]["cross"]][:8],
            "m2000_in_receipt":sum(r["flags"][-2:] == ["-m", "2000"] for r in rows)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("workspace", "trace", "lookup", "output"):
        p.add_argument("--"+n, required=True, type=Path)
    args = p.parse_args()
    work = args.workspace.resolve(strict=True)
    out = args.output.resolve()
    if out.is_relative_to(work):
        raise ValueError("read-only probe must write outside the primary workspace")
    trace = bound_json(args.trace, TRACE_SHA, 8*1024**2)
    lookup = bound_json(args.lookup, LOOKUP_SHA, 16*1024**2)
    if len(trace["raw_markers"]) != 1189:
        raise ValueError("wrong recorded scope cohort")
    start = time.monotonic()
    rows = measure(work, lookup, trace["raw_markers"])
    result = {"status":"complete_archived_window_scope_audit_no_mapper", "summary":summarize(rows),
              "elapsed_s":time.monotonic()-start, "rows":rows, "workspace_modified":False,
              "limitations":["frozen 1189 completed windows, not a random sample of remaining windows",
                "target bp inventory is neither evidence utilization nor time spent on intra alignments",
                "pure intra is a scope condition only; independent support and placement/gap-fill impact not validated",
                "original complete PAF data not re-read; expected contexts and receipts rehashed"]}
    with out.open("x") as f:
        json.dump(result, f, indent=2); f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
