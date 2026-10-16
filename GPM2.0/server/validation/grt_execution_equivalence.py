#!/usr/bin/env python3
"""Compare baseline/optimized execution on two disposable prepared workspaces.

No input cloning/deletion occurs here. Both directories must be independent
clones of the same frozen inputs. Numerical caches may be reused; their elapsed
times are NOT cold full-pipeline benchmarks. Only raw artifact hashes (whose
headers contain workspace paths) and stage execution fingerprints are excluded
from semantic equality. Candidate/rejection tables retain exact row order/IDs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from argparse import Namespace
from types import SimpleNamespace
from pathlib import Path


def comparison(label, expected, observed):
    result = {"label": label, "status": "PASS" if expected == observed else "FAIL"}
    if isinstance(expected, (list, dict)):
        result.update(expected_count=len(expected), observed_count=len(observed))
    if expected != observed:
        result.update(expected_preview=repr(expected)[:1500], observed_preview=repr(observed)[:1500])
    return result


def semantic_result(result):
    result = dict(result)
    result.pop("input_fingerprint", None)
    result["evidence_rows"] = [
        {key: value for key, value in row.items() if key != "raw_artifact_sha256"}
        for row in result["evidence_rows"]
    ]
    return result


def compare_stage(engine, stage, baseline_dir, optimized_dir, baseline, optimized):
    checks = [comparison(f"{stage}:result", semantic_result(baseline), semantic_result(optimized))]
    q = "q2" if stage == "step2" else "q3"
    checks.append(comparison(f"{q}:file_sha256", engine.sha256_file(baseline_dir / f"grt/q/{q}.fa"),
                             engine.sha256_file(optimized_dir / f"grt/q/{q}.fa")))
    left = baseline_dir / "grt/evidence" / stage
    right = optimized_dir / "grt/evidence" / stage
    names = sorted({p.name for p in left.glob("*.tsv")} | {p.name for p in right.glob("*.tsv")})
    for name in names:
        a, b = engine.read_tsv(left / name), engine.read_tsv(right / name)
        if name == "evidence.tsv":
            a = [{k: v for k, v in row.items() if k != "raw_artifact_sha256"} for row in a]
            b = [{k: v for k, v in row.items() if k != "raw_artifact_sha256"} for row in b]
        checks.append(comparison(f"{stage}:{name}", a, b))
    return checks


def run_stage(engine, server, args, profile, previous=None):
    cli = Namespace(server_dir=server, nucmer=args.nucmer, delta_filter=args.delta_filter,
                    show_coords=args.show_coords, minimap2=args.minimap2,
                    threads=args.threads, repair_mode=engine.DEFAULT_REPAIR_MODE)
    context = args.context_factory(engine, cli) if args.context_factory else engine.execution_context(cli)
    if previous is None:
        return context, engine.run_step2(
            server, context["run_id"], context["chromosome_order"], context["q1_paths"], context["q1_records"],
            context["q1_rows"], context["donor_set"], context["donor_members"], context["assignments"],
            context["sources"], context["initial_consumed"], context["tools"], context["minimap"],
            args.threads, mummer_scope=args.scope, execution_profile=profile,
        )
    _, paths, records = engine.load_q_paths(server, "q2", previous["q_rows"], context["sources"])
    return context, engine.run_step3(
        server, context["run_id"], context["chromosome_order"], paths, records, previous["q_rows"],
        context["donor_set"], context["donor_members"], context["assignments"], context["sources"],
        context["recipe"]["primary_dataset"], [*context["initial_consumed"], *previous["accepted_intervals"]],
        context["tools"], context["minimap"], args.threads,
        mummer_scope=args.scope, execution_profile=profile,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("optimized", type=Path)
    parser.add_argument("--tools-dir", type=Path, required=True,
                        help="Pinned Server tools directory containing both stage entrypoints and grt_core")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--scope", choices=["full", "gap-screen"], default="full")
    parser.add_argument("--nucmer", default="nucmer")
    parser.add_argument("--delta-filter", default="delta-filter")
    parser.add_argument("--show-coords", default="show-coords")
    parser.add_argument("--minimap2", default="minimap2")
    parser.add_argument("--snapshot-adapter", type=Path,
                        help="Test-only validated diagnostic-export context adapter; never production validation")
    args = parser.parse_args()
    args.baseline, args.optimized = args.baseline.resolve(), args.optimized.resolve()
    if args.baseline == args.optimized:
        parser.error("workspaces must be independent")
    sys.path.insert(0, str(args.tools_dir.resolve()))
    from grt_core import repair_common, repair_runtime, step2_engine, step3_engine
    engine = SimpleNamespace(**{
        name: value
        for module in (repair_common, repair_runtime, step2_engine, step3_engine)
        for name, value in vars(module).items() if not name.startswith("_")
    })
    args.context_factory = None
    if args.snapshot_adapter:
        spec = importlib.util.spec_from_file_location("snapshot_adapter", args.snapshot_adapter)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        args.context_factory = adapter.snapshot_context
    results, times, checks = {}, {}, []
    for stage in ("step2", "step3"):
        for profile, server in (("baseline", args.baseline), ("optimized", args.optimized)):
            started = time.monotonic()
            previous = results[profile] if stage == "step3" else None
            _, (result, cache_hit) = run_stage(engine, server, args, profile, previous)
            results[profile] = result
            times[f"{profile}:{stage}"] = {"seconds": time.monotonic() - started, "stage_cache_hit": cache_hit}
        checks.extend(compare_stage(engine, stage, args.baseline, args.optimized,
                                    results["baseline"], results["optimized"]))
    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    report = {"status": status, "engine_sha256": engine.ENGINE_SHA256, "scope": args.scope,
              "boundary": "Cache-assisted exact-execution comparison; not cold full-pipeline timing",
              "excluded_provenance_fields": ["input_fingerprint", "evidence.raw_artifact_sha256"],
              "timings": times, "checks": checks}
    path = args.optimized.parent / f"execution_equivalence_{args.scope}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for check in checks:
        print(f"{check['label']}={check['status']}", flush=True)
        if check["status"] != "PASS":
            print(json.dumps(check, sort_keys=True), flush=True)
    print(f"report={path}", flush=True)
    if status != "PASS":
        raise SystemExit("Exact execution comparison failed")


if __name__ == "__main__":
    main()
