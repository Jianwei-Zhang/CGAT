"""Internal finite ordinary-workload calibration with reusable COMPLETE sources.

This executor does not authorize an entire assembly from its small pilot. It
performs the real bounded work needed before that decision: automatic complete-
record selection, amortization admission, checkpointed paired native executions,
and one source per pilot record. No failed/partial PAF is ever profiled.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

import adaptive_screening as quality
import minimap_options as mo
import minimap_index_context as mic
import native_first as nf
import proactive_reference_plan as pp
import proactive_resume as pr
import recovery_publication as publication
import selective_reference_alignment as sr
import windowed_alignment as wa

POLICY = "automatic-ordinary-pilot-v1"
STATE = "ordinary-pilot.json"


@dataclass(frozen=True)
class Budget:
    reference_bases: int = 5_000_000_000
    workload_bases: int = 1_000_000_000
    long_ordinary_bases: int = 20_000_000
    pilot_bases: int = 128_000_000
    minimum_workload_multiple: int = 64
    case_seconds: int = 1200
    total_seconds: int = 4800
    output_bytes: int = 64 * 1024**2
    review_records: int = 32
    review_fraction: float = .05
    minimum_speedup: float = 2.0

    def checked(self):
        for name, value in asdict(self).items():
            if name in ("review_fraction", "minimum_speedup"):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("finite pilot policy required")
            elif type(value) is not int or value <= 0:
                raise ValueError("positive integer pilot budgets required")
        if not 0 <= self.review_fraction <= 1 or self.minimum_speedup < 1:
            raise ValueError("invalid loss/speed budget")
        return self


def plan(reference_bases, records, *, explicit_filter=None, budget=Budget()):
    """Size admits a finite experiment, not an automatic sensitivity change.

    The base-weighted median avoids choosing only tiny, unrepresentative records
    from a long-contig assembly. All selected records remain whole; a dominant
    record larger than the pilot cap declines calibration instead of slicing it.
    """
    budget.checked()
    if type(reference_bases) is not int or reference_bases <= 0:
        raise ValueError("positive reference length required")
    lengths = quality.record_lengths(records)
    ordinary = {q: n for q, n in lengths.items() if n <= pp.MAX_OPERATION}
    total = sum(ordinary.values())
    result = {"policy": POLICY, "enabled": False, "budget": asdict(budget),
              "reference_bases": reference_bases, "ordinary_bases": total,
              "ordinary_records": [{"name": q, "length": n} for q, n in ordinary.items()],
              "pilot_records": [], "sensitivity_changed": False,
              "whole_workload_performance_predicted": False}
    if explicit_filter is not None:
        mo.seed_fraction(explicit_filter)
        return {**result, "reason": "explicit_filter_preserved"}
    if (reference_bases < budget.reference_bases or total < budget.workload_bases
            or not ordinary or max(ordinary.values()) < budget.long_ordinary_bases):
        return {**result, "reason": "insufficient_large_ordinary_workload"}
    ordered = sorted(ordinary, key=lambda q: (ordinary[q], q))
    accumulated = 0
    for median in ordered:
        accumulated += ordinary[median]
        if accumulated * 2 >= total:break
    if ordinary[median] > budget.pilot_bases:
        return {**result, "reason": "representative_complete_record_exceeds_pilot_cap"}
    chosen = {median}
    # Include a weak/short sentinel and mid-length evidence if present, without
    # replacing the representative by a more convenient tiny input.
    for desired in (500_000, 3_000_000, 20_000_000):
        candidates = [q for q in ordinary if q not in chosen
                      and sum(ordinary[n] for n in chosen) + ordinary[q] <= budget.pilot_bases]
        if candidates:
            chosen.add(min(candidates, key=lambda q: (abs(ordinary[q] - desired), q)))
    pilot = [{"name": q, "length": n} for q, n in ordinary.items() if q in chosen]
    bases = sum(r["length"] for r in pilot)
    result.update(pilot_records=pilot, pilot_bases=bases, representative=median,
                  workload_to_pilot_bases=total / bases)
    if total < bases * budget.minimum_workload_multiple:
        return {**result, "reason": "pilot_cost_not_amortizable_by_workload_size"}
    return {**result, "enabled": True, "reason": "bounded_complete_record_calibration",
            "pilot_fraction_of_ordinary_bases": bases / total}


def materialize(catalog, names, destination):
    """Copy original complete records, preserving headers/case/wrapping/order.

    Plain input uses catalogued byte extents rather than rescanning a huge file
    for every unit. gzip streams to EOF and revalidates its complete source hash.
    """
    destination = Path(destination)
    catalog.require_unchanged()
    wanted = set(names)
    selected = [r for r in catalog.records if r.name in wanted]
    if not names or [r.name for r in selected] != list(names):
        raise ValueError("unique records in original input order required")
    identity = {"source_sha256": catalog.source_sha256,
                "records": [asdict(r) for r in selected]}
    marker = destination.with_suffix(destination.suffix + ".json")
    if marker.exists():
        old = pr.read_json(marker)
        if old.get("identity") != identity or destination.is_symlink() or wa.verified_sha256(destination) != old["sha256"]:
            raise wa.ExperimentError("completed ordinary input unit changed")
        catalog.require_unchanged()
        return old
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.parent.is_symlink():
        raise wa.ExperimentError("linked ordinary input destination")
    pending = destination.with_suffix(destination.suffix + ".partial")
    pr.archive_partial(pending); pr.archive_partial(destination)
    digest = hashlib.sha256(); copied = 0
    with pending.open("xb") as out:
        if catalog.encoding == "plain":
            with Path(catalog.source).open("rb") as stream:
                for record in selected:
                    stream.seek(record.byte_start)
                    remaining = record.byte_end - record.byte_start; individual = hashlib.sha256()
                    while remaining:
                        block = stream.read(min(wa.CHUNK, remaining))
                        if not block:raise wa.ExperimentError("ordinary input truncated")
                        out.write(block); digest.update(block); individual.update(block)
                        remaining -= len(block); copied += len(block)
                    if individual.hexdigest() != record.sha256:
                        raise wa.ExperimentError("ordinary record changed after cataloguing")
        else:
            wanted = set(names)
            with pp.decoded_input(catalog.source) as (stream, hashed, encoding):
                if encoding != catalog.encoding:raise wa.ExperimentError("ordinary source encoding changed")
                for record in catalog.records:
                    remaining = record.byte_end - record.byte_start; individual = hashlib.sha256()
                    while remaining:
                        block = stream.read(min(wa.CHUNK, remaining))
                        if not block:raise wa.ExperimentError("compressed ordinary input truncated")
                        if record.name in wanted:
                            out.write(block); digest.update(block); individual.update(block); copied += len(block)
                        remaining -= len(block)
                    if record.name in wanted and individual.hexdigest() != record.sha256:
                        raise wa.ExperimentError("compressed ordinary record changed")
                if stream.read(1) or hashed.digest.hexdigest() != catalog.source_sha256:
                    raise wa.ExperimentError("compressed ordinary source changed")
    catalog.require_unchanged()
    pending.rename(destination)
    result = {"identity": identity, "path": str(destination), "sha256": digest.hexdigest(),
              "copied_bytes": copied, "complete_original_records": True}
    wa.write_json(marker, result)
    return result


def _complete_traversal(text, expected_parts, query_count):
    observed = []
    for line in text.splitlines():
        loaded = re.search(r"loaded/built the index for ([0-9]+) target sequence", line)
        if loaded:observed.append([int(loaded[1]), 0])
        batch = re.search(r"\[M::worker_pipeline::[^\]]+\] mapped ([0-9]+) sequences", line)
        if batch:
            if not observed:raise wa.ExperimentError("pilot batch precedes original index part")
            observed[-1][1] += int(batch[1])
    if observed != [[n, query_count] for n in expected_parts]:
        raise wa.ExperimentError("pilot omitted original part/query traversal")


def _verify_case(root, row, query, index, tool, records, fraction, options):
    directory = Path(row["directory"])
    publication.regular_under(directory / "native-attempt.json", root)
    receipt = publication.verify_attempt(directory / "native-attempt.json", root, "native_success",
        tool=tool["path"], target=Path(index["path"]), query=Path(query["path"]), fraction=fraction)
    expected = [tool["path"], "-c", "-x", "asm10", *mo.native_flags(options), "-t", str(options.threads),
                "-o", str(directory / "native.partial.paf"), index["path"], query["path"]]
    if receipt["execution"]["command"] != expected or receipt["index_sequence_counts"] != [len(p["records"]) for p in index["parts"]]:
        raise wa.ExperimentError("pilot command/original index traversal changed")
    _complete_traversal((directory / "native.stderr").read_text(),
                        [len(p["records"]) for p in index["parts"]], len(records))
    path = Path(receipt["path"])
    if path.stat().st_size > options.max_output_bytes:
        raise wa.ExperimentError("pilot output exceeded its finite audit budget")
    queries = {r["name"]: {"length": r["length"]} for r in records}
    targets = {r["name"]: {"length": r["length"]} for p in index["parts"] for r in p["records"]}
    with path.open("rb") as stream:
        for line in stream:sr.validate_row(line, queries, targets, set(queries), "native")
    elapsed = receipt["execution"]["seconds"]
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
        raise wa.ExperimentError("positive completed native timing required")
    return {"directory": str(directory), "receipt_sha256": wa.sha256(directory / "native-attempt.json"),
            "path": str(path), "sha256": receipt["paf_sha256"], "wall_seconds": elapsed,
            "profile": quality.coverage_profile(path, records)}


def execute(root, pilot_plan, query, index, tool, args):
    """Run at most six complete-native cases with a cumulative resume-safe budget.

    baseline0 / candidate0 / candidate1 / baseline1 allow early rejection of an
    obviously slow first candidate. Reuse baseline1 for a stronger candidate.
    Saved complete cases survive cancellation; failed cases are never rerun.
    A chosen policy still needs bounded workload-unit execution and review.
    """
    invocation = time.monotonic()
    if not pilot_plan.get("enabled") or pilot_plan.get("policy") != POLICY:
        raise ValueError("internally admitted ordinary pilot required")
    budget = Budget(**pilot_plan["budget"]).checked()
    if type(args.threads) is not int or args.threads < 1 or type(args.memory_gib) is not int or args.memory_gib < 0:
        raise ValueError("invalid ordinary pilot resources")
    if getattr(args, "timeout", None) is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
        raise ValueError("positive optional pilot timeout required")
    records = pilot_plan["pilot_records"]
    if [{"name": r["name"], "length": r["length"]} for r in query["identity"]["records"]] != records:
        raise wa.ExperimentError("pilot input differs from complete-record plan")
    if pilot_plan != plan(pilot_plan["reference_bases"], pilot_plan["ordinary_records"], budget=budget):
        raise wa.ExperimentError("ordinary pilot plan changed")
    root = Path(root)
    if root.is_symlink() or root.parent.is_symlink():raise wa.ExperimentError("linked ordinary pilot root")
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    parsed = mic.read_catalog(index["path"])
    if ([p["records"] for p in parsed["parts"]] != [p["records"] for p in index["parts"]]
            or sum(r["length"] for p in parsed["parts"] for r in p["records"]) != pilot_plan["reference_bases"]):
        raise wa.ExperimentError("pilot reference is not the complete declared index")
    if subprocess.check_output([tool["path"], "--version"], text=True, timeout=5).strip() != "2.31-r1302":
        raise wa.ExperimentError("ordinary pilot requires pinned minimap2 2.31-r1302")
    actual = pp.scan_query(query["path"])
    if (actual.source_sha256 != query["sha256"] or [(r.name, r.length, r.sha256) for r in actual.records]
            != [(r["name"], r["length"], r["sha256"]) for r in query["identity"]["records"]]):
        raise wa.ExperimentError("pilot complete-record content changed")
    batch = mo.batch_size(getattr(args, "minimap_batch", None) or "1G")
    identity = {"policy": POLICY, "query_sha256": query["sha256"], "index_sha256": index["sha256"],
                "tool_sha256": tool["sha256"], "threads": args.threads, "batch": batch,
                "memory_gib": args.memory_gib, "budget": asdict(budget), "plan": pilot_plan,
                "mapping_sources": {Path(m.__file__).name: wa.sha256(Path(m.__file__)) for m in (nf, wa, mo)}}
    state_path = root / STATE
    state = pr.read_json(state_path) if state_path.exists() else {"schema": 1, "identity": identity, "cases": {}, "spent_seconds": 0.0}
    if state.get("schema") != 1 or state.get("identity") != identity:
        raise wa.ExperimentError("ordinary pilot source/recipe changed")
    if (type(state.get("spent_seconds")) not in (int, float) or not math.isfinite(state["spent_seconds"])
            or state["spent_seconds"] < 0 or not isinstance(state.get("cases"), dict)):
        raise wa.ExperimentError("ordinary pilot budget ledger changed")
    allowed_cases = {"baseline-0", "baseline-1", "f0.005-0", "f0.005-1", "f0.01-0", "f0.01-1"}
    if not state["cases"].keys() <= allowed_cases:
        raise wa.ExperimentError("unknown ordinary calibration case")
    for label, row in state["cases"].items():
        if (row.get("directory") != str(root / label)
                or row.get("status") not in ("started", "interrupted_no_retry", "pending_validation", "failed", "complete")
                or type(row.get("reserved_seconds")) not in (int, float)
                or not math.isfinite(row["reserved_seconds"]) or not 0 < row["reserved_seconds"] <= budget.case_seconds + 5):
            raise wa.ExperimentError("ordinary pilot case ledger changed")
    def guard():
        for path, digest in ((query["path"], query["sha256"]), (index["path"], index["sha256"]), (tool["path"], tool["sha256"])):
            if wa.verified_sha256(Path(path)) != digest:raise wa.ExperimentError("ordinary pilot source content changed")
    def save():wa.write_json(state_path, state)
    guard()
    # A hard-killed case has no reliable end timestamp. Reserve its entire
    # admitted slice on resume rather than silently resetting the total budget.
    for row in state["cases"].values():
        if row.get("status") == "started":
            state["spent_seconds"] += row["reserved_seconds"]
            receipt_path = Path(row["directory"]) / "native-attempt.json"
            complete = (receipt_path.exists() and pr.read_json(publication.regular_under(receipt_path, root)).get("status") == "native_success")
            row.update(status="pending_validation" if complete else "interrupted_no_retry")
    save()
    spent_before = state["spent_seconds"]
    def case(label, fraction):
        old = state["cases"].get(label)
        options = argparse.Namespace(**vars(args))
        options.minimap_filter = fraction; options.minimap_batch = batch
        options.max_output_bytes = budget.output_bytes
        options.memory_gib = min(36, args.memory_gib) if args.memory_gib else 36
        options.timeout = min(budget.case_seconds, getattr(args, "timeout", None) or budget.case_seconds, max(0.0, budget.total_seconds - spent_before - (time.monotonic() - invocation)))
        if old:
            if old.get("status") not in ("complete", "pending_validation"):return None
            checked = _verify_case(root, old, query, index, tool, records, fraction, options)
            if old["status"] == "complete" and any(checked[k] != old[k] for k in
                    ("directory", "receipt_sha256", "path", "sha256", "wall_seconds")):
                raise wa.ExperimentError("completed ordinary pilot evidence changed")
            # Profiles are cheap derived data, never an admission cache. A new
            # quality implementation re-evaluates the verified complete PAF.
            old.update(status="complete", **checked); save()
            return checked
        if options.timeout <= 0:return None
        directory = root / label
        row = {"status": "started", "directory": str(directory), "fraction": fraction, "reserved_seconds": options.timeout + 5}
        state["cases"][label] = row
        # Seal preflight/verification time before starting the child, too. A
        # hard kill must not erase the cost already spent in this invocation.
        state["spent_seconds"] = spent_before + time.monotonic() - invocation
        save()
        try:
            native = nf.attempt(tool["path"], Path(index["path"]), Path(query["path"]), directory, options)
            if native["execution"].get("interrupted") == "KeyboardInterrupt":
                raise KeyboardInterrupt("ordinary calibration cancelled")
            if native["status"] != "native_success":
                row.update(status="failed", native_status=native["status"])
                return None
            checked = _verify_case(root, row, query, index, tool, records, fraction, options)
            guard(); row.update(status="complete", **checked)
            return checked
        except BaseException as exc:
            row.update(status="failed", error=type(exc).__name__ + ": " + str(exc)); raise
        finally:
            state["spent_seconds"] = spent_before + time.monotonic() - invocation; save()
    result = {"policy": POLICY, "status": "evaluating", "selected_filter": "default", "candidates": [],
              "whole_workload_approved": False, "hybrid_runtime_measured": False,
              "reason": "no_completed_bounded_candidate", "queries": [], "quality_policy": quality.POLICY,
              "input_binding": [{"path": query["path"], "sha256": query["sha256"]},
                                {"path": index["path"], "sha256": index["sha256"]},
                                {"path": tool["path"], "sha256": tool["sha256"]}]}
    try:
        baseline = case("baseline-0", None)
        if baseline is None:
            result.update(reason="baseline_incomplete_no_sensitivity_change", status="incomplete_no_baseline")
            return result
        result["baseline"] = baseline
        result["queries"] = [{"query": r["name"], "source": "baseline", "reasons": []} for r in records]
        if not any(row["covered"] for row in baseline["profile"].values()):
            guard()
            result.update(status="complete", reason="baseline_uninformative_no_filter_trials")
            return result
        for fraction in ("0.005", "0.01"):
            entry = {"fraction": fraction, "eligible": False}; result["candidates"].append(entry)
            first = case("f" + fraction + "-0", fraction)
            if first is None:
                entry["reason"] = "candidate_incomplete"; continue
            speed0 = baseline["wall_seconds"] / first["wall_seconds"]
            entry["first_speedup"] = speed0
            review = quality.plan_completed_record_review(baseline["profile"], first["profile"])
            fallback = [r["query"] for r in review["queries"] if r["source"] == "baseline"]
            lengths = quality.record_lengths(records)
            fallback_bases = sum(lengths[q] for q in fallback)
            if (review["status"] != "completed_record_review_planned" or len(fallback) > budget.review_records
                    or len(fallback) == len(records) or fallback_bases > sum(lengths.values()) * budget.review_fraction):
                entry["reason"] = "review_cost_or_quality_failed"; continue
            if speed0 < budget.minimum_speedup:
                entry["reason"] = "first_completed_speedup_insufficient"; continue
            second = case("f" + fraction + "-1", fraction)
            reference_repeat = case("baseline-1", None)
            if second is None or reference_repeat is None:
                entry["reason"] = "complete_paired_repeat_missing"; continue
            speed1 = reference_repeat["wall_seconds"] / second["wall_seconds"]
            if (first["sha256"] != second["sha256"] or baseline["sha256"] != reference_repeat["sha256"]):
                entry["reason"] = "same_recipe_output_not_repeatable"; continue
            if speed1 < budget.minimum_speedup:
                entry["reason"] = "second_completed_speedup_insufficient"; continue
            entry.update(eligible=True, speedups=[speed0, speed1], review=review)
            result.update(selected_filter=fraction, reason="weakest_repeatable_completed_candidate",
                          candidate=first, queries=review["queries"])
            break
        guard()
        result["status"] = "complete"
        return result
    except BaseException as exc:
        result.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        state["spent_seconds"] = spent_before + time.monotonic() - invocation
        state["status"] = result["status"]
        state["decision"] = result if result["status"] == "complete" else None
        save()


def materialize_selection(root, decision, records):
    """One completed source per record, including complete no-hit records.

    Caller must obtain decision from execute(), not manufacture a native receipt
    for this composite. The manifest keeps each actual source separately.
    """
    root = Path(root).resolve()
    if (decision.get("status") != "complete" or pr.read_json(root / STATE).get("decision") != decision
            or decision.get("quality_policy") != quality.POLICY):
        raise wa.ExperimentError("pilot selection requires the current verified decision")
    def inputs_unchanged():
        for source in decision["input_binding"]:
            if wa.verified_sha256(Path(source["path"])) != source["sha256"]:
                raise wa.ExperimentError("pilot input changed before selected-source publication")
    inputs_unchanged()
    choices = decision["queries"]
    if [r["query"] for r in choices] != [r["name"] for r in records]:
        raise wa.ExperimentError("pilot selection omits/reorders original records")
    sources = {name: decision[name] for name in ("baseline", "candidate") if name in decision}
    if any(r["source"] not in sources for r in choices):
        raise wa.ExperimentError("pilot selection names an unavailable complete source")
    identity = {"policy": POLICY, "quality_policy": quality.POLICY, "records": records,
                "selected_filter": decision["selected_filter"], "choices": choices,
                "sources": {k: {n: v[n] for n in ("path", "sha256", "receipt_sha256")} for k, v in sources.items()}}
    for source in sources.values():
        if (wa.verified_sha256(Path(source["path"])) != source["sha256"]
                or wa.verified_sha256(Path(source["directory"]) / "native-attempt.json") != source["receipt_sha256"]):
            raise wa.ExperimentError("completed pilot source changed before selection")
    output, marker = root / "pilot.selected.paf", root / "pilot-selected.json"
    if marker.exists():
        old = pr.read_json(marker)
        if old.get("identity") == identity:
            if wa.verified_sha256(output) != old["sha256"]:raise wa.ExperimentError("pilot selection changed")
            return old
    pr.archive_partial(output); pr.archive_partial(marker)
    pending = root / "pilot.selected.partial.paf"; pr.archive_partial(pending)
    rows = []; overall = hashlib.sha256()
    with pending.open("xb") as out:
        for choice in choices:
            source = sources[choice["source"]]; digest = hashlib.sha256(); selected = hashlib.sha256(); count = 0
            with Path(source["path"]).open("rb") as stream:
                for line in stream:
                    digest.update(line)
                    if line.split(b"\t", 1)[0].decode("ascii") == choice["query"]:
                        out.write(line); overall.update(line); selected.update(line); count += 1
            if digest.hexdigest() != source["sha256"]:
                raise wa.ExperimentError("pilot source changed while selecting complete records")
            rows.append({**choice, "source_path": source["path"], "source_sha256": source["sha256"],
                         "rows": count, "selected_rows_sha256": selected.hexdigest(), "complete_no_hit": count == 0})
    inputs_unchanged()
    for source in sources.values():
        if wa.verified_sha256(Path(source["directory"]) / "native-attempt.json") != source["receipt_sha256"]:
            raise wa.ExperimentError("pilot receipt changed during selected-source publication")
    pending.rename(output)
    result = {"identity": identity, "path": str(output), "sha256": overall.hexdigest(), "queries": rows,
              "status": "complete_pilot_sources_only", "whole_workload_approved": False,
              "partial_PAF_reused": False, "sources_combined_within_query": False}
    wa.write_json(marker, result)
    return result
