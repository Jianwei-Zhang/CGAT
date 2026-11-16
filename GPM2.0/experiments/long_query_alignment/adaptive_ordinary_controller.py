"""Finite calibration, whole-unit continuation and limited full-record review.

Internal orchestration: callers own an exclusive task lock. The package-bound
Server adapter enables this without user classification. Scientific accuracy is
not inferred from absence of screening flags. Budget exhaustion ends filtering,
not the task; actual failed native work never publishes a partial PAF.
"""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict
from pathlib import Path
import time
import sys

import adaptive_ordinary_units as units
import automatic_ordinary_pilot as pilot
import proactive_reference_plan as pp
import proactive_resume as pr
import windowed_alignment as wa

POLICY = "automatic-ordinary-controller-v1"
STATE = "ordinary-controller.json"


def automatic_budget():
    """Internal policy, never loaded from user/runtime cache metadata."""
    return pilot.Budget()


def execute(root, catalog, index, tool, args, *, budget=None,
            calibration_root=None, calibration_query=None, unit_bases=128_000_000,
            unit_limit=None, unit_seconds=2400, completed_units=None, readonly=False, primary_work=False):
    """Run the admitted internal policy without a whole-input parameter sweep.

    unit_limit is an internal bounded-development checkpoint, not a user choice.
    Review reservations survive hard kills; a failed review is never retried.
    The parent task lock must cover this call and any source adoption.
    """
    if unit_limit is not None and (type(unit_limit) is not int or unit_limit < 0):
        raise ValueError("nonnegative internal unit checkpoint required")
    if type(primary_work) is not bool or not (primary_work and unit_seconds is None) and (type(unit_seconds) is not int or unit_seconds < 1):
        raise ValueError("positive ordinary unit timeout required outside primary work")
    budget = automatic_budget() if budget is None else budget
    budget.checked(); catalog.require_unchanged()
    limits = pilot.quality.assignment_limits(getattr(args, "assignment_coverage", .60))
    def progress(message):
        if not readonly and getattr(args, "report_progress", False):
            print("CGAT automatic ordinary: " + message, file=sys.stderr, flush=True)
    records = [{"name": r.name, "length": r.length} for r in catalog.records]
    reference_bases = sum(r["length"] for part in index["parts"] for r in part["records"])
    plan = pilot.plan(reference_bases, records, explicit_filter=getattr(args, "minimap_filter", None), budget=budget)
    if not plan["enabled"]:
        return {"status": "not_triggered", "plan": plan, "mapping_commands": 0}
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked ordinary controller directory")
    root = root.resolve()
    snapshot = None
    if readonly:
        saved = pr.read_json(root / STATE)
        if saved.get("status") != "complete_bounded_policy_candidate" or unit_limit is not None:
            raise wa.ExperimentError("completed full ordinary controller required for read-only verification")
        snapshot = (root / STATE).read_bytes()
    else:root.mkdir(parents=True, exist_ok=True)
    if (calibration_root is None) != (calibration_query is None):
        raise ValueError("calibration root and complete query must be supplied together")
    external = calibration_root is not None
    calibration_root = Path(calibration_root) if external else root / "calibration"
    completed_units = {} if completed_units is None else completed_units
    if not isinstance(completed_units, dict) or any(type(k) is not int or k < 0 for k in completed_units):
        raise ValueError("completed unit bindings require original plan ordinals")
    bindings = [{"ordinal": number, "root": str(Path(binding["root"]).resolve()),
                 "query_path": binding["query"]["path"], "query_sha256": binding["query"]["sha256"]}
                for number, binding in sorted(completed_units.items())]
    admission = {**pilot.quality.assignment_identity(limits), "source_sha256": catalog.source_sha256, "index_sha256": index["sha256"],
                 "tool_sha256": tool["sha256"], "budget": asdict(budget),
                 "calibration_root": str(calibration_root.resolve()), "completed_unit_bindings": bindings}
    # Reject a changed continuation BEFORE any new calibration command, even
    # when an external completed-pilot/unit binding was accidentally omitted.
    if (root / STATE).exists():
        previous = pr.read_json(root / STATE).get("identity", {})
        if (previous.get("assignment_coverage", .60) != limits.assignment_coverage
                or any(previous.get(k) != v for k, v in admission.items())
                or previous.get("plan", {}).get("unit_bases") != unit_bases
                or external and previous.get("pilot_query_sha256") != calibration_query["sha256"]):
            raise wa.ExperimentError("ordinary controller source/policy changed before calibration")
    if not external:
        if readonly and not (root / "pilot.fa.json").is_file():
            raise wa.ExperimentError("completed pilot input required for read-only verification")
        calibration_query = pilot.materialize(catalog, [r["name"] for r in plan["pilot_records"]], root / "pilot.fa")
        # Resume retains the original pilot resources; new resources affect only
        # future work units, never invalidate already paid pilot cases.
        options = argparse.Namespace(**vars(args))
        if (calibration_root / pilot.STATE).exists():
            identity = pr.read_json(calibration_root / pilot.STATE)["identity"]
            options.threads = identity["threads"]; options.memory_gib = identity["memory_gib"]
            options.minimap_batch = identity["batch"]
        decision = pilot.execute(calibration_root, plan, calibration_query, index, tool, options, readonly=readonly)
        if decision["status"] != "complete":
            return {"status": "calibration_incomplete", "decision": decision, "output_published": False}
    if pr.read_json(calibration_root / pilot.STATE)["identity"]["plan"] != plan:
        raise wa.ExperimentError("calibration plan/budget differs from controller admission")
    adopted = units.adopt_calibration(calibration_root, catalog, calibration_query, index, tool, assignment_coverage=limits.assignment_coverage)
    if adopted["decision"].get("input_binding") != [{"path": calibration_query["path"], "sha256": calibration_query["sha256"]},
            {"path": index["path"], "sha256": index["sha256"]}, {"path": tool["path"], "sha256": tool["sha256"]}]:
        raise wa.ExperimentError("calibration source binding changed")
    # Do not infer a broad length rule from unrelated records: only the short
    # cohort at/below the longest actually failed pilot record stays default.
    lengths = pilot.quality.record_lengths(records)
    ceiling = max([lengths[r["query"]] for r in adopted["decision"]["queries"] if r["source"] == "baseline"] or [0])
    work = units.plan_units(records, adopted["pilot_names"], adopted["future_filter"],
                            default_below=ceiling, unit_bases=unit_bases)
    progress(f"selected {adopted['future_filter']}; {len(work['units'])} whole-record work units; completed data will be reused")
    for number, binding in completed_units.items():
        if number >= len(work["units"]):raise ValueError("completed unit ordinal exceeds plan")
        directory = Path(binding["root"])
        if directory.is_symlink():raise wa.ExperimentError("linked external unit root")
        if pr.read_json(directory / "unit.json").get("status") != "complete":
            raise wa.ExperimentError("external unit is not sealed complete")
    identity = {**admission, "policy": POLICY, "plan": work,
                "pilot_query_sha256": calibration_query["sha256"],
                "pilot_default_sha256": adopted["decision"]["baseline"]["sha256"]}
    def review_path(name):return root / "reviews" / hashlib.sha256(name.encode("ascii")).hexdigest()
    marker = root / STATE
    state = pr.read_json(marker) if marker.exists() else {"schema": 1, "identity": identity, "reviews": {}}
    if state.get("schema") != 1 or state.get("identity") != identity or not isinstance(state.get("reviews"), dict):
        raise wa.ExperimentError("ordinary controller source/policy changed")
    ordinary_names = {r["name"] for r in work["ordinary_records"]}
    if not set(state["reviews"]) <= ordinary_names - set(adopted["pilot_names"]):
        raise wa.ExperimentError("ordinary review ledger contains an unrelated query")
    for name, row in state["reviews"].items():
        if (row.get("directory") != str(review_path(name))
                or row.get("status") not in ("reserved", "complete", "failed")
                or type(row.get("timeout_seconds")) is not int or not 0 < row["timeout_seconds"] <= budget.case_seconds
                or row["status"] == "reserved" and row.get("charged_seconds") != row["timeout_seconds"] + 5
                or type(row.get("charged_seconds")) not in (int, float)
                or not 0 < row["charged_seconds"] < float("inf")):
            raise wa.ExperimentError("invalid finite ordinary review ledger")
    def save():
        if not readonly:wa.write_json(marker, state)
    def stop(reason):
        state.update(status="stopped_without_publication", reason=reason, output_published=False,
                     whole_workload_quality_approved=False); save(); return state
    state.pop("composition", None)
    state.update(status="running", output_published=False, whole_workload_quality_approved=False,
                 pilot_default_preserved=True, selected_filter=adopted["future_filter"], completed_units=[],
                 default_continuation=None)
    save()
    active = [u["ordinal"] for u in work["units"] if unit_limit is None or u["ordinal"] < unit_limit]
    pending = [number for number in active if number not in completed_units]
    if readonly and any(not (root / "inputs" / ("unit-%06d.fa.json" % n)).is_file() for n in pending):
        raise wa.ExperimentError("completed ordinary input required for read-only verification")
    inputs = dict(zip(pending, units.materialize_units(catalog, work, root / "inputs", ordinals=pending)))
    original = {r.name: r for r in catalog.records}
    selections = list(adopted["selections"])
    for unit in work["units"]:
        if unit_limit is not None and unit["ordinal"] >= unit_limit:
            state.update(status="bounded_checkpoint", reason="internal_unit_limit"); save(); return state
        binding = completed_units.get(unit["ordinal"])
        directory = root / "units" / ("unit-%06d" % unit["ordinal"])
        if binding is not None:
            query = binding["query"]
            wanted = [(r["name"], original[r["name"]].length, original[r["name"]].sha256) for r in unit["records"]]
            if [(r["name"], r["length"], r["sha256"]) for r in query["identity"]["records"]] != wanted:
                raise wa.ExperimentError("external completed unit differs from original complete records")
            directory = Path(binding["root"])
        else:query = inputs[unit["ordinal"]]
        execution_unit = {**unit, "fraction": None} if state["default_continuation"] is not None else unit
        progress(f"unit {unit['ordinal'] + 1}/{len(work['units'])}, {unit['bases']} bp, filter {execution_unit['fraction'] or 'default'}")
        result = units.run_unit(directory, execution_unit, query, index, tool, args,
                                timeout=unit_seconds, readonly=readonly or binding is not None, primary_work=primary_work)
        progress("unit complete (verified cached output)" if result["reused"] else f"unit complete; native mapping {result['source']['wall_seconds']:.1f}s")
        names = [r["name"] for r in unit["records"]]
        if execution_unit["fraction"] is None:
            selections.append({"queries": names, "source": result["source"]})
            state["completed_units"].append({"ordinal": unit["ordinal"], "default": True}); save(); continue
        review = units.review_plan(result["source"]["profile"], work["ordinary_records"],
            previously_reviewed=list(state["reviews"]), max_records=budget.review_records,
            max_base_fraction=budget.review_fraction, assignment_coverage=limits.assignment_coverage)
        budget_stop = ("cumulative_review_count_or_bases_exceeded"
                       if review["action"] == "stop_filtered_continuation" else None)
        # Never add a native baseline block to filtered blocks for one query.
        # Every reviewed query chooses its COMPLETE default source, already paid.
        risks = review["review_queries"]; filtered = [q for q in names if q not in risks]
        if filtered:selections.append({"queries": filtered, "source": result["source"]})
        unit_review, unresolved = [], []
        for name in risks:
            destination = review_path(name)
            previous = state["reviews"].get(name)
            if previous is not None and previous["status"] == "failed":return stop("review_failed_no_retry")
            spent = sum(r["charged_seconds"] for r in state["reviews"].values())
            remaining = budget.total_seconds - spent
            if previous is None:
                if budget_stop is None and remaining <= 5:budget_stop = "review_wall_budget_exhausted"
                if budget_stop is not None:
                    unresolved.append(name); continue
                if readonly:raise wa.ExperimentError("complete default review missing during read-only verification")
                bound = min(budget.case_seconds, int(remaining - 5))
                if bound < 1:
                    budget_stop = "review_wall_budget_exhausted"; unresolved.append(name); continue
                previous = {"directory": str(destination), "status": "reserved", "timeout_seconds": bound,
                            "charged_seconds": bound + 5}
                state["reviews"][name] = previous; save()
            else:
                # A reserved entry alone is never proof of a live child, nor
                # permission to start it again. Only actual complete receipts
                # permit zero-mapping recovery after a hard kill.
                child = destination / "native" / "native-attempt.json"
                if not child.exists() or pr.read_json(child).get("status") != "native_success":
                    return stop("interrupted_review_no_automatic_retry")
            started = time.monotonic()
            try:
                unit_catalog = pp.scan_query(query["path"])
                review_input = root / "review-inputs" / (destination.name + ".fa")
                if readonly and not review_input.with_suffix(".fa.json").is_file():
                    raise wa.ExperimentError("complete review input missing during read-only verification")
                review_query = pilot.materialize(unit_catalog, [name], review_input)
                review_unit = {"records": [{"name": name, "length": lengths[name]}], "fraction": None}
                baseline = units.run_unit(destination, review_unit, review_query, index, tool, args,
                    timeout=previous["timeout_seconds"], retry_incomplete=False, readonly=readonly)
                if previous["status"] == "complete" and previous["charged_seconds"] < baseline["source"]["wall_seconds"]:
                    raise wa.ExperimentError("completed default review cost was understated")
                loss = pilot.quality.assess_loss(baseline["source"]["profile"], {name: result["source"]["profile"][name]}, limits)
                if previous["status"] != "complete" and not baseline["reused"]:
                    previous["charged_seconds"] = max(time.monotonic() - started, baseline["source"]["wall_seconds"])
                previous.update(status="complete", source_sha256=baseline["source"]["sha256"],
                                candidate_relative_loss=loss, complete_default_selected=True)
                selections.append({"queries": [name], "source": baseline["source"]})
                unit_review.append(name); save()
            except BaseException as exc:
                child = destination / "native" / "native-attempt.json"
                recoverable = child.exists() and pr.read_json(child).get("status") == "native_success"
                previous.update(status="reserved" if recoverable else "failed",
                                error=type(exc).__name__ + ": " + str(exc))
                if recoverable:previous["charged_seconds"] = previous["timeout_seconds"] + 5
                save(); raise
        if unresolved:
            progress(f"review allowance reached; {len(unresolved)} unresolved current records and future work use default; no whole-assembly restart")
            # End the approximation phase, not the user's task. At most ONE
            # transition unit resolves this unit's still-unreviewed records;
            # all future records run default ONCE as ordinary work. Previously
            # selected complete sources are never discarded or globally rerun.
            transition = root / "default-transition"
            transition_input = root / "default-transition.fa"
            if readonly and not transition_input.with_suffix(".fa.json").is_file():
                raise wa.ExperimentError("complete default transition input missing")
            current_catalog = pp.scan_query(query["path"])
            default_query = pilot.materialize(current_catalog, unresolved, transition_input)
            default_unit = {"records": [{"name": n, "length": lengths[n]} for n in unresolved], "fraction": None}
            default = units.run_unit(transition, default_unit, default_query, index, tool, args,
                                     timeout=unit_seconds, readonly=readonly, primary_work=primary_work)
            selections.append({"queries": unresolved, "source": default["source"]})
            state["default_continuation"] = {"ordinal": unit["ordinal"], "reason": budget_stop,
                "transition_queries": unresolved, "transition_source_sha256": default["source"]["sha256"],
                "transition_native_seconds": default["source"]["wall_seconds"],
                "transition_bases": sum(lengths[n] for n in unresolved),
                "future_filter": "default", "complete_prior_sources_preserved": True,
                "whole_assembly_restart": False}
        state["completed_units"].append({"ordinal": unit["ordinal"], "default": False,
                                         "reviewed_queries": unit_review, "screen": review}); save()
    if set(state["reviews"]) != {q for row in state["completed_units"] for q in row.get("reviewed_queries", [])}:
        raise wa.ExperimentError("ordinary review ledger contains unverified extra records")
    catalog.require_unchanged()
    if readonly and not (root / "composition/composition.json").is_file():
        raise wa.ExperimentError("complete composition missing during read-only verification")
    composition = units.compose_completed(root / "composition", work["ordinary_records"], index, selections)
    state.update(status="complete_bounded_policy_candidate", composition=composition,
                 complete_default_pilot_preserved=True, scientific_accuracy_proven=False,
                 baseline_compared_queries=list(state["reviews"]),
                 coverage="all_original_ordinary_records_and_index_parts", output_published=False)
    if readonly and marker.read_bytes() != snapshot:
        raise wa.ExperimentError("ordinary controller changed during read-only verification")
    save(); return state
