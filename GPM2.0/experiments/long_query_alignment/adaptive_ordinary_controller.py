"""Finite calibration, whole-unit continuation and limited full-record review.

Internal orchestration only: callers own an exclusive task lock. No CLI or
Server-default hook is enabled here. Scientific accuracy is not inferred from
absence of screening flags. A stopped controller never publishes a partial PAF.
"""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict
from pathlib import Path
import time

import adaptive_ordinary_units as units
import automatic_ordinary_pilot as pilot
import proactive_reference_plan as pp
import proactive_resume as pr
import windowed_alignment as wa

POLICY = "automatic-ordinary-controller-v1"
STATE = "ordinary-controller.json"


def execute(root, catalog, index, tool, args, *, budget=pilot.Budget(),
            calibration_root=None, calibration_query=None, unit_bases=128_000_000,
            unit_limit=None, unit_seconds=2400, completed_units=None):
    """Run the admitted internal policy without a whole-input parameter sweep.

    unit_limit is an internal bounded-development checkpoint, not a user choice.
    Review reservations survive hard kills; a failed review is never retried.
    The parent task lock must cover this call and any source adoption.
    """
    if unit_limit is not None and (type(unit_limit) is not int or unit_limit < 0):
        raise ValueError("nonnegative internal unit checkpoint required")
    if type(unit_seconds) is not int or unit_seconds < 1:raise ValueError("positive ordinary unit timeout required")
    budget.checked(); catalog.require_unchanged()
    records = [{"name": r.name, "length": r.length} for r in catalog.records]
    reference_bases = sum(r["length"] for part in index["parts"] for r in part["records"])
    plan = pilot.plan(reference_bases, records, explicit_filter=getattr(args, "minimap_filter", None), budget=budget)
    if not plan["enabled"]:
        return {"status": "not_triggered", "plan": plan, "mapping_commands": 0}
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked ordinary controller directory")
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
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
    admission = {"source_sha256": catalog.source_sha256, "index_sha256": index["sha256"],
                 "tool_sha256": tool["sha256"], "budget": asdict(budget),
                 "calibration_root": str(calibration_root.resolve()), "completed_unit_bindings": bindings}
    # Reject a changed continuation BEFORE any new calibration command, even
    # when an external completed-pilot/unit binding was accidentally omitted.
    if (root / STATE).exists():
        previous = pr.read_json(root / STATE).get("identity", {})
        if (any(previous.get(k) != v for k, v in admission.items())
                or previous.get("plan", {}).get("unit_bases") != unit_bases
                or external and previous.get("pilot_query_sha256") != calibration_query["sha256"]):
            raise wa.ExperimentError("ordinary controller source/policy changed before calibration")
    if not external:
        calibration_query = pilot.materialize(catalog, [r["name"] for r in plan["pilot_records"]], root / "pilot.fa")
        # Resume retains the original pilot resources; new resources affect only
        # future work units, never invalidate already paid pilot cases.
        options = argparse.Namespace(**vars(args))
        if (calibration_root / pilot.STATE).exists():
            identity = pr.read_json(calibration_root / pilot.STATE)["identity"]
            options.threads = identity["threads"]; options.memory_gib = identity["memory_gib"]
            options.minimap_batch = identity["batch"]
        decision = pilot.execute(calibration_root, plan, calibration_query, index, tool, options)
        if decision["status"] != "complete":
            return {"status": "calibration_incomplete", "decision": decision, "output_published": False}
    if pr.read_json(calibration_root / pilot.STATE)["identity"]["plan"] != plan:
        raise wa.ExperimentError("calibration plan/budget differs from controller admission")
    adopted = units.adopt_calibration(calibration_root, catalog, calibration_query, index, tool)
    if adopted["decision"].get("input_binding") != [{"path": calibration_query["path"], "sha256": calibration_query["sha256"]},
            {"path": index["path"], "sha256": index["sha256"]}, {"path": tool["path"], "sha256": tool["sha256"]}]:
        raise wa.ExperimentError("calibration source binding changed")
    # Do not infer a broad length rule from unrelated records: only the short
    # cohort at/below the longest actually failed pilot record stays default.
    lengths = pilot.quality.record_lengths(records)
    ceiling = max([lengths[r["query"]] for r in adopted["decision"]["queries"] if r["source"] == "baseline"] or [0])
    work = units.plan_units(records, adopted["pilot_names"], adopted["future_filter"],
                            default_below=ceiling, unit_bases=unit_bases)
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
    def save():wa.write_json(marker, state)
    def stop(reason):
        state.update(status="stopped_without_publication", reason=reason, output_published=False,
                     whole_workload_quality_approved=False); save(); return state
    state.pop("composition", None)
    state.update(status="running", output_published=False, whole_workload_quality_approved=False,
                 pilot_default_preserved=True, selected_filter=adopted["future_filter"], completed_units=[])
    save()
    active = [u["ordinal"] for u in work["units"] if unit_limit is None or u["ordinal"] < unit_limit]
    pending = [number for number in active if number not in completed_units]
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
        result = units.run_unit(directory, unit, query, index, tool, args,
                                timeout=unit_seconds, readonly=binding is not None)
        names = [r["name"] for r in unit["records"]]
        if unit["fraction"] is None:
            selections.append({"queries": names, "source": result["source"]})
            state["completed_units"].append({"ordinal": unit["ordinal"], "default": True}); save(); continue
        review = units.review_plan(result["source"]["profile"], work["ordinary_records"],
            previously_reviewed=list(state["reviews"]), max_records=budget.review_records,
            max_base_fraction=budget.review_fraction)
        if review["action"] == "stop_filtered_continuation":
            return stop("cumulative_review_count_or_bases_exceeded")
        # Never add a native baseline block to filtered blocks for one query.
        # Every reviewed query chooses its COMPLETE default source, already paid.
        risks = review["review_queries"]; filtered = [q for q in names if q not in risks]
        if filtered:selections.append({"queries": filtered, "source": result["source"]})
        unit_review = []
        for name in risks:
            destination = review_path(name)
            previous = state["reviews"].get(name)
            if previous is not None and previous["status"] == "failed":return stop("review_failed_no_retry")
            spent = sum(r["charged_seconds"] for r in state["reviews"].values())
            remaining = budget.total_seconds - spent
            if previous is None:
                if remaining <= 5:return stop("review_wall_budget_exhausted")
                bound = min(budget.case_seconds, int(remaining - 5))
                if bound < 1:return stop("review_wall_budget_exhausted")
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
                review_query = pilot.materialize(unit_catalog, [name], root / "review-inputs" / (destination.name + ".fa"))
                review_unit = {"records": [{"name": name, "length": lengths[name]}], "fraction": None}
                baseline = units.run_unit(destination, review_unit, review_query, index, tool, args,
                    timeout=previous["timeout_seconds"], retry_incomplete=False)
                loss = pilot.quality.assess_loss(baseline["source"]["profile"], {name: result["source"]["profile"][name]})
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
        state["completed_units"].append({"ordinal": unit["ordinal"], "default": False,
                                         "reviewed_queries": unit_review, "screen": review}); save()
    catalog.require_unchanged()
    composition = units.compose_completed(root / "composition", work["ordinary_records"], index, selections)
    state.update(status="complete_bounded_policy_candidate", composition=composition,
                 complete_default_pilot_preserved=True, scientific_accuracy_proven=False,
                 baseline_compared_queries=list(state["reviews"]),
                 coverage="all_original_ordinary_records_and_index_parts", output_published=False)
    save(); return state
