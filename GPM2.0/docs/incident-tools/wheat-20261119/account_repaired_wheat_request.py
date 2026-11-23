"""Count the latest whole-wheat demand against the ORIGINAL plan, without rerunning a mapper.

Run bind under the request producer; run count under the frozen historical planner.
Only the latter may reconstruct missing historical target geometry. Neither writes to the run.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from census_wheat_q0_fork import GEOM, LOOK, SNAP, bind, bounded, require
from lgz_core.q0_threshold_acceptance import decode


CURRENT = "1d66bcfce3d1cf96cfcb10984540a300678b3e1fd683ba9a84581be64a98b74d"
REVISION = "612cbce944c3443d5d5458741dc57e08330e1c97"
AXES_RECEIPT = "0a2d812b579ba13c27cda84e274d7244a86b2b1c6a5dacbb1aba9405fb3c239a"


def write(path, doc):
    temporary = path.with_suffix('.partial'); payload = (json.dumps(doc, sort_keys=True, indent=2)+'\n').encode()
    with temporary.open('xb') as f:
        f.write(payload)
    os.link(temporary, path); temporary.unlink()


def inputs(base, ctrl, out):
    old = base / "q0-latest-fork-20261123-1435/control/snapshot.json"
    original = json.loads(bounded(old, 256 << 10, SNAP))
    latest = json.loads(bounded(ctrl / "snapshot.json", 256 << 10, CURRENT))
    require(latest == dict(original, revision=REVISION), "historical plan not reusable: producer inputs differ")
    for protected in (Path(original["source"]), ctrl, old.parent):
        require(not out.is_relative_to(protected) and not protected.is_relative_to(out), "unsafe output directory")
    raw = bounded(ctrl / "global-first-request.json", 64 << 20); req = json.loads(raw)
    require(req["schema"] == "wheat_threshold_global_first_request_v1" and req["revision"] == REVISION
            and req["snapshot_sha256"] == CURRENT and req["published_q0"] is False and type(req["has_path"]) is bool
            and type(req["mapper_calls"]) is int and req["mapper_calls"] == 0, "wrong or published first request")
    return old, req, {"revision": REVISION, "snapshot_sha256": CURRENT, "inventory_snapshot_sha256": SNAP,
                      "request_sha256": sha256(raw).hexdigest(), "has_path": req["has_path"]}


def main(mode, base, ctrl, out):
    old, req, stamp = inputs(base, ctrl, out)
    if mode == "bind":
        from lgz_core.q0_preparation import supplement_policy
        require(req["threshold_contract"] == supplement_policy("positive_threshold")["decision_frontier"],
                "request does not match the deployed selector and threshold contract")
        write(out / "bound.json", stamp); return
    require(mode == "count" and json.loads(bounded(out / "bound.json", 1 << 20)) == stamp, "unbound request")
    from check_wheat_inverse_targets import axes, init_worker, intersects, inverse_group, invert, lookups, reference
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    from measure_replayed_wheat_demand import QUERIES, REPLAY, account
    from replay_wheat_partial_queries import AXES
    from lgz_core.common import stable_id

    frozen, root, parts, order, lengths = bind(old, base / "q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    demand = decode(req["request"], lengths)
    kind = ("full_fallback" if demand is None else "localized" if demand else
            "base_only" if req["has_path"] else "no_supported_backbone")
    plan = base / "q0-fork-partial-queries-20261123-1556/plan"
    replay = json.loads(bounded(plan / "replay.json", 1 << 20, REPLAY))
    require(replay["snapshot"] == SNAP and replay["count_matches"] is True and
            replay["logged_plan_count"] == replay["replayed_query_count"] == 61000, "wrong query plan")
    report = {**stamp, "request_kind": kind, "historical_planned_queries": 61000,
              "requested_sources": None if demand is None else len(demand),
              "requested_intervals": None if demand is None else sum(map(len, demand.values())),
              "requested_bp": None if demand is None else sum(i.length for v in demand.values() for i in v),
              "replay_sha256": REPLAY, "limits": "Initial demand on historical partial-window geometry only; not actual mapper calls, final Q0, or wall time."}
    if kind != "localized":
        write(out / "first-demand.json", report); return
    census = base / "q0-fork-window-census-20261123-1505/census"
    meta = json.loads(bounded(census / "axes-receipt.json", 1 << 20, AXES_RECEIPT)); arc = census / "axes.bin.gz"
    require(meta["snapshot"] == SNAP and meta["lookup"] == LOOK and meta["source"] == str(root) and
            meta["uncompressed_sha256"] == AXES and meta["count"] == 23845, "wrong frozen context geometry")
    hist = Counter(); idx = lookups(demand, order)
    known_geom = {}; check = {}; controls = Counter()
    def classify(_, qid, data):
        rows = GEOM.iter_unpack(data); geom = next(rows); q = intersects(geom, idx); t = any(intersects(g, idx) for g in rows)
        known_geom[qid] = geom
        if controls[t] < 32:
            check[qid] = t; controls[t] += 1
        hist["both" if q and t else "query_only" if q else "target_only" if t else "omitted"] += 1
    known = axes(arc, classify)
    by_rank = sorted(parts, key=lambda p: parts[p][0]); seen = set(); digest = sha256(); direct = 0
    groups = defaultdict(list)
    for line in gzip.decompress(bounded(plan / "queries.tsv.gz", 8 << 20, QUERIES)).splitlines(keepends=True):
        digest.update(line); name, rank, a, b = line.decode().split(); r, a, b = map(int, (rank, a, b))
        require(0 <= r < len(order) and 0 <= a < b <= lengths[order[r]], "query out of bounds")
        require(name == stable_id("q0-query-window", {"segment_id": by_rank[r], "segment_length": lengths[order[r]],
                                                       "start": a, "end": b}), "mismatched historical query")
        qid = bytes.fromhex(name.rsplit("-", 1)[1]); require(qid not in seen, "duplicate query"); seen.add(qid)
        hit = intersects((r, a, b), idx); direct += hit
        if qid in known:
            require(known_geom[qid] == (r, a, b), "known query geometry mismatch")
            if qid not in check:
                continue
        elif hit:
            continue  # A query hit already retains the window regardless of its targets.
        groups[by_rank[r]].append((qid, by_rank[r], a, b))
    require(known <= seen and len(seen) == 61000 and digest.hexdigest() == replay["queries_uncompressed_sha256"], "incomplete replay")
    counts = {"accounting": account(kind, len(seen), direct, len(known), hist)}
    report.update(counts, observed_contexts=len(known), observed_axes=dict(hist), axes_sha256=AXES)
    write(out / "observed.json", report)
    todo = {row[0] for rows in groups.values() for row in rows}
    acc = counts["accounting"]; other = acc["without_target_inventory_needs_target_check"]
    require(len(todo) == other + len(check), "inverse lookup inventory mismatch")
    kept_by_target = 0
    if other:
        print(f"Checking {other} unseen query-side misses and {len(check)} observed target controls", flush=True)
        with TemporaryDirectory(prefix="wheat-demand-", dir="/tmp") as tmp, reference(frozen,root,parts,order,lengths,Path(tmp)) as index:
            mask = invert(index, demand)
            with ProcessPoolExecutor(4, mp_context=get_context('spawn'), initializer=init_worker,
                                     initargs=(index.reader_snapshot(), mask)) as pool:
                batches = (rows[i:i+64] for rows in groups.values() for i in range(0,len(rows),64))
                for batch in pool.map(inverse_group, batches, chunksize=8):
                    for qid, hit in batch:
                        require(qid in todo and type(hit) is bool, "unexpected or duplicate inverse result")
                        todo.remove(qid)
                        if qid in check:
                            require(hit is check[qid], "inverse disagrees with actual historical targets")
                        else:
                            kept_by_target += hit
        require(not todo, "incomplete inverse result")
    keep = acc["known_either_axis"] + acc["without_target_inventory_query_intersects"] + kept_by_target
    omit = acc["known_neither_axis"] + other - kept_by_target
    require(keep + omit == len(seen), "final counts do not cover original plan")
    report["partial_geometry"] = {"query_or_target_hit":keep, "neither_axis_hit":omit,
                                  "unseen_target_only":kept_by_target, "frozen_target_controls":len(check) if other else 0}
    write(out / "first-demand.json", report)


if __name__ == "__main__":
    main(sys.argv[1], *(Path(arg).resolve(strict=True) for arg in sys.argv[2:]))
