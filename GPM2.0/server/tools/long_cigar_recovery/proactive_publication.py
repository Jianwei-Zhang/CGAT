"""Admission for direct long-query candidates, without fabricated abort receipts.

Reuses native input/stdout binding, chain completeness and overlap checks. Length
is only routing eligibility, not evidence that the customer's assertion has a
particular cause. Admission returns a private checked source, never publishes it.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import native_first as nf
import minimap_options as mo
import ordinary_partition_alignment as opa
import adaptive_ordinary_controller as oc
import proactive_reference_plan as pp
import recovery_publication as rp
import selective_reference_alignment as sr
import windowed_alignment as wa

POLICY = "proactive-original-chain-native-selection-v1"
require = rp.require


def capture_guided(name, part, root, result, pair, *, query_sha256, reference_sha256, bundle):
    witness = {"status": "proactive_long_query_eligibility", "query": name,
               "query_length": result["native_recovery"]["selection"]["queries"][name]["length"],
               "query_source_sha256": result["query"]["sha256"],
               "scope": "original_record_length_not_assertion_diagnosis"}
    # Keep the existing bounded evidence inventory/name; the receipt explicitly
    # labels this as eligibility rather than an observed overflowing operation.
    wa.write_json(root / "long-operation-witness.json", witness)
    proof = rp.capture_leaf(name, part, root, result, witness, pair,
        query_sha256=query_sha256, reference_sha256=reference_sha256, bundle=bundle, proactive=True)
    path = root / rp.PROOF
    wa.write_json(path, proof)
    return {"query": name, "rows": pair["rows"], "native_evaluation_pair": pair,
            "publication_proof_path": str(path), "publication_proof_sha256": wa.sha256(path)}


def completed_command(directory, name, root, expected):
    execution = rp.read_json(directory / (name + ".execution.json"), root)
    require(execution.get("returncode") == 0 and "interrupted" not in execution
            and execution.get("command") == expected, "proactive native command did not complete unchanged")
    require(rp.read_json(directory / (name + ".command.json"), root, expected_type=list) == expected,
            "proactive command receipt differs")
    return execution


def check_empty(row, part, group, report, root):
    directory = rp.regular_under(Path(row["directory"]) / "guidance.json", root).parent
    guidance = rp.read_json(directory / "guidance.json", root)
    window = rp.read_json(directory / "windows/experiment.json", root)
    require(wa.sha256(directory / "guidance.json") == row["guidance_sha256"]
            and guidance.get("status") == "no_candidates_in_original_part"
            and guidance.get("original_inputs_unchanged") is True
            and window.get("status") == "validated_experimental_candidate"
            and window.get("original_inputs_unchanged") is True,
            "no-candidate cell lacks complete independent window/chain evidence")
    require(guidance.get("index_sha256") == window.get("index_sha256") == part["sha256"]
            and window["target"]["sha256"] == report["reference"]["sha256"]
            and window["query"]["sha256"] == group["sha256"]
            and window["tool"]["sha256"] == report["tool"]["sha256"],
            "empty cell belongs to another input/index/tool")
    options = window["parameters"]
    require(options.get("query") == group["path"] and options.get("target") == report["reference"]["source"]
            and options.get("core_bases") == report["plan"]["window_policy"]["core_bases"]
            and options.get("context_bases") == report["plan"]["window_policy"]["context_bases"]
            and options.get("window_candidate_policy") == "all_chains_pool"
            and options.get("allow_empty_index_part") is True,
            "empty-cell mapping scope/options changed")
    mm = report["tool"]["path"]
    threads = str(options["threads"])
    require(threads.isdigit() and int(threads) > 0, "invalid empty-cell threads")
    completed_command(directory / "windows", "map", root,
        [mm, "-c", "--eqx", "-x", "asm10", "-f", str(part["mid_occ"]), "-P", "-t", threads,
         "-o", str(directory / "windows/raw.windows.paf"), part["path"], str(directory / "windows/windows.fa")])
    completed_command(directory, "whole-query", root,
        [mm, "-x", "asm10", "-f", str(part["mid_occ"]), "-t", threads,
         "-o", str(directory / "whole-query.chains.paf"), part["path"], group["path"]])
    for name in ("guided.experimental.paf", "whole-query.chains.paf", "windows/raw.windows.paf",
                 "windows/stitched.experimental.paf"):
        require(rp.regular_under(directory / name, root).stat().st_size == 0,
                "nonempty candidate was hidden as an empty cell")
    for filename, key in (("windows.json", "windows_manifest_sha256"), ("windows.fa", "windows_fasta_sha256"),
                          ("provenance.jsonl", "owned_provenance_sha256"), ("stitch-provenance.jsonl", "stitch_provenance_sha256")):
        require(wa.sha256(rp.regular_under(directory / "windows" / filename, root)) == window[key],
                "empty-cell window coverage evidence changed")
    return {"path": str(directory / "guided.experimental.paf"), "sha256": guidance["output_sha256"],
            "route": "no_candidates", "queries": [row["query"]], "parts": [part["part_index"]]}


def admit(report, root, *, bundle, ordinary_catalog=None):
    import approximate_reference_cells as ap
    root = Path(root).resolve()
    ordinary_only = report.get("routing_mode") == "adaptive_large_ordinary"
    approximate = report.get("routing_mode") == "adaptive_large_reference" or ordinary_only
    require(report.get("status") == "proactive_candidate_complete"
            and report.get("routing_mode") in ("proactive_query_length", "adaptive_large_reference", "adaptive_large_ordinary")
            and report.get("original_inputs_unchanged") is True
            and report.get("native_row_bytes_preserved") is True
            and report.get("partial_PAF_reused") is False
            and all(report.get(k) is False for k in ("whole_input_failure_trial", "bisection", "singleton_assertion_replay")),
            "not a completed proactive alignment")
    if not approximate or bundle is not None:
        require(bundle is not None and (bundle.get("runtime_abi") or {}).get("legacy_2_17_checked") is True
                and report["helper"]["sha256"] == bundle["sha256"]
                and report["helper"]["manifest_sha256"] == bundle["manifest_sha256"], "proactive helper identity differs")
    if approximate:
        require(report.get("approximate_policy") == ap.POLICY, "approximate publication policy differs")
    plan = report["plan"]
    rp.compare_json(root / "routing-plan.json", root, plan)
    catalog = rp.read_json(root / "query-catalog.json", root)
    groups = report["groups"]
    rp.compare_json(root / "inputs/groups.json", root, groups)
    require(plan == report["plan"] and groups == report["groups"]
            and catalog["source_sha256"] == plan["source_sha256"] == report["query"]["sha256"]
            and plan["risk_threshold"] == pp.MAX_OPERATION == rp.PROACTIVE_QUERY_LIMIT,
            "routing catalog/plan/source/threshold changed")
    records = catalog["records"]
    names = [r["name"] for r in records]
    ordinary = [r["name"] for r in records if r["length"] <= pp.MAX_OPERATION]
    long_names = [r["name"] for r in records if r["length"] > pp.MAX_OPERATION]
    require(names and len(names) == len(set(names)) and long_names == plan["long_queries"]
            and ordinary == plan["native_queries"] and (bool(long_names) or ordinary_only and bool(ordinary)), "proactive query routing changed")
    require(groups["all_original_records_accounted"] is True and groups["original_sequence_order"] == names,
            "group materialization omitted original queries")
    expected_groups = ([ordinary] if ordinary else []) + [[n] for n in long_names]
    require([g["queries"] for g in groups["groups"]] == expected_groups, "groups duplicate/omit/reorder original queries")
    group_by_name = {n: g for g in groups["groups"] for n in g["queries"]}
    for group in groups["groups"]:
        path = Path(group["path"])
        require(path.is_file() and not path.is_symlink() and wa.verified_sha256(path) == group["sha256"],
                "group FASTA changed after mapping")
    index_path = rp.regular_under(root / "index-context.json", root)
    require(wa.sha256(index_path) == report["index_catalog_sha256"], "original index catalog changed")
    index = json.loads(index_path.read_bytes())
    require(wa.verified_sha256(rp.regular_under(root / "target.default.mmi", root)) == index["sha256"],
            "ordinary original index changed")
    parts = index["parts"]
    require(len(parts) == report["index_part_count"] and [p["part_index"] for p in parts] == list(range(len(parts))),
            "original index parts missing/reordered")
    for part in parts:
        require(part["reference_sha256"] == report["reference"]["sha256"]
                and part["tool_sha256"] == report["tool"]["sha256"] and part["preset"] == "asm10"
                and wa.verified_sha256(rp.regular_under(part["path"], root)) == part["sha256"], "original index part changed")
    if approximate and not ordinary_only:
        require(sum(r["length"] for p in parts for r in p["records"]) >= ap.MIN_REFERENCE_BASES,
                "approximate route not eligible for this reference size")
    expected_sources = []
    if ordinary:
        if report.get("ordinary_adaptive") is not None:
            require(report.get("minimap_filter") is None, "explicit filter cannot be replaced by automatic policy")
            current_catalog = ordinary_catalog if ordinary_catalog is not None else pp.scan_query(catalog["source"])
            current_catalog.require_unchanged()
            require(current_catalog.source == catalog["source"]
                    and current_catalog.source_sha256 == catalog["source_sha256"]
                    and [pp.asdict(r) for r in current_catalog.records] == records,
                    "ordinary full-record source catalog changed")
            controller_root = rp.regular_under(root / "ordinary-adaptive" / oc.STATE, root).parent
            saved = oc.pr.read_json(controller_root / oc.STATE, fields={"identity"})
            current = oc.execute(controller_root, current_catalog, {**index, "path": str(root / "target.default.mmi")},
                report["tool"], argparse.Namespace(threads=1, memory_gib=0, minimap_batch="1G", assignment_coverage=report.get("assignment_coverage", 0.60)), readonly=True,
                unit_bases=saved["identity"]["plan"]["unit_bases"], primary_work=True, unit_seconds=None)
            reported = report["ordinary_adaptive"]
            # Reuse/cumulative-reservation diagnostics naturally differ on
            # revalidation. Bind actual sources and scientific policy, not those
            # incidental first-invocation counters.
            require(current["status"] == "complete_bounded_policy_candidate"
                    and all(current[k] == reported.get(k) for k in ("identity", "composition", "reviews", "selected_filter", "default_continuation")),
                    "automatic ordinary complete sources or decision changed")
            composed = current["composition"]
            expected_sources.append({"path": composed["path"], "sha256": composed["sha256"], "route": "native",
                                     "queries": ordinary, "parts": list(range(len(parts)))})
            mid = sr.read_shared_mid_occ(controller_root / "calibration/baseline-0/native.stderr", len(parts))
        elif report["ordinary_native"].get("kind") == opa.KIND:
            ordinary_records = [{"name": r["name"], "length": r["length"]} for r in records if r["name"] in ordinary]
            native = opa.verify(root / "ordinary-native", report["tool"]["path"], group_by_name[ordinary[0]]["path"],
                                parts, ordinary_records, fraction=report.get("minimap_filter"))
            mid = native["mid_occ"]
            for row in native["parts"]:
                expected_sources.append({"path": row["native"]["path"], "sha256": row["native"]["paf_sha256"],
                    "route": "native", "queries": ordinary, "parts": [row["part_index"]]})
        else:
            native = rp.verify_attempt(root / "ordinary-native/native-attempt.json", root, "native_success",
                tool=report["tool"]["path"], target=root / "target.default.mmi", query=group_by_name[ordinary[0]]["path"], fraction=report.get("minimap_filter"))
            mid = sr.read_shared_mid_occ(root / "ordinary-native/native.stderr", len(parts))
            expected_sources.append({"path": native["path"], "sha256": native["paf_sha256"], "route": "native",
                                     "queries": ordinary, "parts": list(range(len(parts)))})
        if report.get("ordinary_adaptive") is None:
            require(not ordinary_only, "ordinary-only adaptive route lacks verified controller")
            require(native == report["ordinary_native"], "ordinary native result changed")
    else:
        directory = root / "first-part-metadata"
        execution = report["threshold_source"]["execution"]
        command = execution["command"]
        flags = mo.seed_flags(report.get("minimap_filter"))
        prefix = [report["tool"]["path"], "-x", "asm10", *flags, "-t"]
        rest = command[len(prefix):]
        require(command[:len(prefix)] == prefix and len(rest) == 5
                and rest[0].isdigit() and int(rest[0]) > 0
                and rest[1:] == ["-o", str(directory / "empty.paf"), parts[0]["path"], str(directory / "empty.fa")],
                "all-long threshold was not read from a zero-query first-part pass")
        completed_command(directory, "metadata", root, command)
        require((directory / "empty.fa").stat().st_size == (directory / "empty.paf").stat().st_size == 0,
                "threshold metadata pass included queries")
        mid = sr.read_shared_mid_occ(directory / "metadata.stderr", 1)
    require(all(p["mid_occ"] == mid for p in parts) and report["threshold_source"]["mid_occ"] == mid,
            "later parts did not retain original first-part threshold")
    rows = report["parts"]
    expected_cells = [(n, p["part_index"]) for n in long_names for p in parts]
    require([(r["query"], r["part_index"]) for r in rows] == expected_cells,
            "long-query original-part cells omitted/duplicated/reordered")
    reviews = {}
    if approximate:
        for review in report.get("native_reviews", []):
            name = review["query"]
            require(name in long_names and name not in reviews, "native reviews omit/duplicate query identity")
            directory = rp.regular_under(Path(review["directory"]) / "quality-review.json", root).parent
            verified = ap.verify_review(directory, group_by_name[name], {**index, "path": str(root / "target.default.mmi")},
                report["tool"], argparse.Namespace(minimap_filter=report.get("minimap_filter")))
            require(review == verified, "native quality review completion changed")
            reviews[name] = review
    proofs, empty, projected, inserted_reviews = [], 0, [], set()
    for row in rows:
        part = parts[row["part_index"]]
        if row["query"] in reviews:
            name = row["query"]
            if name not in inserted_reviews:
                native = reviews[name]["native"]
                expected_sources.append({"path": native["path"], "sha256": native["paf_sha256"], "route": "native",
                                         "queries": [name], "parts": list(range(len(parts)))})
                inserted_reviews.add(name)
            continue
        if row.get("kind") == ap.POLICY:
            require(approximate, "approximate cell cannot enter native-confidence recovery admission")
            directory = rp.regular_under(Path(row["directory"]) / ap.MANIFEST, root).parent
            group = group_by_name[row["query"]]
            length = next(r["length"] for r in records if r["name"] == row["query"])
            expected = ap.identity(row["query"], length, group["sha256"], report["reference"]["sha256"], report["tool"], part)
            proof = ap.verify(directory, expected, report["tool"], part)
            require(proof == row, "approximate cell completion receipt changed")
            projected.append(row)
            expected_sources.append({"path": row["path"], "sha256": row["sha256"], "route": "approximate",
                                     "queries": [row["query"]], "parts": [part["part_index"]]})
            continue
        rp.regular_under(Path(row["directory"]) / "guidance.json", root)
        if row["status"] == "no_candidates_in_original_part":
            expected_sources.append(check_empty(row, part, group_by_name[row["query"]], report, root))
            empty += 1
        else:
            require(row["status"] == "validated_experimental_guidance", "long cell did not finish")
            require(bundle is not None, "legacy recovered cell requires its original native companion proof")
            recovery = row["publication"]
            proof = rp.check_leaf(recovery, Path(row["directory"]), part, report, bundle, sr.validate_row,
                                  eligibility="proactive_query_length")
            require(proof["query"] == row["query"] and proof["query_length"] > pp.MAX_OPERATION
                    and proof["query_length"] == next(r["length"] for r in records if r["name"] == row["query"]),
                    "recovered cell lost proactive eligibility")
            proofs.append(proof)
            pair = proof["paired_paths"]
            expected_sources.append({"path": pair["path"] if approximate else pair["public_path"],
                                     "sha256": pair["sha256"] if approximate else pair["public_sha256"],
                                     "route": "legacy_recovered" if approximate else "recovered",
                                     "queries": [row["query"]], "parts": [row["part_index"]]})
    if approximate:
        import adaptive_screening as screening
        projected_names = [n for n in long_names if any(r["query"] == n for r in projected)]
        reviewed = report.get("projection_screening", [])
        require([r["query"] for r in reviewed] == projected_names, "whole-query projection screening omitted/reordered queries")
        for row in reviewed:
            source = rp.regular_under(row["path"], root)
            expected = [{"path": r["path"], "sha256": r["sha256"]} for r in expected_sources if r["queries"] == [row["query"]]]
            require(row["sources"] == expected and wa.verified_sha256(source) == row["sha256"],
                    "whole-query screening lost its all-part sources")
            length = next(r["length"] for r in records if r["name"] == row["query"])
            profile = screening.coverage_profile(source, [{"name": row["query"], "length": length}])
            current = screening.screen_candidate_projection(profile, screening.assignment_limits(report.get("assignment_coverage", 0.60)))
            require(profile == row["profile"] and current == row["screening"] and row["approved"] is True
                    and all(r["action"] == "no_obvious_assignment_risk" for r in current["queries"]),
                    "approximate whole-query risk is unresolved")
        assembly = report["combination"]
        require(assembly["all_cells_completed"] is True and assembly["original_cells"] == len(names)*len(parts)
                and assembly["native_cells"] == (len(ordinary)+len(reviews))*len(parts) and assembly["sources"] == expected_sources
                and report.get("approximate_query_part_cells") == len(projected),
                "approximate assembly omitted/duplicated original cells")
        output = rp.regular_under(report["output_path"], root)
        require(wa.verified_sha256(output) == report["output_sha256"], "complete approximate candidate changed")
        return {"schema": 1, "policy": oc.POLICY if ordinary_only else ap.POLICY,
                "ordinary_policy": oc.POLICY if report.get("ordinary_adaptive") is not None else None,
                "status": "complete_approximate_reference_admitted",
                "path": str(output), "sha256": report["output_sha256"], "original_cells": len(names)*len(parts),
                "approximate_cells": len(projected), "legacy_recovered_cells": len(proofs), "native_reviewed_queries": sorted(reviews),
                "native_confidence_reconstructed": False, "whole_query_dp_equivalence_certified": False,
                "result_published": False}
    for key in ("combination", "native_evaluation_combination"):
        assembly = report[key]
        require(assembly["all_cells_completed"] is True and assembly["original_cells"] == len(names)*len(parts)
                and assembly["native_cells"] == len(ordinary)*len(parts) and assembly["recovered_cells"] == len(proofs)
                and assembly["no_candidate_cells"] == empty and assembly["sources"] == expected_sources,
                "final assembly does not contain exactly all completed cells")
    replacements = report["native_evaluation_combination"]["evaluated_replacements"]
    require(replacements == sorted([p["paired_paths"] for p in proofs], key=lambda p: (p["part_index"], p["query"])),
            "native-evaluated assembly lost recovered input/stdout bindings")
    require(wa.sha256(rp.regular_under(report["output_path"], root)) == report["output_sha256"]
            and wa.sha256(rp.regular_under(report["private_path"], root)) == report["private_sha256"],
            "complete proactive candidate changed")
    return {"schema": 1, "policy": POLICY, "status": "proactive_recovery_admitted",
            "path": report["private_path"], "sha256": report["private_sha256"],
            "original_cells": len(names)*len(parts), "recovered_cells": len(proofs), "no_candidate_cells": empty,
            "whole_query_dp_equivalence_certified": False, "AS_reconstructed": False,
            "result_published": False, "customer_root_cause_confirmed": False}
