#!/usr/bin/env python3
"""Re-audit completed pilot PAFs under the current policy without re-mapping.

Original reports/PAFs are read-only. This checks recorded output identity and
mapping geometry, not present-day source FASTA contents or biological accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import adaptive_screening as policy
import benchmark_ordinary_partitions as parts
import ordinary_batch_performance as perf


def audit(path):
    if path.stat().st_size > 32 * 1024**2:
        raise ValueError("pilot receipt exceeds bounded audit size")
    raw = path.read_bytes()
    original = json.loads(raw)
    if (original.get("status") not in ("screening_completed_not_production_acceptance", "budget_exhausted")
            or original.get("input_content_unchanged") is not True):
        raise ValueError("terminal source-verified pilot required; never audit a running attempt")
    queries, targets = original["sources"]["query"]["records"], original["sources"]["reference"]["records"]
    policy.record_lengths(queries); policy.record_lengths(targets)
    profiles, runs, paf_hashes = {}, {}, {}
    for run in original["runs"]:
        rep, fraction = run["repeat"], run["fraction"]
        key = (rep, fraction)
        if type(rep) is not int or rep not in (0, 1) or fraction not in ("default", "0.005", "0.01") or key in runs:
            raise ValueError("invalid/duplicate pilot condition")
        runs[key] = run
        if run["outcome"] != "completed":
            continue
        if type(run["mid_occ"]) is not int or run["mid_occ"] < 1:
            raise ValueError("invalid effective filtering threshold")
        paf = path.parent / f"r{rep}-f{fraction}.paf"
        if paf.is_symlink() or not paf.is_file() or paf.stat().st_size > 64 * 1024**2:
            raise ValueError("regular bounded PAF required")
        digest = perf.sha256(paf)
        if digest != run["paf_sha256"]:
            raise ValueError("completed PAF changed")
        parts.validate_paf(paf, queries, targets, allow_empty=True)
        profiles[key] = policy.coverage_profile(paf, queries)
        if perf.sha256(paf) != digest:
            raise ValueError("PAF changed during audit")
        paf_hashes[paf.name] = digest
    comparisons = []
    for rep in (0, 1):
        baseline = runs.get((rep, "default"))
        if baseline is None:
            continue
        for fraction in ("0.005", "0.01"):
            candidate = runs.get((rep, fraction))
            if candidate is not None:
                result = policy.compare(baseline, candidate, profiles.get((rep, "default")), profiles.get((rep, fraction)))
                comparisons.append({"repeat": rep, "fraction": fraction, **result})
    eligible = []
    for fraction in ("0.005", "0.01"):
        selected = [c for c in comparisons if c["fraction"] == fraction]
        if len(selected) == 2 and all(c["eligible"] for c in selected):
            # Repeatability applies to both baseline and candidate, even when
            # the old report claimed success under an earlier auditor.
            for condition in ("default", fraction):
                if runs[0, condition]["paf_sha256"] != runs[1, condition]["paf_sha256"]:
                    raise ValueError("same-policy paired outputs differ")
            eligible.append(fraction)
    reviews = []
    for fraction in ("0.005", "0.01"):
        keys = [(rep, value) for rep in (0, 1) for value in ("default", fraction)]
        if not all(key in profiles for key in keys):
            continue  # Partial/timed-out/missing baselines cannot seed review.
        if any(runs[0, value]["paf_sha256"] != runs[1, value]["paf_sha256"]
               for value in ("default", fraction)):
            continue
        review = policy.plan_completed_record_review(profiles[0, "default"], profiles[0, fraction])
        reviews.append({"fraction": fraction, **review, "completed_source_hashes_verified": True,
                        "baseline_paf_sha256": runs[0, "default"]["paf_sha256"],
                        "candidate_paf_sha256": runs[0, fraction]["paf_sha256"]})
    if path.read_bytes() != raw:
        raise ValueError("pilot report changed during audit")
    return {"status": "audited_completed_artifacts", "policy": policy.POLICY,
            "original_policy": original.get("policy"), "original_report_sha256": hashlib.sha256(raw).hexdigest(),
            "auditor_sha256": perf.sha256(__file__), "policy_sha256": perf.sha256(policy.__file__),
            "paf_validator_sha256": perf.sha256(parts.__file__), "paf_sha256": paf_hashes,
            "comparisons": comparisons, "completed_record_review_plans": reviews,
            "eligible_for_expanded_validation": eligible,
            "selected_for_next_experiment": eligible[0] if eligible else None,
            "mapper_executed": False, "source_fasta_revalidated": False, "production_approved": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    result = audit(args.report)
    with args.out.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "policy", "selected_for_next_experiment")}))


if __name__ == "__main__":
    main()
