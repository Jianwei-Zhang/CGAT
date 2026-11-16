"""Automatic finite pilot decision and materialization from completed native runs.

The workload (not its small pilot) triggers screening. Select the least aggressive
measured filter whose two completed repeats meet the speed floor and whose
complete-record fallback fits the finite review budget. Publish exactly ONE
source per pilot query, in original query order. No mapper is called here.

This is a reusable execution boundary, not whole-workload production admission:
whole-workload inputs/routing and future review costs still need execution proof.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import time

import adaptive_screening as policy
import audit_adaptive_pilot as audit
import benchmark_ordinary_partitions as validator
import catalog_adaptive_inputs as input_catalogue
import windowed_alignment as wa

POLICY = "automatic-complete-native-sources-v1"


@dataclass(frozen=True)
class ReviewBudget:
    max_records: int = 32
    max_bases_fraction: float = 0.05


def choose(reference_bases, workload_records, pilot_records, audited, *, budget=ReviewBudget()):
    """Pure internal decision; caller must obtain audited via the actual auditor.

    Size alone never changes sensitivity. A timeout lower bound cannot select a
    filter. Cost applies to every positive fallback base, without netting gains.
    """
    if (type(budget.max_records) is not int or budget.max_records < 0
            or not math.isfinite(budget.max_bases_fraction)
            or not 0 <= budget.max_bases_fraction <= 1):
        raise ValueError("finite nonnegative record/base review budget required")
    lengths = policy.record_lengths(pilot_records)
    workload = policy.record_lengths(workload_records)
    if not all(workload.get(q) == n for q, n in lengths.items()):
        raise ValueError("pilot must contain complete records from the actual workload")
    if audited.get("status") != "audited_completed_artifacts":
        raise ValueError("completed source audit required")
    gate = policy.screening_gate(reference_bases, workload_records)
    result = {"policy": POLICY, "workload_gate": gate, "review_budget": asdict(budget),
              "selected_filter": "default", "candidates": [],
              "selection_reason": "standard_shape" if gate["action"] == "standard" else "no_bounded_candidate",
              "queries": [{"query": q, "source": "baseline", "reasons": []} for q in lengths],
              "quality_policy": policy.POLICY, "pilot_output_only": True, "production_approved": False,
              "hybrid_speedup_measured": False, "new_mapping_commands": 0}
    if gate["action"] == "standard":
        return result
    for fraction in ("0.005", "0.01"):
        comparisons = [c for c in audited["comparisons"] if c["fraction"] == fraction]
        reviews = [r for r in audited["completed_record_review_plans"] if r["fraction"] == fraction]
        row = {"fraction": fraction, "eligible": False}
        result["candidates"].append(row)
        if (len(comparisons) != 2 or {c["repeat"] for c in comparisons} != {0, 1}
                or any(not isinstance(c.get("speedup"), (int, float))
                       or not math.isfinite(c["speedup"])
                       or c["speedup"] < policy.Limits().minimum_speedup for c in comparisons)):
            row["reason"] = "two_complete_speed_measurements_required"
            continue
        if (len(reviews) != 1 or reviews[0].get("status") != "completed_record_review_planned"
                or reviews[0].get("completed_source_hashes_verified") is not True
                or reviews[0].get("reviewed_loss", {}).get("passed") is not True):
            row["reason"] = "repeatable_complete_record_review_required"
            continue
        decisions = reviews[0]["queries"]
        names = [r["query"] for r in decisions]
        if names != list(lengths) or any(r["source"] not in ("baseline", "candidate") for r in decisions):
            raise ValueError("review must decide exactly once in original query order")
        fallback = [r["query"] for r in decisions if r["source"] == "baseline"]
        bases = sum(lengths[q] for q in fallback)
        row.update(review_records=len(fallback), review_bases=bases,
                   review_bases_fraction=bases / sum(lengths.values()),
                   measured_candidate_speedups=[c["speedup"] for c in comparisons])
        if (len(fallback) > budget.max_records
                or bases / sum(lengths.values()) > budget.max_bases_fraction):
            row["reason"] = "finite_review_budget_exceeded"
            continue
        if len(fallback) == len(lengths):
            row["reason"] = "no_filtered_records_remain"
            continue
        row.update(eligible=True, reason="bounded_completed_sources_selected")
        result.update(selected_filter=fraction, queries=decisions,
                      selection_reason="weakest_filter_with_paired_gain_and_bounded_review")
        break
    return result


def _json(path, limit=32 * 1024**2):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("bounded regular receipt required")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError("receipt grew beyond bounded audit size")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def materialize(report_path, workload_catalogue, subset_receipt, out):
    """Execute the internal decision, preserving raw row bytes and provenance.

    Inputs are a completed paired pilot, its exact complete-record extraction
    receipt and the full workload catalogue. Fresh record-level sequence digests
    establish membership even when the pilot was extracted through intermediate
    subsets; an incidental catalogue-path/receipt link cannot veto equal content.
    Current pilot/reference FASTA bytes are checked; the original whole workload
    is NOT reread or certified by this bounded finalizer. No formal result.paf is
    written, and incomplete/timed-out PAFs never become input sources.
    """
    report_path, workload_catalogue, subset_receipt, out = map(Path,
        (report_path, workload_catalogue, subset_receipt, out))
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    receipt = {"status": "running", "policy": POLICY, "quality_policy": policy.POLICY, "mapper_executed": False,
               "production_approved": False, "whole_workload_source_revalidated": False}
    receipt_path = out / "selected-sources.json"
    wa.write_json(receipt_path, receipt)
    guarded = {}
    def guard(path):
        path = Path(path)
        digest = wa.verified_sha256(path)
        guarded[str(path)] = digest
        return digest
    try:
        receipt["implementation_sha256"] = {module: guard(Path(file)) for module, file in
            (("materializer", __file__), ("auditor", audit.__file__),
             ("policy", policy.__file__), ("paf_validator", validator.__file__),
             ("content_identity", wa.__file__), ("sequence_catalogue", input_catalogue.__file__))}
        report, report_hash = _json(report_path)
        catalogue, catalogue_hash = _json(workload_catalogue)
        subset, subset_hash = _json(subset_receipt)
        for p, digest in ((report_path, report_hash), (workload_catalogue, catalogue_hash),
                          (subset_receipt, subset_hash)):
            if guard(p) != digest:
                raise ValueError("receipt changed between parsing and content binding")
        if (catalogue.get("status") != "complete" or subset.get("status") != "complete"
                or subset.get("source_unchanged") is not True):
            raise ValueError("completed workload catalogue and extraction receipt required")
        direct_link = subset.get("catalogue_sha256") == catalogue_hash
        if direct_link and subset.get("source_decompressed_sha256") != catalogue.get("decompressed_sha256"):
            raise ValueError("direct catalogue link contradicts its source content")
        all_records = {r["name"]: r for r in catalogue["records"]}
        lengths = policy.record_lengths(catalogue["records"])
        pilot = report["sources"]["query"]
        expected = [{"name": r["name"], "length": r["length"]} for r in subset["records"]]
        if (pilot["records"] != expected or pilot["sha256"] != subset["output_sha256"]
                or any(all_records.get(r["name"]) != r for r in subset["records"])
                or [q for q in lengths if q in {r["name"] for r in expected}]
                    != [r["name"] for r in expected]):
            raise ValueError("pilot content/records/order differ from complete-record extraction")
        for source in report["sources"].values():
            if guard(Path(source["source"])) != source["sha256"]:
                raise ValueError("pilot/reference source content changed")
        actual = input_catalogue.catalogue(Path(pilot["source"]))
        if (actual["decompressed_sha256"] != pilot["sha256"]
                or actual["records"] != subset["records"]):
            raise ValueError("pilot sequence content differs from workload record digests")
        receipt.update(workload_membership_verified_by="fresh_complete_record_sequence_digests",
                       direct_catalogue_link_matches=direct_link)
        audited = audit.audit(report_path)
        if audited["original_report_sha256"] != report_hash:
            raise ValueError("auditor consumed a different pilot receipt")
        decision = choose(sum(r["length"] for r in report["sources"]["reference"]["records"]),
                          catalogue["records"], pilot["records"], audited)
        fraction = decision["selected_filter"]
        baselines = [report_path.parent / f"r{repeat}-fdefault.paf" for repeat in (0, 1)
                     if f"r{repeat}-fdefault.paf" in audited["paf_sha256"]]
        if not baselines:
            raise ValueError("no completed baseline source; partial PAFs cannot be published")
        sources = {"baseline": baselines[0]}
        if any(r["source"] == "candidate" for r in decision["queries"]):
            sources["candidate"] = report_path.parent / f"r0-f{fraction}.paf"
        for name, source in sources.items():
            if guard(source) != audited["paf_sha256"].get(source.name):
                raise ValueError("selected source is not a verified complete PAF")
        # The pilot is already bounded to <=64 MiB per audited PAF. Preserve
        # within-record row order, including multiple chromosomes/strands; never
        # concatenate alternative sources for the same record or deduplicate.
        selected = {r["query"]: r["source"] for r in decision["queries"]}
        rows = {q: [] for q in selected}
        proofs = {q: [] for q in selected}
        for label, source in sources.items():
            with source.open("rb") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.endswith(b"\n"):
                        raise ValueError("incomplete PAF line")
                    query = line.split(b"\t", 1)[0].decode("ascii")
                    if selected[query] == label:
                        rows[query].append(line)
                        proofs[query].append(number)
        pending = out / "reference.selected.pending.paf"
        per_query = []
        with pending.open("xb") as output:
            for query, label in selected.items():
                payload = b"".join(rows[query]); output.write(payload)
                per_query.append({"query": query, "length": lengths[query], "source": label,
                    "filter": "default" if label == "baseline" else fraction,
                    "source_path": str(sources[label]), "source_sha256": guarded[str(sources[label])],
                    "source_rows": proofs[query], "output_rows": len(rows[query]),
                    "record_output_sha256": hashlib.sha256(payload).hexdigest()})
        total_rows = validator.validate_paf(pending, pilot["records"],
            report["sources"]["reference"]["records"], allow_empty=True)
        before = policy.coverage_profile(sources["baseline"], pilot["records"])
        after = policy.coverage_profile(pending, pilot["records"])
        quality = policy.assess_loss(before, after)
        if not quality["passed"]:
            raise ValueError("materialized full-record result failed the measured quality budget")
        if any(wa.verified_sha256(Path(p)) != digest for p, digest in guarded.items()):
            raise ValueError("source/receipt changed while finalizing")
        identity = {"policy": POLICY, "quality_policy": policy.POLICY, "query_sha256": pilot["sha256"],
                    "reference_sha256": report["sources"]["reference"]["sha256"],
                    "workload_catalogue_sha256": guarded[str(workload_catalogue)],
                    "per_query_sources": [{k: q[k] for k in
                        ("query", "length", "filter", "source_sha256", "record_output_sha256")} for q in per_query]}
        receipt["selection_identity"] = hashlib.sha256(json.dumps(identity, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        final = out / "reference.selected.experimental.paf"
        pending.rename(final)
        receipt.update(status="complete_bounded_pilot_output_not_whole_workload_acceptance",
            decision=decision, queries=per_query, quality=quality, output_path=str(final),
            output_sha256=wa.sha256(final), output_rows=total_rows,
            pilot_and_reference_sources_revalidated=True, per_query_sources_combined=False,
            hybrid_speedup_measured=False, auditor=audited)
    except BaseException as exc:
        receipt.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        receipt["guarded_sources_sha256"] = guarded
        receipt["elapsed_seconds"] = time.monotonic() - started
        wa.write_json(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workload-catalogue", type=Path, required=True)
    parser.add_argument("--subset-receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = materialize(args.report, args.workload_catalogue, args.subset_receipt, args.out)
    print(json.dumps({"status": result["status"], "selected_filter": result["decision"]["selected_filter"],
                      "output_rows": result["output_rows"], "mapper_executed": False}))


if __name__ == "__main__":
    main()
