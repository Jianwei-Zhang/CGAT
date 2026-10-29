#!/usr/bin/env python3
"""Isolated -X self-alignment window/alias audit, not a Server implementation.

Uses the current production alias writer, preserves its original unordered-pair
order, and compares actual minimap2 base/indel relations (not just pair counts).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

import windowed_alignment as wa
from compare_small_fixtures import relation_signature, write_fasta


def assignment_definitions(server):
    path = server / "tools/assign_chr_groups.py"
    source = path.read_text().split('\nwork_root = Path(os.environ["GPM_FAST_WORK_ROOT"])', 1)
    if len(source) != 2:
        raise wa.ExperimentError("production assignment module boundary changed; audit adapter first")
    sys.path.insert(0, str(server / "tools"))
    try:
        namespace = {"__name__": "experimental_assignment_definitions"}
        exec(compile(source[0], str(path), "exec"), namespace)
        return namespace
    finally:
        sys.path.pop(0)


def read_aliases(path):
    targets, queries = {}, {}
    for row in path.read_text().splitlines():
        alias, original = row.split("\t")
        mapping = targets if alias.endswith("a") else queries if alias.endswith("b") else None
        if mapping is None or alias in mapping or original in mapping.values():
            raise wa.ExperimentError("invalid/ambiguous canonical aliases")
        mapping[alias] = original
    if set(targets.values()) != set(queries.values()):
        raise wa.ExperimentError("canonical target/query identities differ")
    names = sorted(targets.values(), key=lambda name: name.encode("utf-8"))
    width = max(9, len(str(len(names))))
    expected_t = {f"gpm_pair_{rank:0{width}d}a": name for rank, name in enumerate(names, 1)}
    expected_q = {f"gpm_pair_{rank:0{width}d}b": name for rank, name in enumerate(names, 1)}
    if targets != expected_t or queries != expected_q:
        raise wa.ExperimentError("canonical alias/rank contract changed; audit before windowing")
    return targets, queries


def canonical_windows(records, core, context, query_aliases):
    by_original = {original: alias for alias, original in query_aliases.items()}
    if len(by_original) != len(query_aliases) or set(records) != set(by_original):
        raise wa.ExperimentError("window records differ from canonical query aliases")
    # The rank and b stay before the window suffix. Thus same-record query is
    # greater than target a, and earlier original ranks stay before later ranks.
    return [replace(w, alias=f"{by_original[w.query]}_w{index:09d}")
            for index, w in enumerate(wa.make_windows(records, core, context))]


def validate_pairs(path, query_names, target_names):
    pairs = set()
    ranks = {name: rank for rank, name in enumerate(sorted(target_names.values(), key=lambda s: s.encode("utf-8")))}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) < 12 or fields[0] not in query_names or fields[5] not in target_names:
            raise wa.ExperimentError(f"unknown/malformed self pair at line {number}")
        query, target = query_names[fields[0]], target_names[fields[5]]
        if query not in ranks or ranks[query] >= ranks[target]:
            raise wa.ExperimentError(f"same-record or noncanonical self pair at line {number}")
        pairs.add((query, target, fields[4]))
    return sorted(pairs)


def restore_targets(source, output, aliases, original_names):
    validate_pairs(source, {name: name for name in original_names}, aliases)
    with output.open("x") as handle:
        for line in source.read_text().splitlines():
            fields = line.split("\t")
            fields[5] = aliases[fields[5]]
            handle.write("\t".join(fields) + "\n")


def fixtures():
    rng = random.Random(29102028)
    seq = bytes(rng.choice(b"ACGT") for _ in range(120_000))
    insertion = bytes(rng.choice(b"ACGT") for _ in range(600))
    records = {"ctg2": seq, "rc_ctg": seq.translate(wa.RC)[::-1], "ctg10": seq}
    return [("canonical_order", records), ("permuted_input", dict(reversed(list(records.items())))),
            ("boundary_indel", {"ctg2": seq[:29_700] + insertion + seq[29_700:], "rc_ctg": seq.translate(wa.RC)[::-1], "ctg10": seq})]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    mm = shutil.which(args.minimap2)
    if not mm:
        parser.error("minimap2 unavailable")
    server = args.server_dir.resolve()
    definitions = assignment_definitions(server)
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    summary = {"status": "running", "production_ready": False, "customer_validated": False,
               "tool": {"path": mm, "version": subprocess.check_output([mm, "--version"], text=True).strip(), "sha256": wa.sha256(Path(mm))},
               "alias_writer_sha256": wa.sha256(server / "tools/assign_chr_groups.py"),
               "harness_sha256": wa.sha256(Path(__file__)), "cases": []}
    try:
        for name, records in fixtures():
            case = root / name
            case.mkdir()
            fasta = case / "original.fa"
            write_fasta(fasta, records)
            target_path, query_path, mapping, restore = definitions["write_self_pair_inputs"](case, fasta)
            targets, queries = read_aliases(mapping)
            flags = [mm, "-c", "--eqx", "-x", "asm10", "-X", "--no-hash-name", "-m", "200", "-n", "100", "-t", "2"]
            raw = case / "baseline.raw.paf"
            wa.run_command([*flags, "-o", str(raw), str(target_path), str(query_path)], case, "baseline", 60, 4)
            expected_pairs = validate_pairs(raw, queries, targets)
            baseline = case / "baseline.paf"
            with raw.open("rb") as inp, baseline.open("xb") as out:
                subprocess.run([sys.executable, str(restore), str(mapping)], stdin=inp, stdout=out, check=True, timeout=10)
            query = wa.FastaStore(fasta, case / "query.bases")
            target = None
            try:
                target = wa.FastaStore(target_path, case / "target.bases")
                windows = canonical_windows(query.records, 30_000, 2_000, queries)
                wa.write_json(case / "windows.json", [asdict(w) for w in windows])
                wa.write_windows(case / "windows.fa", query, windows)
                raw_windows = case / "raw.windows.paf"
                wa.run_command([*flags, "-o", str(raw_windows), str(target_path), str(case / "windows.fa")], case, "windowed", 60, 4)
                actual_pairs = validate_pairs(raw_windows, {w.alias: w.query for w in windows}, targets)
                owned, stitched = case / "owned.pending.paf", case / "stitched.pending.paf"
                coverage = wa.recover(raw_windows, owned, case / "provenance.jsonl", windows, query, target)
                stitching = wa.stitch_owned(owned, stitched, case / "stitch-provenance.jsonl", windows, query, target)
                final = case / "stitched.experimental.paf"
                pending = case / "restored.pending.paf"
                restore_targets(stitched, pending, targets, records)
                if not query.unchanged() or not target.unchanged():
                    raise wa.ExperimentError("self inputs changed")
                # Negative control: ordinary gpm_window aliases must not be
                # mistaken for working -X self windows when output is empty.
                naive = wa.make_windows(query.records, 30_000, 2_000)
                wa.write_windows(case / "naive.fa", query, naive)
                naive_paf = case / "naive.paf"
                wa.run_command([*flags, "-o", str(naive_paf), str(target_path), str(case / "naive.fa")], case, "naive", 60, 4)
                if wa.sha256(Path(mm)) != summary["tool"]["sha256"]:
                    raise wa.ExperimentError("minimap2 changed during experiment")
                os.replace(pending, final)
                record = {"case": name, "pair_sets_equal": expected_pairs == actual_pairs,
                          "pairs": actual_pairs, "relation_equal": relation_signature(baseline) == relation_signature(final),
                          "baseline_rows": len(raw.read_text().splitlines()), "raw_rows": coverage["raw_rows"],
                          "stitched_rows": stitching["stitched_rows"], "naive_rows": len(naive_paf.read_text().splitlines()),
                          "original_inputs_unchanged": True, "mapq_ranking_equivalence": "not_established"}
                summary["cases"].append(record)
                print(json.dumps(record), flush=True)
            finally:
                query.close()
                if target is not None:
                    target.close()
        summary["status"] = "completed_comparisons_not_production_acceptance"
    except BaseException as exc:
        summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root / "comparison.json", summary)


if __name__ == "__main__":
    main()
