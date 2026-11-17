"""Whole-record ordinary work units, original-index native receipts and resume.

Unit completion is not whole-workload quality admission. This layer executes
one chosen native policy per unit, retains complete sources across resource
changes, and never turns an interrupted PAF into a completed source.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import subprocess

import automatic_ordinary_pilot as pilot
import minimap_options as mo
import proactive_reference_plan as pp
import proactive_resume as pr
import windowed_alignment as wa
import ordinary_tool_transition as ott

POLICY = "adaptive-ordinary-whole-units-v1"


def plan_units(records, pilot_names, selected_filter, *, default_below=0,
               unit_bases=128_000_000, max_records=4096):
    """Pack whole records, excluding already completed pilot records.

    Default/filtered cohorts have separate units but retain source order inside
    each cohort. Final assembly must restore original query/index-part order.
    One indivisible ordinary record may exceed the unit base target; never slice
    it merely to fit a nominal batch size.
    """
    lengths = pilot.quality.record_lengths(records)
    if (type(unit_bases) is not int or unit_bases < 1 or type(max_records) is not int or max_records < 1
            or type(default_below) is not int or default_below < 0):
        raise ValueError("positive unit targets and nonnegative default cohort required")
    if selected_filter != "default":mo.seed_fraction(selected_filter)
    if len(pilot_names) != len(set(pilot_names)) or not set(pilot_names) <= lengths.keys():
        raise ValueError("unique original pilot names required")
    ordinary = {q: n for q, n in lengths.items() if n <= pp.MAX_OPERATION}
    if not set(pilot_names) <= ordinary.keys():raise ValueError("pilot contains an ultralong query")
    excluded = set(pilot_names); current = {}; units = []
    for name, length in ordinary.items():
        if name in excluded:continue
        fraction = None if selected_filter == "default" or length <= default_below else selected_filter
        unit = current.get(fraction)
        if unit is None or unit["bases"] + length > unit_bases or len(unit["records"]) >= max_records:
            unit = {"ordinal": len(units), "fraction": fraction, "records": [], "bases": 0}
            units.append(unit); current[fraction] = unit
        unit["records"].append({"name": name, "length": length}); unit["bases"] += length
    return {"policy": POLICY, "units": units, "pilot_names": list(pilot_names),
            "ordinary_records": [{"name": q, "length": n} for q, n in ordinary.items()],
            "default_below": default_below, "unit_bases": unit_bases, "max_records": max_records,
            "selected_filter": selected_filter, "records_split": False}


def materialize_units(catalog, plan, root, *, ordinals=None):
    """Plain FASTA uses byte extents; gzip is streamed at most ONCE for all units."""
    records = [{"name": r.name, "length": r.length} for r in catalog.records]
    expected = plan_units(records, plan["pilot_names"], plan["selected_filter"],
        default_below=plan["default_below"], unit_bases=plan["unit_bases"], max_records=plan["max_records"])
    if plan != expected:raise wa.ExperimentError("ordinary unit plan changed")
    if ordinals is None:ordinals = [u["ordinal"] for u in plan["units"]]
    if (not isinstance(ordinals, list) or any(type(n) is not int or not 0 <= n < len(plan["units"]) for n in ordinals)
            or ordinals != sorted(set(ordinals))):raise ValueError("unique original unit ordinals required")
    selected_units = [plan["units"][n] for n in ordinals]
    catalog.require_unchanged()
    if not selected_units:return []
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked unit input directory")
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    if catalog.encoding == "plain":
        return [pilot.materialize(catalog, [r["name"] for r in u["records"]], root / ("unit-%06d.fa" % u["ordinal"]))
                for u in selected_units]
    by_name = {r.name: r for r in catalog.records}
    missing, completed = {}, {}
    for unit in selected_units:
        number = unit["ordinal"]; path = root / ("unit-%06d.fa" % number)
        marker = path.with_suffix(".fa.json")
        identity = {"source_sha256": catalog.source_sha256,
                    "records": [asdict(by_name[r["name"]]) for r in unit["records"]]}
        if marker.exists():
            previous = pr.read_json(marker)
            if (previous.get("identity") != identity or path.is_symlink()
                    or wa.verified_sha256(path) != previous["sha256"]):
                raise wa.ExperimentError("completed compressed-source unit changed")
            completed[number] = previous
        else:
            pending = path.with_suffix(".fa.partial")
            pr.archive_partial(path); pr.archive_partial(pending)
            missing[number] = {"unit": unit, "path": path, "pending": pending, "identity": identity,
                               "digest": hashlib.sha256(), "bytes": 0}
    if not missing:
        catalog.require_unchanged()
        return [completed[u["ordinal"]] for u in selected_units]
    owners = {r["name"]: u["ordinal"] for u in selected_units for r in u["records"]}
    active = {}
    try:
        with pp.decoded_input(catalog.source) as (stream, hashed, encoding):
            if encoding != catalog.encoding:raise wa.ExperimentError("unit source encoding changed")
            for record in catalog.records:
                number = owners.get(record.name); state = missing.get(number)
                output = None; digest = hashlib.sha256()
                if state is not None:
                    cohort = state["unit"]["fraction"]
                    previous = active.get(cohort)
                    if previous is None or previous[0] != number:
                        if previous is not None:previous[1].close()
                        output = state["pending"].open("xb")
                        active[cohort] = (number, output)
                    else:output = previous[1]
                remaining = record.byte_end - record.byte_start
                while remaining:
                    block = stream.read(min(wa.CHUNK, remaining))
                    if not block:raise wa.ExperimentError("compressed unit source truncated")
                    if output is not None:
                        output.write(block); digest.update(block); state["digest"].update(block); state["bytes"] += len(block)
                    remaining -= len(block)
                if output is not None and digest.hexdigest() != record.sha256:
                    raise wa.ExperimentError("ordinary unit record differs from catalog")
            if stream.read(1) or hashed.digest.hexdigest() != catalog.source_sha256:
                raise wa.ExperimentError("complete compressed unit source changed")
    finally:
        for _, handle in active.values():handle.close()
    catalog.require_unchanged()
    for number, state in missing.items():
        state["pending"].rename(state["path"])
        result = {"identity": state["identity"], "path": str(state["path"]),
                  "sha256": state["digest"].hexdigest(), "copied_bytes": state["bytes"], "complete_original_records": True}
        wa.write_json(state["path"].with_suffix(".fa.json"), result); completed[number] = result
    return [completed[u["ordinal"]] for u in selected_units]


def run_unit(root, unit, query, index, tool, args, *, timeout=1800, retry_incomplete=True, readonly=False, primary_work=False, execution_tool=None):
    """One native command, or verified reuse. No inner retry/parameter loop.

    A new explicit invocation may retry an interrupted ordinary work unit; a
    completed receipt is never rerun merely because threads/K/memory changed.
    Callers disable retry_incomplete for limited quality-review commands.
    """
    if (type(args.threads) is not int or args.threads < 1 or type(args.memory_gib) is not int or args.memory_gib < 0
            or type(primary_work) is not bool
            or not (primary_work and timeout is None) and (type(timeout) is not int or timeout < 1)):
        raise ValueError("invalid native unit resources")
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked ordinary unit root")
    root = root.resolve()
    if readonly and not root.is_dir():raise wa.ExperimentError("completed ordinary unit required")
    if not readonly:root.mkdir(parents=True, exist_ok=True)
    if unit["records"] != [{"name": r["name"], "length": r["length"]} for r in query["identity"]["records"]]:
        raise wa.ExperimentError("unit input records differ from plan")
    identity = {"policy": POLICY, "records": unit["records"], "query_sha256": query["sha256"],
                "index_sha256": index["sha256"], "tool_sha256": tool["sha256"], "fraction": unit["fraction"], "preset": "asm10"}
    marker = root / "unit.json"
    state = pr.read_json(marker) if marker.exists() else {"schema": 1, "identity": identity, "attempts": 0}
    execution_transition = None
    if execution_tool is not None:
        execution_transition = ott.transition_record(tool, execution_tool)
        next_identity = {**identity, "tool_sha256": execution_tool["sha256"]}
        previous_identity = state.get("identity")
        if state.get("schema") != 1 or previous_identity not in (identity, next_identity):
            raise wa.ExperimentError("ordinary unit source/filter identity changed before tool transition")
        native_receipt = root / "native/native-attempt.json"
        completed = (state.get("status") in ("complete", "native_complete_pending_validation")
            or native_receipt.exists() and pr.read_json(native_receipt).get("status") == "native_success")
        if marker.exists() and previous_identity == next_identity and state.get("execution_tool_transition") != execution_transition:
            raise wa.ExperimentError("ordinary unit execution provenance changed")
        if previous_identity == next_identity or not completed:
            if previous_identity != next_identity and marker.exists():
                if readonly or not retry_incomplete or not primary_work:
                    raise wa.ExperimentError("incomplete historical unit cannot be retried in this context")
                # Validate actual full inputs before archiving an incomplete unit.
                for path, digest in ((query["path"], query["sha256"]), (index["path"], index["sha256"])):
                    if wa.verified_sha256(Path(path)) != digest:
                        raise wa.ExperimentError("ordinary unit source changed before tool transition")
                archived = pr.archive_partial(root)
                root.mkdir()
                state = {"schema": 1, "identity": next_identity, "attempts": 0,
                         "previous_execution": {"directory": str(archived), "identity": previous_identity}}
            elif not marker.exists():
                state = {"schema": 1, "identity": next_identity, "attempts": 0}
            tool, identity = execution_tool, next_identity
        if not readonly:
            state["execution_tool_transition"] = execution_transition
    snapshot = marker.read_bytes() if readonly and marker.is_file() else None
    if readonly and (snapshot is None or state.get("status") != "complete"):
        raise wa.ExperimentError("ordinary unit not sealed complete")
    if state.get("schema") != 1 or state.get("identity") != identity:
        raise wa.ExperimentError("ordinary unit source/filter identity changed")
    def guard():
        for path, sha in ((query["path"], query["sha256"]), (index["path"], index["sha256"]), (tool["path"], tool["sha256"])):
            if wa.verified_sha256(Path(path)) != sha:raise wa.ExperimentError("ordinary unit source content changed")
    guard()
    actual_query = pp.scan_query(query["path"])
    if (actual_query.source_sha256 != query["sha256"] or [(r.name, r.length, r.sha256) for r in actual_query.records]
            != [(r["name"], r["length"], r["sha256"]) for r in query["identity"]["records"]]):
        raise wa.ExperimentError("ordinary unit actual query differs from complete input identity")
    actual_index = pilot.mic.read_catalog(index["path"])
    if [p["records"] for p in actual_index["parts"]] != [p["records"] for p in index["parts"]]:
        raise wa.ExperimentError("ordinary unit original index membership differs")
    sealed_native = root / "native/native-attempt.json"
    historical = (readonly or state.get("status") in ("complete", "native_complete_pending_validation")
        or sealed_native.exists() and pr.read_json(sealed_native).get("status") == "native_success")
    if ott.checked_version(tool, historical=historical) != "2.31-r1302":
        raise wa.ExperimentError("ordinary unit requires pinned minimap2 2.31-r1302")
    child = root / "native"
    def verify():
        resources = state["resources"]
        options = argparse.Namespace(threads=resources["threads"], memory_gib=resources["memory_gib"],
            minimap_batch=resources["batch"], minimap_filter=unit["fraction"], max_output_bytes=resources["output_bytes"])
        row = pilot._verify_case(root, {"directory": str(child)}, query, index, tool, unit["records"], unit["fraction"], options)
        guard()
        return row
    # Actual completed child receipts survive a controller kill between child
    # completion and sealing the unit. Validate them, never infer from PAF alone.
    if state.get("status") in ("running", "native_complete_pending_validation") and (child / "native-attempt.json").is_file():
        receipt = pr.read_json(child / "native-attempt.json")
        if state.get("native_receipt_sha256") is not None and wa.sha256(child / "native-attempt.json") != state["native_receipt_sha256"]:
            raise wa.ExperimentError("completed native unit receipt changed")
        if receipt.get("status") == "native_success":
            state.update(status="complete", source=verify()); wa.write_json(marker, state)
        elif state["status"] == "native_complete_pending_validation":
            raise wa.ExperimentError("sealed native unit lost its completion receipt")
    if state.get("status") == "native_complete_pending_validation":
        raise wa.ExperimentError("completed native unit receipt missing; refusing remapping")
    if state.get("status") == "complete":
        checked = verify()
        if any(checked[k] != state["source"][k] for k in ("directory", "receipt_sha256", "path", "sha256", "wall_seconds")):
            raise wa.ExperimentError("completed ordinary unit evidence changed")
        if readonly and marker.read_bytes() != snapshot:
            raise wa.ExperimentError("ordinary unit changed during read-only audit")
        return {"identity": identity, "source": checked, "reused": True, "resources": state["resources"]}
    if state.get("status") in ("running", "failed") and not retry_incomplete:
        raise wa.ExperimentError("bounded native review did not complete; no automatic retry")
    if execution_transition is not None and tool["sha256"] != execution_transition["execution"]["sha256"]:
        raise wa.ExperimentError("historical native completion could not be validated; refusing remapping")
    archived = pr.archive_partial(child)
    if archived is not None and state.get("attempt_history"):
        state["attempt_history"][-1]["archived_child"] = str(archived)
    options = argparse.Namespace(**vars(args))
    options.timeout = timeout; options.minimap_filter = unit["fraction"]
    options.minimap_batch = mo.batch_size(getattr(args, "minimap_batch", None) or "1G")
    options.memory_gib = args.memory_gib if primary_work else min(36, args.memory_gib) if args.memory_gib else 36
    options.max_output_bytes = None if primary_work else 64 * 1024**2
    state.update(status="running", attempts=state["attempts"] + 1,
        resources={"threads": args.threads, "batch": options.minimap_batch,
                   "memory_gib": options.memory_gib, "output_bytes": options.max_output_bytes, "timeout_seconds": timeout})
    wa.write_json(marker, state); started = time.monotonic()
    try:
        receipt = pilot.nf.attempt(tool["path"], Path(index["path"]), Path(query["path"]), child, options)
        if receipt["execution"].get("interrupted") == "KeyboardInterrupt":raise KeyboardInterrupt("ordinary unit cancelled")
        if receipt["status"] != "native_success":raise wa.ExperimentError("ordinary native unit did not complete")
        state.update(status="native_complete_pending_validation", native_receipt_sha256=wa.sha256(child / "native-attempt.json"))
        wa.write_json(marker, state)
        state.update(status="complete", source=verify()); state.pop("error", None)
    except BaseException as exc:
        state.update(status="native_complete_pending_validation" if state.get("status") == "native_complete_pending_validation" else "failed",
                     error=type(exc).__name__ + ": " + str(exc)); raise
    finally:
        state["last_invocation_seconds"] = time.monotonic() - started
        state.setdefault("attempt_history", []).append({"attempt": state["attempts"], "status": state["status"],
            "elapsed_seconds": state["last_invocation_seconds"], "resources": state["resources"]})
        wa.write_json(marker, state)
    return {"identity": identity, "source": state["source"], "reused": False, "resources": state["resources"]}


def compose_completed(root, records, index, selections):
    """Compose already VERIFIED complete sources, not a scientific approval.

    Each selection binds its native source and a disjoint set of full queries.
    This function has no mapper and cannot fill missing queries or native parts.
    Its caller must read-only validate pilot/unit receipts before calling it.
    Final order is original index part then original query, not cohort order.
    """
    from native_first import CellMerger
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked ordinary composition")
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    lengths = pilot.quality.record_lengths(records)
    membership = [name for selection in selections for name in selection["queries"]]
    if len(membership) != len(set(membership)) or set(membership) != set(lengths):
        raise wa.ExperimentError("ordinary composition omits/duplicates queries")
    if any(n > pp.MAX_OPERATION for n in lengths.values()):
        raise wa.ExperimentError("ordinary composition contains a long-route query")
    identity = {"policy": POLICY, "records": records, "index_sha256": index["sha256"],
                "parts": [{"part_index": p["part_index"], "records": p["records"]} for p in index["parts"]],
                "selections": [{"queries": selected["queries"], "source": {k: selected["source"][k]
                    for k in ("directory", "path", "sha256", "receipt_sha256")}} for selected in selections]}
    def guard():
        if wa.verified_sha256(Path(index["path"])) != index["sha256"]:
            raise wa.ExperimentError("ordinary composition index changed")
        for selected in selections:
            source = selected["source"]
            if (wa.verified_sha256(Path(source["path"])) != source["sha256"]
                    or wa.verified_sha256(Path(source["directory"]) / "native-attempt.json") != source["receipt_sha256"]):
                raise wa.ExperimentError("ordinary composition complete source changed")
    guard()
    output, marker = root / "ordinary.selected.paf", root / "composition.json"
    if marker.exists():
        previous = pr.read_json(marker)
        if previous.get("identity") != identity:raise wa.ExperimentError("ordinary composition policy/source changed")
        if wa.verified_sha256(output) != previous["sha256"]:raise wa.ExperimentError("completed ordinary composition changed")
        return previous
    pr.archive_partial(output); pr.archive_partial(root / "cells"); pr.archive_partial(root / "selected-sources")
    (root / "selected-sources").mkdir()
    targets = {r["name"]: {"length": r["length"]} for p in index["parts"] for r in p["records"]}
    merger = CellMerger(root / "cells", {q: {"length": n} for q, n in lengths.items()}, targets, index["parts"])
    provenance = []
    for number, selected in enumerate(selections):
        source = selected["source"]; names = selected["queries"]; wanted = {q.encode("ascii") for q in names}
        path = root / "selected-sources" / ("source-%06d.paf" % number)
        digest = hashlib.sha256(); copied = hashlib.sha256(); counts = {q: 0 for q in names}
        with Path(source["path"]).open("rb") as stream, path.open("xb") as out:
            for line in stream:
                digest.update(line)
                name = line.split(b"\t", 1)[0]
                if name in wanted:
                    out.write(line); copied.update(line); counts[name.decode("ascii")] += 1
        if digest.hexdigest() != source["sha256"]:raise wa.ExperimentError("native source changed while composing")
        merger._add(path, copied.hexdigest(), names, "adaptive_native", part_index=None)
        provenance.append({"queries": names, "source_path": source["path"], "source_sha256": source["sha256"],
                           "source_receipt_sha256": source["receipt_sha256"], "rows_by_query": counts,
                           "selected_sha256": copied.hexdigest()})
    pending = root / "ordinary.selected.partial.paf"; pr.archive_partial(pending)
    combination = merger.finish(pending)
    guard(); pending.rename(output)
    result = {"status": "complete_native_source_composition_not_quality_admission", "identity": identity,
              "path": str(output), "sha256": wa.sha256(output), "combination": combination,
              "provenance": provenance, "whole_workload_quality_approved": False,
              "fake_native_receipt_created": False, "sources_combined_within_query": False}
    wa.write_json(marker, result)
    return result


def review_plan(profile, workload_records, *, previously_reviewed=(), max_records=32,
                max_base_fraction=.05, assignment_coverage=.60):
    """Finite full-record review allowance over the ORIGINAL ordinary workload.

    This is a budget reservation plan, not a quality verdict or a runtime
    prediction. Exceeding the allowance stops automatic filtered continuation;
    it never silently approves ambiguous candidates or launches a whole baseline.
    """
    import math
    lengths = pilot.quality.record_lengths(workload_records)
    if (any(n > pp.MAX_OPERATION for n in lengths.values()) or type(max_records) is not int or max_records < 0
            or type(max_base_fraction) not in (int, float) or not math.isfinite(max_base_fraction)
            or not 0 <= max_base_fraction <= 1):raise ValueError("finite ordinary review allowance required")
    previous = list(previously_reviewed)
    if len(previous) != len(set(previous)) or not set(previous) <= lengths.keys():
        raise ValueError("review ledger must name unique original ordinary records")
    if any(q not in lengths or r["length"] != lengths[q] for q, r in profile.items()):
        raise wa.ExperimentError("review profile differs from original workload")
    limits = pilot.quality.assignment_limits(assignment_coverage)
    if not profile or not pilot.quality.assess_loss(profile, profile, limits)["passed"]:
        raise wa.ExperimentError("complete native assignment evidence required")
    screened_rows = []
    for name, row in profile.items():
        assigned = pilot.quality.consumer_assignments(row, limits); reasons = []
        if not assigned:
            reasons.append("covered_but_unassigned" if row["covered"] / row["length"] >= limits.assignment_coverage else "low_reference_support")
        # Inspect both sides of the consumer threshold: a previously qualifying
        # alternative could have fallen just below it after seed filtering.
        if any(limits.assignment_coverage - limits.assignment_margin <= candidate["covered"] / row["length"]
               < limits.assignment_coverage + limits.assignment_margin for candidate in row["assignment_candidates"].values()):
            reasons.append("near_assignment_threshold")
        for target in assigned:
            weights = row["assignment_candidates"][target]["strand_weights"]
            if abs(weights["+"] - weights["-"]) / sum(weights.values()) < limits.assignment_margin:
                reasons.append("orientation_ambiguous"); break
        # These are COMPLETE native-query chains, not independent window-local
        # candidates. Absolute anchor dispersion and multiple valid chromosomes
        # alone are not proof of a new loss; the default wheat native control
        # itself has broad anchors. Keep the stricter window gate on its own path.
        screened_rows.append({"query": name, "coverage_fraction": row["covered"] / row["length"],
            "assigned_targets": sorted(assigned), "reasons": reasons,
            "action": "bounded_review" if reasons else "no_obvious_assignment_risk"})
    screened = {"scope": "whole_query_native_only", "queries": screened_rows,
                "window_coherence_rule_applied": False, "baseline_comparison_performed": False,
                "scientific_accuracy_proven": False}
    risks = [r["query"] for r in screened["queries"] if r["action"] == "bounded_review"]
    combined = set(previous) | set(risks)
    bases = sum(lengths[q] for q in combined)
    exceeded = len(combined) > max_records or bases > sum(lengths.values()) * max_base_fraction
    return {"policy": POLICY, "quality_policy": pilot.quality.POLICY, "screen": screened,
            "action": "stop_filtered_continuation" if exceeded else "bounded_full_record_review" if risks else "no_obvious_assignment_risk",
            "review_queries": risks, "new_review_queries": [q for q in risks if q not in previous],
            "cumulative_review_records": len(combined), "cumulative_review_bases": bases,
            "review_limit_records": max_records, "review_limit_bases": int(sum(lengths.values()) * max_base_fraction),
            "native_baseline_compared": False, "whole_workload_quality_approved": False}


def adopt_calibration(root, catalog, query, index, tool, *, assignment_coverage=.60):
    """Revalidate a completed calibration and KEEP its full default pilot data.

    The chosen filter applies to future records only. Both policies were already
    measured on the pilot, so discarding its complete default output buys no
    runtime saving. Nested extraction/catalogue parents are accepted by actual
    complete-record content, not by a direct-parent metadata link.
    """
    catalog.require_unchanged()
    state = pr.read_json(Path(root) / pilot.STATE)
    identity = state["identity"]
    limits = pilot.quality.assignment_limits(assignment_coverage)
    if identity.get("assignment_coverage", .60) != limits.assignment_coverage:
        raise wa.ExperimentError("completed calibration assignment threshold differs from current project")
    records = [{"name": r.name, "length": r.length} for r in catalog.records]
    plan = pilot.plan(identity["plan"]["reference_bases"], records, budget=pilot.Budget(**identity["budget"]))
    if plan != identity["plan"]:raise wa.ExperimentError("calibration does not describe this ordinary workload")
    full = {r.name: r for r in catalog.records}
    selected = query["identity"]["records"]
    if any(r["name"] not in full or (r["length"], r["sha256"]) != (full[r["name"]].length, full[r["name"]].sha256) for r in selected):
        raise wa.ExperimentError("pilot record content is not from this workload")
    args = argparse.Namespace(threads=identity["threads"], memory_gib=identity["memory_gib"], minimap_batch=identity["batch"], assignment_coverage=limits.assignment_coverage)
    decision = pilot.execute(root, plan, query, index, tool, args, readonly=True)
    names = [r["name"] for r in plan["pilot_records"]]
    if [r["name"] for r in selected] != names or decision["status"] != "complete":
        raise wa.ExperimentError("complete native pilot source missing")
    catalog.require_unchanged()
    return {"policy": POLICY, "future_filter": decision["selected_filter"], "decision": decision,
            "pilot_names": names, "selections": [{"queries": names, "source": decision["baseline"]}],
            "complete_default_pilot_preserved": True, "new_mapping_commands": 0,
            "whole_workload_quality_approved": False, "workload_source_sha256": catalog.source_sha256}
