"""Cold, prospective full versus bounded Q0 proof repair on a frozen natural panel.

Uses the real planner, mapper, receipts, and selector. Only the lab adapter
substitutes the already-frozen panel for production outer checkpoints. The lab
scope identity includes the repair frontier and is rejected outside this probe.
Both arms start without mapping/index receipts, in separate private workspaces.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from threading import Lock
from time import monotonic
from unittest.mock import patch

from lgz_core import q0_admission as admission, q0_preparation as prep, q0_regional_mapping as mapping
from lgz_core.common import stable_id
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_frontier_scope import UnsearchedQ0Context, selected_proof_frontier
from lgz_core.q0_sources import Q0EvidenceError, merged_intervals
from probe_q0_decision_frontier import compare
from run_wheat_frontier_panel import base_input, digest, within


def expand_frontier(current, demand):
    if current is None:
        raise Q0EvidenceError("cannot repair a missing or full-scope Q0 frontier")
    expanded = {source: merged_intervals((*current.get(source, ()), *demand.get(source, ())))
                for source in current.keys() | demand.keys()}
    if expanded == current:
        raise Q0EvidenceError("Q0 proof repair would not widen the search")
    return expanded


def frontier_identity(frontier):
    return stable_id("cold-panel-repair", [[asdict(source), [[span.start, span.end] for span in spans]]
                                         for source, spans in sorted(frontier.items())])


def run_arm(panel, manifest, data, assignments, desc, root, mapper, threads, *, scoped, maximum_repairs):
    start = monotonic()
    for name, expected in manifest["artifacts"].items():
        src = within(panel, name)
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        if digest(dest) != expected:
            raise Q0EvidenceError("cold panel input changed")
    input_copy_s = monotonic() - start
    frontier = None
    chosen_scope = "decision_frontier" if scoped else "full"
    result = None
    reason = None
    phases = []
    original_policy, base_frontier = prep.supplement_policy, prep._provisional_frontier
    original_select, original_execute = admission.select_q0_paths, mapping._execute
    native_lock = Lock()

    def initial(path):
        if path != root:
            raise Q0EvidenceError("cold panel adapter called on another workspace")
        observed = ObservedSourcePairs({key: len(seq) for key, seq in data.sources.items()})
        for link in data.pair_links:
            observed.observe_alignment(link.hit, link.query_source, link.target_source)
        return (data.sources, data.reference_lengths, assignments, {"minimap_preset": "asm10"},
                sorted(manifest["artifacts"]), desc, observed)

    def load_fasta(path):
        if path == root / "reference-lengths.json":
            return [(name, range(length)) for name, length in data.reference_lengths.items()]
        # This adapter exists only because the frozen panel uses reference lengths, not a huge reference FASTA.
        from lgz_core.common import read_fasta
        return read_fasta(path)

    def planned_frontier(*args):
        nonlocal frontier
        if frontier is None:
            frontier = base_frontier(*args)
        return frontier

    def lab_policy(scope):
        policy = original_policy(scope)
        if scope == "full":
            return policy
        # On pass 0, the deterministic base frontier is not yet computed when the manifest is bound.
        tag = "initial_base_selector" if pass_number == 0 else frontier_identity(frontier)
        return {**policy, "decision_frontier": {**policy["decision_frontier"], "private_cold_panel": tag}}

    def save_selection(*args, **kwargs):
        nonlocal selection
        selection = original_select(*args, **kwargs)
        return selection

    def timed_execute(root, directory, *args, **kwargs):
        before = monotonic()
        result = original_execute(root, directory, *args, **kwargs)
        with native_lock:
            stage = "chaining" if directory.name == "chaining" else "exact"
            fresh[stage] += 1
            service[stage] += monotonic() - before
        return result

    start = monotonic()
    for pass_number in range((maximum_repairs if scoped else 0) + 1):
        selection = None
        fresh, service = Counter(), Counter()
        before = monotonic()
        with (patch.object(prep, "_initial_inputs", initial), patch.object(prep, "supplement_policy", lab_policy),
              patch.object(prep, "_provisional_frontier", planned_frontier),
              patch.object(mapping, "_execute", timed_execute)):
            ready = prep.prepare_evidence(root, threads=threads, minimap2=mapper, supplement_scope=chosen_scope)
            prepared = monotonic()
            with patch.object(admission, "read_fasta", load_fasta):
                observed = admission.load_evidence_input(root)
            loaded = monotonic()
            try:
                with patch.object(admission, "select_q0_paths", save_selection):
                    result = admission.construct_q0(observed)
            except UnsearchedQ0Context as exc:
                if not scoped or selection is None:
                    raise
                reason = str(exc)
            else:
                reason = None
        phase = {"pass": pass_number, "prepare_s": prepared-before, "load_verify_s": loaded-prepared,
                 "select_and_audit_s": monotonic()-loaded, "fresh_regional_mapper_calls": dict(fresh),
                 "regional_job_service_sum_s": dict(service), "ready": observed.ready_manifest_identity,
                 "supplementary_kinds": dict(Counter(task["kind"] for task in observed.catalog["supplementary_alignments"])),
                 "scope_details": {k:v for k,v in observed.catalog.get("supplement_scope", {}).items() if k != "unsearched_part_intervals"},
                 "omitted_windows": sum(observed.catalog.get(name,{}).get("frontier_omitted_windows",0)
                                        for name in ("regional_partial_discovery", "regional_candidate_discovery")),
                 "requires_more_context": reason}
        phases.append(phase)
        print("COLD_PASS", "targeted" if scoped else "full", json.dumps(phase, sort_keys=True), flush=True)
        if result is not None or pass_number == maximum_repairs:
            break
        frontier = expand_frontier(frontier, selected_proof_frontier(observed, selection.admission, selection.paths))
    return result, {"input_copy_s": input_copy_s, "wall_s": monotonic()-start, "phases": phases,
                    "terminal_guard": reason, "ready_catalog": ready["catalog"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mapper", type=Path, required=True)
    p.add_argument("--mapper-sha", required=True)
    p.add_argument("--threads", type=int, choices=(2,4,6), default=6)
    p.add_argument("--maximum-repairs", type=int, choices=(1,2,3), default=2)
    p.add_argument("--full-first", action="store_true")
    args = p.parse_args()
    panel, out, mapper = args.panel.resolve(strict=True), args.output.resolve(), args.mapper.resolve(strict=True)
    if out.exists() or out.is_relative_to(panel) or panel.is_relative_to(out) or not out.is_relative_to("/tmp"):
        raise ValueError("cold panel outputs need fresh, private scratch")
    if digest(mapper) != args.mapper_sha:
        raise Q0EvidenceError("cold panel mapper identity changed")
    start = monotonic()
    manifest = json.loads((panel / "panel.json").read_text())
    if manifest["panel"] != panel.name or any(digest(within(panel, name)) != expected for name, expected in manifest["artifacts"].items()):
        raise Q0EvidenceError("cold panel input is not bound")
    data, assignments, desc = base_input(panel, manifest)
    report = {"schema": "wheat_cold_frontier_proof_repair_v1", "input": data.input_fingerprint,
              "scope": "isolated real natural panel only; no production artifact",
              "common_input_load_s": monotonic()-start, "mapper_sha256": args.mapper_sha,
              "selector": admission.selector_identity(), "builder": prep.builder_identity(), "threads": args.threads}
    order = ("full", "targeted") if args.full_first else ("targeted", "full")
    report["arm_order"] = order
    results = {}
    for arm in order:
        results[arm], report[arm] = run_arm(panel, manifest, data, assignments, desc, out/arm, str(mapper), args.threads,
                                          scoped=arm=="targeted", maximum_repairs=args.maximum_repairs)
    if results["full"] is None or digest(mapper) != args.mapper_sha:
        raise Q0EvidenceError("cold full arm did not produce a valid result or mapper changed")
    report["targeted_vs_full"] = compare(results["full"], results["targeted"]) if results["targeted"] else None
    report["full_fasta_sha256"] = {c: sha256(v.encode("ascii")).hexdigest() for c,v in results["full"].records.items()}
    with (out/"report.json.tmp").open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        print(file=f)
    (out/"report.json.tmp").replace(out/"report.json")


if __name__ == "__main__":
    main()
