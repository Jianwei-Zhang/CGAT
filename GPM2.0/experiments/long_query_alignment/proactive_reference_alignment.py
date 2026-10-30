#!/usr/bin/env python3
"""Direct length routing with original index context; private candidates only.

No whole-input trial, failure-driven bisection, singleton assertion replay or
parameter retries. The standalone CLI remains PLAN ONLY by default; the internal
Server adapter owns prepared-workspace permission and atomic publication. This
module only produces candidates and optional private-source admission. Durable
group resume remains a separate integration gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import guided_alignment as ga
import native_chain_state as nst
import native_first as nf
import proactive_reference_plan as pp
import proactive_publication as pub
import selective_reference_alignment as sr
import windowed_alignment as wa


def query_identity(catalog):
    """Reuse the scanner's actual byte hash instead of hashing the FASTA twice."""
    _, inode, size, mtime_ns, ctime_ns = catalog.identity
    return dict(source=catalog.source, inode=inode, size=size, mtime_ns=mtime_ns,
                ctime_ns=ctime_ns, sha256=catalog.source_sha256)


def first_part_threshold(mm, part, root, args):
    """Run unchanged mapper on zero queries, only for an all-long input.

    No sequence is skipped: every original query has its own subsequent cell.
    The first original MMI part supplies the same default threshold that upstream
    retains across the remaining index parts. This is not an alignment trial.
    """
    directory = root / "first-part-metadata"
    directory.mkdir()
    empty = directory / "empty.fa"
    empty.write_bytes(b"")
    output = directory / "empty.paf"
    command = [mm, "-x", "asm10", "-t", str(args.threads), "-o", str(output), part["path"], str(empty)]
    execution = wa.run_command(command, directory, "metadata", args.timeout, args.memory_gib)
    if output.read_bytes() or execution.get("returncode") != 0:
        raise wa.ExperimentError("first-part metadata pass was not a successful zero-query pass")
    mid = sr.read_shared_mid_occ(directory / "metadata.stderr", 1)
    return mid, {"kind": "zero_query_first_original_part", "mid_occ": mid,
                 "execution": execution, "stderr_sha256": wa.sha256(directory / "metadata.stderr"),
                 "part_sha256": part["sha256"], "alignment_queries": 0}


def add_empty_cell(merger, root, result, name, part):
    """An explicit zero-candidate cell, never a fabricated native-success row.

    Caller must retain the two independent successful window/coarse executions.
    This is candidate assembly, NOT formal publication admission.
    """
    public = root / "guided.experimental.paf"
    paths = (public, root / "whole-query.chains.paf", root / "windows/raw.windows.paf",
             root / "windows/stitched.experimental.paf")
    empty_sha = hashlib.sha256(b"").hexdigest()
    if (result.get("status") != "no_candidates_in_original_part"
            or result.get("original_inputs_unchanged") is not True
            or result.get("output_sha256") != empty_sha
            or any(not p.is_file() or p.is_symlink() or p.stat().st_size != 0 for p in paths)):
        raise wa.ExperimentError("empty original-part cell lacks independent zero-candidate evidence")
    for path in (root / "whole-query.execution.json", root / "windows/map.execution.json"):
        receipt = json.loads(path.read_bytes())
        if receipt.get("returncode") != 0 or "interrupted" in receipt:
            raise wa.ExperimentError("empty cell mapping did not complete")
    merger.add_no_candidates(public, name, part["part_index"])
    pair = {"part_index": part["part_index"], "query": name, "rows": 0,
            "public_path": str(public), "path": str(public),
            "public_sha256": empty_sha, "sha256": empty_sha,
            "ordered_candidate_path_equal": True, "scope": "no_candidates_in_original_part"}
    return pair


