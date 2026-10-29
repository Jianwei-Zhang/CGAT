#!/usr/bin/env python3
"""Opt-in 270 Mb reproduction: unmodified baseline failure vs checked windows.

Not run in CI. Generates synthetic FASTA only, using the existing deterministic
parameter-audit generator. Requires Linux, cc, ~5 GiB disk and sufficient RAM.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import windowed_alignment as wa
import guided_alignment as ga


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--guide-chains", action="store_true", help="Also require provisional whole-query chain guidance")
    parser.add_argument("--memory-gib", type=int, default=10)
    args = parser.parse_args()
    mm = shutil.which(args.minimap2)
    if not mm:
        parser.error("minimap2 unavailable")
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    generator_source = Path(__file__).resolve().parents[2] / "server/validation/minimap2_long_cigar_parameters.py"
    spec = importlib.util.spec_from_file_location("long_cigar_parameter_audit", generator_source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (root / "generate.c").write_text(module.GENERATOR)
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", str(root / "generate.c"), "-o", str(root / "generate")], check=True)
    reference = root / "reference.fa"
    with reference.open("xb") as output:
        subprocess.run([str(root / "generate"), "270000000"], stdout=output, check=True)
    baseline = root / "baseline"
    baseline.mkdir()
    baseline_error = None
    try:
        wa.run_command([mm, "-c", "-x", "asm10", "-t", "2", "-o", str(baseline / "result.paf"),
                        str(reference), str(reference)], baseline, "map", args.timeout, args.memory_gib)
    except wa.ExperimentError as exc:
        baseline_error = str(exc)
    results = {"baseline_error": baseline_error, "baseline_execution": json.loads((baseline / "map.execution.json").read_text()),
               "same_assertion_reproduced": "mm_update_extra" in (baseline / "map.stderr").read_text(errors="replace")
                   and "qoff" in (baseline / "map.stderr").read_text(errors="replace"),
               "synthetic_only": True, "production_ready": False,
               "harness_sha256": wa.sha256(Path(__file__)), "guided": args.guide_chains, "cases": []}
    wa.write_json(root / "large-summary.json", results)
    for label in ("plus", "reverse"):
        if label == "plus":
            query = reference
        else:
            query = root / "reverse.fa"
            store = wa.FastaStore(reference, root / "reverse-input.bases")
            try:
                name, info = next(iter(store.records.items()))
                with query.open("xb") as output:
                    output.write(b">reverse_270M\n")
                    end = info["length"]
                    while end:
                        start = max(0, end-wa.CHUNK)
                        output.write(store.fetch(name, start, end).translate(wa.RC)[::-1] + b"\n")
                        end = start
            finally:
                store.close()
        options = argparse.Namespace(target=reference, query=query, out=root / label, minimap2=mm, preset="asm10",
                                     core_bases=50000000, context_bases=100000, threads=2, timeout=args.timeout,
                                     memory_gib=args.memory_gib, require_full_query_coverage=True)
        if args.guide_chains:
            options.guide_slack = 1000
            report = ga.experiment(options)
        else:
            report = wa.experiment(options)
        results["cases"].append({"name": label, "experiment": report})
        wa.write_json(root / "large-summary.json", results)
        print(label, report["status"], report["selection"] if args.guide_chains else report["stitching"], flush=True)
    print("Complete. Check baseline assertion and both coverage reports; customer biology remains unvalidated.")


if __name__ == "__main__":
    main()
