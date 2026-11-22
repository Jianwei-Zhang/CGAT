"""Read-only Q0 ablation on a complete, verified ready workspace.

The targeted arm masks whole regional tasks by *input* geometry against a
base-only path. It does not filter candidate hits or alter mapper contexts.
The archived task graph is fixed: this is not a prospective cost benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import time

from lgz_core.common import stable_id
from lgz_core.q0_admission import construct_q0, load_evidence_input
from lgz_core.q0_preparation import MANIFEST, artifact_path, identity, json_file
from lgz_core.q0_sources import Interval, Q0EvidenceError, merged_intervals, subtract_intervals


OPEN_JOIN_KINDS = frozenset({"reference_unknown", "input_assembly_gap"})


def decision_frontier(construction, flank_bp):
    """Demand at unfilled joins and path termini, in original source space."""
    if type(flank_bp) is not int or flank_bp < 1:
        raise ValueError("decision frontier flank must be a positive bp count")
    placements = {p.placement_id: p for p in construction.admission.placements}
    demand = defaultdict(list)

    def add(s, head):
        p = placements[s.placement_id]
        if s.source != p.source or s.orientation != p.orientation or not p.interval.contains(s.interval):
            raise Q0EvidenceError("q0 path slice geometry differs from its placement")
        low_side = head == (s.orientation == "+")
        cut = s.interval.start if low_side else s.interval.end
        # Keep a shoulder on *both* sides of a trimmed cut, when available
        # in the admitted placement. Do not cross the part's N-gap boundary.
        demand[s.source].append(Interval(max(p.interval.start, cut - flank_bp),
                                         min(p.interval.end, cut + flank_bp)))

    for result in construction.paths.values():
        p = result.path
        if not p:
            continue
        if len(p.slices) != len(p.joins) + 1:
            raise Q0EvidenceError("q0 path has mismatched slice and join counts")
        add(p.slices[0], True)
        add(p.slices[-1], False)
        for left, join, right in zip(p.slices, p.joins, p.slices[1:]):
            if join.kind in OPEN_JOIN_KINDS:
                add(left, False)
                add(right, True)
    return {k: merged_intervals(v) for k, v in demand.items()}


def member_geometry(row, parts):
    part = parts[row["segment_id"]]
    window = Interval(row["start"], row["end"])
    if row["segment_length"] != part.interval.length or window.end > part.interval.length:
        raise Q0EvidenceError("regional task window is outside the source segment")
    return part.source, Interval(part.interval.start + window.start, part.interval.start + window.end)


def projected_task(task, spec, parts, demand):
    """Keep both directions and the entire original target inventory."""
    if ({spec["query"]["segment_id"]} != set(task["query_ids"])
            or {r["segment_id"] for r in spec["targets"]} != set(task["target_ids"])):
        raise Q0EvidenceError("regional task inventory differs from its verified receipt")
    qsrc, qi = member_geometry(spec["query"], parts)
    tgts = [member_geometry(row, parts) for row in spec["targets"]]
    query = any(qi.intersection(i) for i in demand.get(qsrc, ()))
    target = any(span.intersection(i) for source, span in tgts for i in demand.get(source, ()))
    return {"query": query, "target": target, "query_bp": qi.length,
            "target_bp": sum(span.length for _, span in tgts),
            "raw": spec["raw_receipt"]["path"], "context": spec["context"]["path"]}


def task_plan(root, data, demand, output_ids):
    retained, skipped, full = set(), set(), set()
    inventory, counts = {}, Counter()
    for t in data.catalog["supplementary_alignments"]:
        paf = t["paf"]
        if paf in full:
            raise Q0EvidenceError("ablation requires unique supplementary PAF descriptors")
        full.add(paf)
        if t["kind"] != "regional_discovery":
            counts["native_tasks_retained"] += 1
            retained.add(paf)
            continue
        receipt = t["receipt"]
        expected = output_ids.get(receipt)
        if expected is None or identity(root, receipt) != expected:
            raise Q0EvidenceError("regional task receipt no longer matches the verified ready manifest")
        spec = json_file(artifact_path(root, receipt))["spec"]
        if identity(root, receipt) != expected:
            raise Q0EvidenceError("regional task receipt changed during decision replay")
        row = inventory[paf] = projected_task(t, spec, data.parts, demand)
        counts["regional_tasks"] += 1
        if row["query"] or row["target"]:
            counts["regional_retained"] += 1
            counts["regional_target_only_retained"] += row["target"] and not row["query"]
            retained.add(paf)
        else:
            skipped.add(paf)
    for kind in ("context", "raw"):
        original = {r[kind] for r in inventory.values()}
        kept = {inventory[paf][kind] for paf in retained if paf in inventory}
        counts[f"unique_{kind}"] = len(original)
        counts[f"unique_{kind}_omitted"] = len(original - kept)
    for kind in ("query_bp", "target_bp"):
        counts[f"projected_task_{kind}"] = sum(r[kind] for r in inventory.values())
        counts[f"projected_task_{kind}_omitted"] = sum(inventory[paf][kind] for paf in skipped)
    return full, retained, dict(counts)


def subset_input(data, keep):
    """No removed PAF records, derived discovery/rank catalog, or ready identity."""
    base = {r["paf"] for r in data.catalog["base_alignments"]}
    supplemental = {r["paf"] for r in data.catalog["supplementary_alignments"]}
    if base & supplemental or not keep <= supplemental:
        raise Q0EvidenceError("ambiguous q0 ablation PAF ownership")
    allowed = base | keep
    links = []
    removed_ids = set()
    for link in data.pair_links:
        if link.hit.artifact in allowed:
            links.append(link)
        elif link.hit.artifact in supplemental:
            removed_ids.add(link.hit.evidence_id)
        else:
            raise Q0EvidenceError("unaccounted PAF in verified q0 pair evidence")
    return replace(data, pair_links=tuple(links), catalog={}, ready_manifest_identity="",
                   evidence={k: v for k, v in data.evidence.items() if k not in removed_ids})


def path_facts(search):
    if search is None or search.path is None:
        return {}, set(), Counter()
    path = search.path
    coverage, accurate_joins, counts = defaultdict(list), set(), Counter()
    for s in path.slices:
        coverage[s.source, s.orientation].append(s.interval)
    for left, j, right in zip(path.slices, path.joins, path.slices[1:]):
        counts[j.kind] += 1
        if j.kind == "sequence_overlap":
            left_cut = left.interval.end if left.orientation == "+" else left.interval.start
            right_cut = right.interval.start if right.orientation == "+" else right.interval.end
            accurate_joins.add((left.source, left.orientation, left_cut, right.source, right.orientation, right_cut))
    return {k: merged_intervals(v) for k, v in coverage.items()}, accurate_joins, counts


def missing_bases(this, other):
    return sum(i.length for key, intervals in this.items() for span in intervals
               for i in subtract_intervals(span, other.get(key, ())))


def compare(full, arm):
    def unmapped_reference(result):
        return {c["chromosome"]: (sum(i["end"] - i["start"] for i in c["reference_unrepresented"])
                                  if "reference_unrepresented" in c else None)
                for c in result.decisions["chromosomes"]}

    full_unrepresented, alt_unrepresented = unmapped_reference(full), unmapped_reference(arm)
    rows = {}
    for chr_name in sorted(full.paths.keys() | arm.paths.keys()):
        coverage, joins, counts = path_facts(full.paths.get(chr_name))
        alt_coverage, alt_joins, alt_counts = path_facts(arm.paths.get(chr_name))
        rows[chr_name] = {
            "same_sequence": full.records.get(chr_name) == arm.records.get(chr_name),
            "full_constructed": chr_name in full.records,
            "arm_constructed": chr_name in arm.records,
            "full_join_kinds": dict(counts), "arm_join_kinds": dict(alt_counts),
            "full_reference_unrepresented_bp": full_unrepresented[chr_name],
            "arm_reference_unrepresented_bp": alt_unrepresented[chr_name],
            "changed_or_lost_overlap_cuts": len(joins - alt_joins),
            "changed_or_new_overlap_cuts": len(alt_joins - joins),
            "lost_or_reoriented_source_bp": missing_bases(coverage, alt_coverage),
            "new_or_reoriented_source_bp": missing_bases(alt_coverage, coverage),
        }
    return rows


def timed(data, allow_no_path=False):
    start = time.monotonic()
    try:
        result = construct_q0(data)
    except Q0EvidenceError as exc:
        if not allow_no_path or str(exc) != "no chromosome has a trustworthy q0 path":
            raise
        # No base path is a real negative arm. It does not authorize skipping
        # full discovery; there are no decision frontiers to restrict it to.
        return None, time.monotonic() - start
    return result, time.monotonic() - start


def replay(root, flank_bp):
    start = time.monotonic()
    data = load_evidence_input(root)
    load_seconds = time.monotonic() - start

    def check_manifest_binding():
        manifest = json_file(artifact_path(root, MANIFEST))
        if stable_id("q0-ready-evidence", manifest) != data.ready_manifest_identity:
            raise Q0EvidenceError("q0 ready manifest changed during decision replay")
        return {row["path"]: row for row in manifest["outputs"]}

    output_ids = check_manifest_binding()
    full, full_seconds = timed(data)
    base, base_seconds = timed(subset_input(data, set()), allow_no_path=True)
    if base is not None:
        demand = decision_frontier(base, flank_bp)
        full_pafs, retained, inventory = task_plan(root, data, demand, output_ids)
        if retained == full_pafs:
            target, target_seconds = full, None
        elif not retained:
            target, target_seconds = base, None
        else:
            target, target_seconds = timed(subset_input(data, retained), allow_no_path=True)
    else:
        demand, inventory, target, target_seconds = {}, {}, None, None
    check_manifest_binding()
    # Use the real checked input binding; never emit a filtered ready manifest.
    result = {"schema": "q0_decision_frontier_ablation_v1", "ready": data.ready_manifest_identity,
              "source_input": data.input_fingerprint, "flank_bp": flank_bp,
              "frontier_bp": sum(i.length for intervals in demand.values() for i in intervals),
              "load_seconds": load_seconds, "full_construction_seconds": full_seconds,
              "base_construction_seconds": base_seconds, "target_construction_seconds": target_seconds,
              "full_sequence_sha256": {k: sha256(v.encode("ascii")).hexdigest() for k, v in full.records.items()},
              "base_only_vs_full": compare(full, base) if base is not None else "no_path",
              "frontier_vs_full": compare(full, target) if target is not None else "no_path_or_requires_full_discovery",
              "projection_inventory": inventory,
              "limitations": ["task-graph replay, not prospective measured wall time",
                              "no construction QC/reads and no comparison of downstream donor validity",
                              "agreement with existing full paths does not establish biological truth"]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="complete ready Q0 evidence workspace; read-only")
    parser.add_argument("--flank-bp", type=int, default=100_000)
    args = parser.parse_args()
    print(json.dumps(replay(args.root.resolve(strict=True), args.flank_bp), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
