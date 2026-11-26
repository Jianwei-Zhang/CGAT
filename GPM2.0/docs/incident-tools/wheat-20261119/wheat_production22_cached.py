"""Production Q0 policy validation on all frozen evidence; no mapper or formal Q0.

The historical staging helper retains its input/content fences. This entry uses
an entire committed production tools tree, not a partial overlay on old tools.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import csv
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import refresh_whole_wheat_cached_demand as frozen
from wheat_selection_checkpoint import Store
from lgz_core import q0_admission as admission
from lgz_core.common import sha256_file
from lgz_core.q0_collinear import clipped, size
from lgz_core.q0_paths import PathPolicy
from lgz_core.q0_sources import Interval, SourceKey

BASELINE_SHA = "d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4"
OLD_ROUTE_SHA = "cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def old_routes(path):
    require(sha256_file(path) == OLD_ROUTE_SHA, "old Q0 comparator changed")
    routes = defaultdict(list)
    total = 0
    with path.open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["q_version"] != "q0" or row["segment_kind"] != "source":
                continue
            iv = Interval(int(row["source_start"]) - 1, int(row["source_end"]))
            require(iv.length == int(row["q_end"]) - int(row["q_start"]) + 1, "old coordinate convention")
            routes[SourceKey(row["dataset_name"], row["contig_name"])].append(
                (iv, row["chr"], row["orientation"]))
            total += iv.length
    require(total == 14097044589, "old Q0 source extent changed")
    return routes


def conflict_rows(source, interval, chromosome, orientation, routes):
    rows = []
    for prior, group, strand in routes.get(source, ()):
        overlap = prior.intersection(interval)
        if overlap is None or (group, strand) == (chromosome, orientation):
            continue
        rows.append(dict(source=[source.dataset, source.contig], interval=[overlap.start, overlap.end],
                         bp=overlap.length, current_group=chromosome, old_group=group,
                         current_orientation=orientation, old_orientation=strand,
                         category="other_chromosome" if group != chromosome else "opposite_orientation"))
    return rows


def n50(lengths):
    half = (sum(lengths) + 1) // 2
    cumulative = 0
    for length in sorted(lengths, reverse=True):
        cumulative += length
        if cumulative >= half:
            return length
    return 0


def read_selection(owner, groups, expected_summary_sha=None):
    summary_path = owner / "result/summary.json"
    if expected_summary_sha:
        require(sha256_file(summary_path) == expected_summary_sha, "frozen baseline summary changed")
    summary = json.loads(summary_path.read_text())
    folder = owner / "selection"
    with (folder / "admission.jsonl").open() as f:
        header = json.loads(f.readline())
    binding = header[1]
    require(binding == ["whole-wheat-local-supplement-v1", frozen.SN, frozen.REQ, frozen.FINAL,
                        summary["kit_sha256"], summary["evidence_digest"], 32], "wrong selection input binding")
    require(sha256_file(owner / "kit.sha256") == summary["kit_sha256"], "checkpoint kit changed")
    store = Store(folder, binding, False)
    admitted = store.load_admission()
    require(admitted is not None, "missing admission checkpoint")
    paths = {}
    for i, group in enumerate(groups, 1):
        result = store.load_group(i, group)
        require(result is not None, "missing group checkpoint: " + group)
        paths[group] = result.path
    require(store.previous == summary["selection_chain"], "selection chain incomplete")
    return admitted, paths, summary


def group_metrics(placements, path):
    selected_refs, lengths, joins = [], [], Counter()
    if path is not None:
        for piece in path.slices:
            p = placements[piece.placement_id]
            require(p.source == piece.source and p.interval.contains(piece.interval)
                    and p.orientation == piece.orientation, "foreign slice geometry")
            lengths.append(piece.interval.length)
            selected_refs.extend(a.reference for a in clipped(p.reference_blocks, piece.interval, p.orientation))
        joins.update(j.kind for j in path.joins)
    return dict(admitted_reference_bp=size(a.reference for p in placements.values() for a in p.reference_blocks),
                selected_reference_bp=size(selected_refs), selected_source_bp=sum(lengths),
                slices=len(lengths), source_slice_n50=n50(lengths), maximum_slice_bp=max(lengths, default=0),
                joins=dict(joins), has_path=path is not None)


def audit(base, owner):
    snapshot, root, _, _, _ = frozen.bind(base / "q0-latest-fork-20261123-1435/control/snapshot.json",
                                         base / "q0-source-part-lookup-20261121-1600/source-part-lookup.json")
    ref, = frozen.prep.table(root, "metadata/reference.tsv", ("fai_relpath",))
    identity, = [r for r in snapshot["files"] if r["path"] == ref["fai_relpath"]]
    require(frozen.prep.identity(root, identity["path"]) == identity, "reference FAI changed")
    lengths = {row[0]: int(row[1]) for row in (v.split("\t") for v in (root / identity["path"]).read_text().splitlines())}
    groups = sorted(lengths)
    require(len(groups) == 22, "not a full 22-group validation")
    old, old_paths, old_summary = read_selection(base / "q0-whole-local-maps.soHq9Z6J", groups, BASELINE_SHA)
    admitted, paths, summary = read_selection(owner, groups)
    require(summary["evidence_digest"] == old_summary["evidence_digest"], "evidence order or cohort changed")
    routes = old_routes(base / "q0-continuity-20261126.RAbGvNba/old-grt-q-segments.tsv")
    old_by_id = {p.placement_id: p for p in old.placements}
    by_group, old_by_group = defaultdict(dict), defaultdict(dict)
    for p in old.placements:
        old_by_group[p.chromosome][p.placement_id] = p
    inherited, new_conflicts, selected_conflicts = [], [], []
    for p in admitted.placements:
        by_group[p.chromosome][p.placement_id] = p
        rows = conflict_rows(p.source, p.interval, p.chromosome, p.orientation, routes)
        for row in rows:
            row["placement_id"] = p.placement_id
        (inherited if old_by_id.get(p.placement_id) == p else new_conflicts).extend(rows)
    results, occupied, overlaps = {}, defaultdict(list), []
    for group in groups:
        current = group_metrics(by_group[group], paths[group])
        baseline = group_metrics(old_by_group[group], old_paths[group])
        current.update(reference_length_bp=lengths[group], baseline=baseline,
                       reference_gain_bp=current["selected_reference_bp"] - baseline["selected_reference_bp"],
                       source_gain_bp=current["selected_source_bp"] - baseline["selected_source_bp"])
        results[group] = current
        path = paths[group]
        if path is None:
            continue
        for piece in path.slices:
            selected_conflicts.extend(conflict_rows(piece.source, piece.interval, group, piece.orientation, routes))
        entries = [(p.source, p.interval) for p in path.slices]
        entries += [(j.gap_source, j.gap_interval) for j in path.joins if j.gap_source is not None]
        for source, iv in entries:
            for previous_group, previous in occupied[source]:
                overlap = iv.intersection(previous)
                if overlap is not None:
                    overlaps.append(dict(source=[source.dataset, source.contig], groups=[previous_group, group],
                                         interval=[overlap.start, overlap.end]))
            occupied[source].append((group, iv))
    main = [str(n) + genome for n in range(1, 8) for genome in "ABD"]
    require(set(main) <= set(groups), "unexpected reference group names")
    result = dict(schema="wheat_production_continuity_22_v1", groups=results,
                  selector_identity=admission.selector_identity(), admission_policy=asdict(admission.AdmissionPolicy()),
                  path_policy=asdict(PathPolicy()), baseline_summary_sha256=BASELINE_SHA,
                  summary_sha256=sha256_file(owner / "result/summary.json"),
                  unchanged_frozen_candidate_conflicts=inherited, new_candidate_conflicts=new_conflicts,
                  selected_old_q0_conflicts=selected_conflicts, source_occupancy_conflicts=overlaps,
                  all_21_main_paths=all(results[g]["has_path"] for g in main), mapper_starts=0,
                  scientific_acceptance="PENDING_REVIEW", formal_q0_lgz="HOLD",
                  scope="Full production draft selector on frozen evidence; old Q0 is a comparator, not biological truth.")
    result["safety_checks_passed"] = (result["all_21_main_paths"] and not new_conflicts
                                        and not selected_conflicts and not overlaps)
    frozen.write(owner / "result/production22-audit.json", result)
    print("PRODUCTION22_AUDIT_DONE", json.dumps({g: r for g, r in results.items()}), flush=True)
    print("PRODUCTION22_SAFETY", result["safety_checks_passed"], "FORMAL_Q0_LGZ_HOLD", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("base", type=Path); p.add_argument("stage", type=Path); p.add_argument("owner", type=Path)
    args = p.parse_args()
    require(args.owner.parent == args.base and args.owner.resolve() == args.owner, "private sibling owner required")
    require(args.owner.stat().st_mode & 0o077 == 0, "owner not private")
    metadata = json.loads((args.owner / "production-source.json").read_text())
    require(sha256_file(args.owner / "tools.tgz") == metadata["tools_sha256"], "production source archive changed")
    require(admission.selector_identity() == metadata["selector_identity"], "loaded selector differs from sealed production source")
    require(asdict(admission.AdmissionPolicy()) == metadata["admission_policy"]
            and asdict(PathPolicy()) == metadata["path_policy"], "production policy changed")
    snapshot = json.loads(frozen.bounded(args.base / "q0-latest-fork-20261123-1435/control/snapshot.json", 256 << 10, frozen.SN))
    task, receipt_sha = next(iter(sorted(frozen.EXPECTED.items())))
    receipt = frozen.get(Path(snapshot["source"]) / "grt/evidence/q0_prepare/tasks" / task / "success.json", receipt_sha)
    tool = receipt["spec"]["tool"]
    binary = shutil.which("minimap2")
    require(binary and str(Path(binary).resolve()) == tool["resolved"]
            and sha256_file(Path(binary)) == tool["sha256"], "retained mapper binary identity changed")
    # Read the pinned successful receipt for version identity; do not even run
    # minimap2 --version. A missing cache can never launch an external mapper.
    def identity(command):
        require(command == "minimap2", "unexpected executable identity request")
        return dict(tool)
    with patch.object(subprocess, "Popen", side_effect=RuntimeError("external commands forbidden in cached validation")), \
         patch.object(frozen.prep, "executable_identity", side_effect=identity):
        frozen.run(args.base, args.stage, args.owner, 32, Path((args.owner / "local-mapping-owner").read_text().strip()))
        audit(args.base, args.owner)


if __name__ == "__main__":
    main()