def experiment(args, *, prepared_workspace=None, admit_output=True):
    args = argparse.Namespace(**vars(args))
    args.target, args.query = args.target.resolve(), args.query.resolve()
    root = args.out.resolve()
    if root.exists() or args.out.is_symlink() or not root.parent.is_dir():
        raise wa.ExperimentError("fresh private proactive output directory required")
    pp.check_prepared_scope(root, prepared_workspace)
    if args.target.resolve() == args.query.resolve():
        raise wa.ExperimentError("initial reference mapping only; self-alignment is unsupported")
    if args.threads < 1 or args.timeout < 1 or args.memory_gib < 0:
        raise wa.ExperimentError("invalid proactive mapping resources")
    executable = shutil.which(args.minimap2)
    if not executable:
        raise wa.ExperimentError("minimap2 unavailable")
    mm = str(Path(executable).resolve())
    root.mkdir(mode=0o700)
    report = {"schema": 1, "status": "running", "production_ready": False, "result_published": False,
              "routing_mode": "proactive_query_length", "partial_PAF_reused": False,
              "whole_input_failure_trial": False, "bisection": False, "singleton_assertion_replay": False,
              "parts": [], "publication_admission": "closed_pending_proactive_contract"}
    try:
        catalog = pp.scan_query(args.query)
        plan = pp.make_plan(catalog)
        groups = pp.materialize(catalog, plan, root / "inputs", prepared_workspace=prepared_workspace)
        wa.write_json(root / "query-catalog.json", {"source": catalog.source,
            "source_sha256": catalog.source_sha256, "records": [pp.asdict(r) for r in catalog.records]})
        wa.write_json(root / "routing-plan.json", plan)
        tool = nf.source_identity(Path(mm))
        report.update(query=query_identity(catalog), plan=plan, groups=groups, tool={"path": mm, **tool})
        native_args = argparse.Namespace(**vars(args))
        if prepared_workspace is not None:
            native_args.timeout = None  # Preserve the original Server native command's unlimited wall time.
        # Normal-only: no reference normalization, MMI preprocessing or companion.
        if not plan["long_queries"]:
            reference = nf.source_identity(args.target.resolve())
            native = nf.attempt(mm, args.target.resolve(), args.query.resolve(), root / "ordinary-native", native_args)
            if native["status"] != "native_success":
                raise wa.ExperimentError("ordinary native mapping failed; no automatic failure recovery")
            catalog.require_unchanged()
            if not nf.identity_unchanged(args.target.resolve(), reference) or not nf.identity_unchanged(Path(mm), tool):
                raise wa.ExperimentError("native source/tool changed")
            report.update(status="proactive_candidate_complete", routing_mode="native_complete_unchanged",
                reference=reference, native=native, output_path=native["path"], output_sha256=native["paf_sha256"],
                native_row_bytes_preserved=True, original_inputs_unchanged=True, recovered_query_part_cells=0,
                companion_required=False, native_confidence_unchanged=True)
            return report
        if subprocess.check_output([mm, "--version"], text=True, timeout=5).strip() != "2.31-r1302":
            raise wa.ExperimentError("long-query original-state recovery requires minimap2 2.31-r1302")
        bundle = nst.validate_bundle(getattr(args, "native_state_bundle", None))
        report["helper"] = bundle
        target = wa.FastaStore(args.target, root / "target.bases")
        try:
            report["reference"] = target.identity
            index = sr.build_default_index(mm, target, root, args, tool["sha256"], reuse_single_part=True)
            queries = {r.name: {"length": r.length} for r in catalog.records}
            merger = nf.CellMerger(root / "cells", queries, target.records, index["parts"])
            ordinary = next((g for g in groups["groups"] if g["route"] == "native"), None)
            if ordinary is not None:
                native = nf.attempt(mm, root / "target.default.mmi", Path(ordinary["path"]), root / "ordinary-native", native_args)
                if native["status"] != "native_success":
                    raise wa.ExperimentError("ordinary group failed; no bisection or failed PAF reuse")
                merger.add_native(native, ordinary["queries"])
                mid = sr.read_shared_mid_occ(root / "ordinary-native/native.stderr", len(index["parts"]))
                report.update(ordinary_native=native, threshold_source={"kind": "ordinary_original_index_mapping", "mid_occ": mid})
            else:
                mid, report["threshold_source"] = first_part_threshold(mm, index["parts"][0], root, args)
            for part in index["parts"]:
                part["mid_occ"] = mid
            wa.write_json(root / "index-context.json", index)
            report.update(index_catalog_sha256=wa.sha256(root / "index-context.json"), index_part_count=len(index["parts"]))
            # Query outer loop: each long record gets ONE store, shared across
            # all original index parts, windows and whole-query guidance.
            for group in (g for g in groups["groups"] if g["route"] == "long_query"):
                name = group["queries"][0]
                number = next(r.ordinal for r in catalog.records if r.name == name)
                directory = root / f"long-{number:08d}"
                directory.mkdir()
                query = wa.FastaStore(Path(group["path"]), directory / "query.bases")
                try:
                    if query.identity["sha256"] != group["sha256"] or list(query.records) != [name]:
                        raise wa.ExperimentError("long query differs from original routed record")
                    for part in index["parts"]:
                        options = argparse.Namespace(target=args.target, query=Path(group["path"]),
                            out=directory / f"part-{part['part_index']:04d}", minimap2=mm, preset="asm10",
                            core_bases=plan["window_policy"]["core_bases"], context_bases=plan["window_policy"]["context_bases"],
                            guide_slack=min(1000, plan["window_policy"]["context_bases"]), threads=args.threads,
                            timeout=args.timeout, memory_gib=args.memory_gib, require_full_query_coverage=False,
                            index_context=part, allow_empty_index_part=True, window_candidate_policy="all_chains_pool",
                            recover_path_scores=True, native_state_bundle=Path(bundle["manifest_path"]).parent)
                        result = ga.experiment(options, shared_target=target, shared_query=query)
                        publication = None
                        if result["status"] == "no_candidates_in_original_part":
                            pair = add_empty_cell(merger, options.out, result, name, part)
                        else:
                            state = result["native_recovery"]
                            validator = lambda raw: sr.validate_row(raw, queries, target.records, {name}, "risk")
                            merger.add_recovered(options.out / "guided.experimental.paf", result["output_sha256"],
                                name, part["part_index"], validator, native_evaluated={"path": state["native_evaluated_paf"],
                                    "sha256": state["native_evaluated_sha256"]})
                            pair = merger.evaluated_cells[(part["part_index"], name)]
                            publication = pub.capture_guided(name, part, options.out, result, pair,
                                query_sha256=catalog.source_sha256, reference_sha256=target.identity["sha256"], bundle=bundle)
                        report["parts"].append({"query": name, "part_index": part["part_index"],
                            "status": result["status"], "directory": str(options.out), "pair": pair,
                            "guidance_sha256": wa.sha256(options.out / "guidance.json"), "publication": publication})
                        wa.write_json(root / "proactive-candidate.json", report)
                finally:
                    query.close()
            catalog.require_unchanged()
            if not target.unchanged() or not nf.identity_unchanged(Path(mm), tool):
                raise wa.ExperimentError("original source/tool changed before assembly")
            output = root / "reference.candidate.experimental.paf"
            private = root / "reference.native-evaluated.experimental.paf"
            report["combination"] = merger.finish(output)
            report["native_evaluation_combination"] = merger.finish(private, native_evaluated=True)
            report.update(status="proactive_candidate_complete", output_path=str(output), output_sha256=wa.sha256(output),
                private_path=str(private), private_sha256=wa.sha256(private), original_inputs_unchanged=True,
                native_row_bytes_preserved=True, recovered_query_part_cells=report["combination"]["recovered_cells"])
            if admit_output:
                report["admission"] = pub.admit(report, root, bundle=bundle)
                current_bundle = nst.validate_bundle(Path(bundle["manifest_path"]).parent)
                if any(current_bundle[k] != bundle[k] for k in ("sha256", "manifest_sha256", "platform")):
                    raise wa.ExperimentError("native companion changed during proactive execution")
            catalog.require_unchanged()
            if not target.unchanged() or not nf.identity_unchanged(Path(mm), tool):
                raise wa.ExperimentError("source/tool changed during proactive admission")
            report["publication_admission"] = ("private_source_checked_not_published" if admit_output
                                                 else "awaiting_adapter_proactive_admission")
        finally:
            target.close()
    except BaseException as exc:
        report.update(status="refused_or_failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root / "proactive-candidate.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "query", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--native-state-bundle", type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=21600)
    parser.add_argument("--memory-gib", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "plan_only", "production_ready": False, "result_published": False}))
        return 0
    try:
        report = experiment(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "refused_or_failed", "error": str(exc)}))
        return 2
    print(json.dumps({"status": report["status"], "result_published": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
