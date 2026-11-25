"""Prepare a complete tool-specific Final Path publication in private staging.

The orchestrator owns workspace locking and atomic directory promotion. An old
final directory is not a current success receipt. This writer only accepts a
successful, content-bound native execution and never falls back to LGZ on error.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

try:
    from refinement_path import build_final_path, inspect_baseline, lift_interval, write_assembly, PathError
    from post_lgz_degap import digest, stat_key, IndexedFasta
except ModuleNotFoundError:
    from .refinement_path import build_final_path, inspect_baseline, lift_interval, write_assembly, PathError
    from .post_lgz_degap import digest, stat_key, IndexedFasta


def write_json(path: Path, payload):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def write_table(path: Path, fields: list[str], rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_baseline(baseline: dict, catalog, fasta: IndexedFasta):
    gaps, records = inspect_baseline(baseline, catalog)
    if set(records) != set(fasta.records):
        raise PathError("baseline FASTA and Final Path chromosome sets differ")
    for name, record in records.items():
        if fasta.records[name][0] != record["length"]:
            raise PathError("baseline FASTA and Final Path lengths differ")
        sha256 = hashlib.sha256()
        for block in fasta.blocks(name, 0, record["length"]):
            sha256.update(block.upper())
        if sha256.hexdigest() != record["sha256"]:
            raise PathError("baseline FASTA differs from sourced Final Path")
    return gaps


def trace_source_keys(value):
    if isinstance(value, dict):
        if {"dataset", "contig", "start", "end", "orientation"} <= value.keys():
            yield value["dataset"], value["contig"]
        for child in value.values():
            yield from trace_source_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from trace_source_keys(child)


def prepare_publication(staging: Path, baseline: dict, baseline_fasta: Path, catalog,
                        edits: list, execution: dict, rejected: list[dict]) -> dict:
    if (execution.get("status") != "success" or not execution.get("run_id")
            or execution.get("baseline_sha256") != digest(baseline_fasta)):
        raise PathError("publication requires a successful baseline-bound native execution")
    artifacts = execution.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise PathError("native execution has no verifiable artifacts")
    input_identities = {baseline_fasta: stat_key(baseline_fasta)}
    for relative, sha256 in artifacts.items():
        path = catalog.root / relative
        # Native evidence belongs to this workspace, not a user-selected outside file.
        if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(catalog.root.resolve()):
            raise PathError("native evidence is outside the workspace")
        before = stat_key(path)
        if digest(path) != sha256 or stat_key(path) != before:
            raise PathError("native evidence changed before publication")
        input_identities[path] = before
    staging.mkdir(parents=True, exist_ok=False)
    final = build_final_path(baseline, catalog, edits, tool=execution["tool"],
                             recipe_sha256=execution["recipe_sha256"], baseline_artifact_sha256=execution["baseline_sha256"])
    withheld = {gid: group for group in execution.get("withheld_candidates", []) for gid in group["gap_ids"]}
    if execution.get("require_native_equality"):
        expected = execution.get("native_assembly", {})
        actual = {row["chr"]: (row["length"], row["sha256"]) for row in final["chromosomes"]}
        retained_flanks = {edit.chromosome for edit in edits if edit.evidence.get("flank_decisions")}
        withheld_chromosomes = {gap["chromosome"] for gap in final["original_gaps"] if gap["gap_id"] in withheld}
        projected = retained_flanks | withheld_chromosomes
        if (set(actual) != set(expected)
                or any(actual[name] != (row["length"], row["sha256"])
                       for name, row in expected.items() if name not in projected)):
            raise PathError("normalized Final Path does not reproduce the fully admitted native result")
    remaining = []
    write_assembly(final, catalog, staging / "assembly.fa", remaining=remaining)
    write_json(staging / "final_path.json", final)
    write_table(staging / "sources.tsv", ["dataset", "contig", "length", "fasta_path", "path_scope", "origin", "fasta_sha256"],
                catalog.manifest_rows(final))
    write_table(staging / "remaining_gaps.tsv", ["chromosome", "start", "end", "original_gap_ids", "attribution"],
                [{**row, "original_gap_ids": json.dumps(row["original_gap_ids"], separators=(",", ":"))} for row in remaining])
    original_gaps = final["original_gaps"]
    touched = {gap_id for edit in edits for gap_id in edit.gap_ids}
    residual = {gap_id for row in remaining for gap_id in row["original_gap_ids"]}
    rejected_ids = {gap_id for row in rejected for gap_id in row.get("gap_ids", [])}
    if touched & residual or touched & withheld.keys():
        raise PathError("incomplete gap cannot enter the published Final Path")
    chromosomes = {row["chr"]: row for row in final["chromosomes"]}
    outcomes = []
    for gap in original_gaps:
        gid = gap["gap_id"]
        status = "closed" if gid in touched else ("rejected" if gid in rejected_ids else "unfilled")
        retention = {}
        if gid in withheld:
            if gid not in residual or lift_interval(chromosomes[gap["chromosome"]], gap["start"], gap["end"]) is None:
                raise PathError("withheld gap was not retained intact")
            status = "unfilled"
            retention = {"reason": "incomplete_gap_kept_original",
                         "note": "Candidate did not close all its gaps; LGZ retained / 候选未完整闭合所涉缺口，保留 LGZ 原序列",
                         "candidate_residual_n_bp": withheld[gid]["residual_n_bp"],
                         "candidate_gap_ids": withheld[gid]["gap_ids"]}
        outcomes.append({**gap, "status": status, **retention,
                         "edit_ids": [edit.edit_id for edit in edits if gid in edit.gap_ids],
                         "residual_attribution": "joint" if any(gid in row["original_gap_ids"] and row["attribution"] == "joint"
                                                                 for row in remaining) else "single"})
    provenance = {"schema": "cgat.refinement-publication", "schema_version": 1, "tool": execution["tool"],
                  "run_id": execution["run_id"], "status": ("native_" + execution["native_outcome"]
                      if execution.get("native_outcome") in {"no_candidates", "no_eligible_gaps", "no_eligible_flanks", "no_remaining_gaps"}
                      else "completed" if edits else "completed_zero_accepted"),
                  "execution": execution, "baseline": final["baseline"], "accepted_edit_count": len(edits),
                  "trace_sources": [{**row, "availability": "server_audit_artifact"}
                                    for row in catalog.source_rows(set(trace_source_keys([edit.evidence for edit in edits])))],
                  "original_gap_count": len(original_gaps), "gap_outcomes": outcomes, "rejected_candidates": rejected,
                  "counts": {status: sum(g["status"] == status for g in outcomes) for status in ("closed", "partial", "unfilled", "rejected")},
                  "sequence_validation": "reconstructed_from_sources",
                  "evidence_policy": "changed coordinate evidence must be rebuilt; retained evidence requires coordinate lift",
                  "biological_accuracy_validated": False,
                  "artifacts": {name: digest(staging / name) for name in ("assembly.fa", "final_path.json", "sources.tsv", "remaining_gaps.tsv")}}
    catalog.verify_unchanged()
    if any(stat_key(path) != value for path, value in input_identities.items()):
        raise PathError("publication inputs changed")
    # Written last; absence of this receipt means incomplete staging, not success.
    write_json(staging / "provenance.json", provenance)
    return provenance
