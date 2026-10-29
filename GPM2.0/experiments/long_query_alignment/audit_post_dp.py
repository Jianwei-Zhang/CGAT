#!/usr/bin/env python3
"""Bounded score/chain-selection audit. No new recovery or filtering algorithm.

-P is diagnostic only: its rows and MAPQ never become final Server evidence.
Keep the existing guidance refusal intact and expose why AS-only selection fails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import shutil
import subprocess
import struct

import guided_alignment as ga
import windowed_alignment as wa
import stream_seed_trace as st
from compare_small_fixtures import relation_signature, write_fasta


RATIO = 0.8


def fixtures():
    rng = random.Random(29102031)
    query = bytes(rng.choices(b"ACGT", k=200_000))
    block = bytes(rng.choices(b"ACGT", k=2000))
    middle = query[:99_000] + block + query[101_000:]
    mixed = bytearray(query)
    for index in range(0, 185_000, 75):
        mixed[index] = b"ACGT"[(b"ACGT".index(mixed[index]) + 1) % 4]
    mixed[185_000:187_000] = block
    return [("identity", {"exact": query}, query),
            ("split_decoy", {"exact": query, "decoy": middle}, query),
            ("chain_score_not_alignment_score", {"exact": query, "decoy": bytes(mixed)}, query)]


def read_paf(path, cigar_required):
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) < 12:
            raise wa.ExperimentError("invalid audit PAF")
        tags = {}
        for field in fields[12:]:
            name, _, value = field.split(":", 2)
            if name in tags:
                raise wa.ExperimentError("duplicate audit PAF tag")
            tags[name] = value
        if "s1" not in tags or (cigar_required and not all(k in tags for k in ("cg", "AS"))):
            raise wa.ExperimentError("missing chain or DP evidence; do not guess scores")
        rows.append({"line": number, "query": fields[0], "query_length": int(fields[1]),
                     "query_start": int(fields[2]), "query_end": int(fields[3]), "strand": fields[4],
                     "target": fields[5], "target_length": int(fields[6]),
                     "target_start": int(fields[7]), "target_end": int(fields[8]),
                     "matches": int(fields[9]), "block": int(fields[10]), "mapq": int(fields[11]),
                     "chain_score": int(tags["s1"]), "alignment_score": int(tags["AS"]) if "AS" in tags else None,
                     "dp_max": int(tags["ms"]) if "ms" in tags else None,
                     "minimizers": int(tags["cm"]) if "cm" in tags else None,
                     "reported_type": tags.get("tp"), "cigar": tags.get("cg"), "raw": line})
    if not rows:
        raise wa.ExperimentError("empty score audit is not evidence")
    return rows


def relation(row):
    return tuple(row[k] for k in ("query", "query_start", "query_end", "strand", "target", "target_start", "target_end", "cigar"))


def score_probe(rows, baseline):
    """A deliberately insufficient hypothesis, NOT a candidate-selection API.

    The known full-query exact fixture is the reference competitor. Even the
    aligner's own AS values cannot substitute for its parent/chain selection.
    """
    exact = [r for r in rows if r["target"] == "exact" and r["query_start"] == 0 and r["query_end"] == r["query_length"]]
    if len(exact) != 1:
        raise wa.ExperimentError("score probe requires one observed full-query exact comparator")
    parent = exact[0]
    threshold = RATIO * parent["alignment_score"]
    hypothetical = [r for r in rows if r["alignment_score"] >= threshold]
    observed = {relation(r) for r in baseline}
    false_positives = [r for r in hypothetical if relation(r) not in observed]
    return {"diagnostic_hypothesis_only": True, "ratio": RATIO, "as_threshold": threshold,
            "hypothetical_rows": len(hypothetical), "baseline_rows": len(baseline),
            "matches_baseline": {relation(r) for r in hypothetical} == observed,
            "false_positives": false_positives,
            "post_dp_chain_score_threshold_for_exact_parent": RATIO * parent["chain_score"]}



def reconstruct_split_scores(trace_path, coarse_rows, fragment_rows, *, trace_budget=None):
    """Bounded positive-strand/two-fragment provenance witness, not an aligner.

    Validate original CN anchors against coarse PAF and fragment geometry;
    do not consult fragment DP scores or reported seed counts before applying v2.31 mm_split_reg's two-part score accounting.
    Unknown trace format, joins, unsupported geometry or missing seeds fail.
    """
    candidates = [r for r in coarse_rows if r["target"] == "decoy"]
    fragments = sorted([r for r in fragment_rows if r["target"] == "decoy"], key=lambda r: r["query_start"])
    if len(candidates) != 1 or len(fragments) != 2 or any(r["strand"] != "+" for r in candidates + fragments):
        raise wa.ExperimentError("witness only supports one positive chain split into two fragments")
    coarse = candidates[0]
    if any(not (0 <= row["query_start"] < row["query_end"] <= row["query_length"]
                and 0 <= row["target_start"] < row["target_end"] <= row["target_length"])
           for row in candidates + fragments):
        raise wa.ExperimentError("coarse/fragment coordinates exceed sequence bounds")
    if any(row["query"] != coarse["query"] or row["query_length"] != coarse["query_length"]
           or row["target_length"] != coarse["target_length"] for row in fragments):
        raise wa.ExperimentError("trace/DP query identity or length does not match the coarse candidate")
    evidence = st.collect_split_counts(trace_path, coarse, fragments, trace_budget)
    counts = evidence["fragment_anchor_counts"]
    if sum(counts) != coarse["minimizers"]:
        raise wa.ExperimentError("original seed counts do not cover the split")
    f32 = lambda v: struct.unpack("f", struct.pack("f", v))[0]
    ratio = f32(f32(counts[1]) / f32(sum(counts)))
    tail = int(f32(f32(coarse["chain_score"]) * ratio) + 0.499)
    scores = [coarse["chain_score"] - tail, tail]
    return {"diagnostic_witness_only": True, "trace_sha256": evidence["trace_sha256"],
            "trace_resources": evidence["resources"],
            "original_chain_score": coarse["chain_score"], "original_anchor_count": evidence["original_anchor_count"],
            "fragment_anchor_counts": counts, "reconstructed_chain_scores": scores,
            "candidate_selection_reconstructed": False, "mapq_reconstructed": False}



def split_score_witness(trace_path, coarse_rows, dp_rows):
    witness = reconstruct_split_scores(trace_path, coarse_rows, dp_rows)
    fragments = sorted([r for r in dp_rows if r["target"] == "decoy"], key=lambda r: r["query_start"])
    if witness["fragment_anchor_counts"] != [r["minimizers"] for r in fragments]:
        raise wa.ExperimentError("original seed counts do not reproduce DP split provenance")
    scores = [r["chain_score"] for r in fragments]
    if witness["reconstructed_chain_scores"] != scores:
        raise wa.ExperimentError("seed-derived chain scores do not match diagnostic DP scores")
    return {**witness, "reported_dp_chain_scores": scores,
            "reported_dp_alignment_scores": [r["alignment_score"] for r in fragments]}


def window_pool_witness(case, target_path, query_path, mm, results):
    """Diagnostic all-chain window pool; no final guidance/refusal is changed.

    Restore simple =/X-only fixture scores from original seeds and recovered
    fragments, then compare to the short-input whole-query diagnostic oracle.
    Neither oracle scores nor its MAPQ are used to construct recovered scores.
    """
    root = case / "diagnostic-window-pool"
    root.mkdir()
    original = case / "guided/windows"
    windows = [wa.Window(**row) for row in json.loads((original / "windows.json").read_text())]
    raw = root / "raw.paf"
    wa.run_command([mm, "-x", "asm10", "-p", str(RATIO), "-P", "-c", "--eqx", "-t", "2", "-o", str(raw),
                    str(original / "target.mmi"), str(original / "windows.fa")], root, "map", 60, 4)
    query = wa.FastaStore(query_path, root / "query.bases")
    target = None
    try:
        target = wa.FastaStore(target_path, root / "target.bases")
        owned, stitched = root / "owned.diagnostic.paf", root / "stitched.diagnostic.paf"
        wa.recover(raw, owned, root / "recovery.jsonl", windows, query, target)
        wa.stitch_owned(owned, stitched, root / "stitching.jsonl", windows, query, target)
        # Map core PAF columns into the same audit shape, without inventing tags.
        whole = {name: wa.Window(name, name, row["length"], 0, row["length"], 0, row["length"])
                 for name, row in query.records.items()}
        rows = []
        for line in stitched.read_text().splitlines():
            hit = wa.parse_hit(line, whole, target.records)
            if any(op not in "=X" for _, op in hit.ops):
                raise wa.ExperimentError("score witness only supports this unambiguous =/X fixture")
            rows.append({"query": hit.query, "query_length": hit.qlen, "query_start": hit.qs, "query_end": hit.qe,
                         "target": hit.target, "target_length": hit.tlen, "target_start": hit.ts, "target_end": hit.te,
                         "strand": hit.strand, "mapq": hit.mapq,
                         "cigar": "".join(f"{n}{op}" for n, op in hit.ops),
                         "alignment_score": sum(n if op == "=" else -9*n for n, op in hit.ops)})
        oracle = results["diagnostic-all-chains"]
        if relation_signature(stitched) != relation_signature(case / "diagnostic-all-chains.paf"):
            raise wa.ExperimentError("bounded all-chain CIGAR paths differ from whole-query diagnostic oracle")
        witness = reconstruct_split_scores(case / "seed-trace.stderr", results["chains"], rows)
        fragments = sorted([r for r in rows if r["target"] == "decoy"], key=lambda r: r["query_start"])
        for row, count, score in zip(fragments, witness["fragment_anchor_counts"], witness["reconstructed_chain_scores"]):
            row.update(minimizers=count, chain_score=score)
        exact = [r for r in rows if r["target"] == "exact"]
        coarse_exact = [r for r in results["chains"] if r["target"] == "exact"]
        if len(exact) != 1 or len(coarse_exact) != 1 or exact[0]["query_start"] != 0 or exact[0]["query_end"] != exact[0]["query_length"]:
            raise wa.ExperimentError("witness requires one complete exact parent")
        exact[0].update(minimizers=coarse_exact[0]["minimizers"], chain_score=coarse_exact[0]["chain_score"])
        observed = {relation(r): r for r in oracle}
        if len(rows) != len(observed) or any(relation(r) not in observed or any(r[key] != observed[relation(r)][key]
                             for key in ("minimizers", "chain_score", "alignment_score")) for r in rows):
            raise wa.ExperimentError("window-derived scores/counts differ from diagnostic oracle")
        threshold = RATIO * exact[0]["chain_score"]
        hypothetical = [r for r in rows if r["chain_score"] >= threshold]
        if not query.unchanged() or not target.unchanged():
            raise wa.ExperimentError("score witness inputs changed")
        return {"diagnostic_only": True, "ordinary_window_pool": str(original / "stitched.experimental.paf"),
                "ordinary_pool_matches_oracle": relation_signature(original / "stitched.experimental.paf") == relation_signature(case / "diagnostic-all-chains.paf"),
                "diagnostic_paf_sha256": wa.sha256(stitched), "pool_path_relations_equal": True,
                "recovered_scores_equal_oracle": True, "rows": rows,
                "seed_counts_and_scores": witness,
                "known_exact_parent_chain_threshold": threshold,
                "threshold_illustration_matches_baseline": {relation(r) for r in hypothetical} == {relation(r) for r in results["baseline"]},
                "general_parent_selection_implemented": False, "mapq_reconstructed": False}
    finally:
        query.close()
        if target is not None:
            target.close()


def experiment(args):
    mm = shutil.which(args.minimap2)
    if not mm:
        raise wa.ExperimentError("minimap2 unavailable")
    mm = str(Path(mm).resolve())
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "production_ready": False, "customer_validated": False,
              "new_candidate_filter_implemented": False,
              "scope": "synthetic score diagnostic only; -P output is NOT production PAF or confidence",
              "harness_sha256": wa.sha256(Path(__file__)),
              "helper_sha256": {"stream_seed_trace.py": wa.sha256(Path(st.__file__)),
                                "windowed_alignment.py": wa.sha256(Path(wa.__file__)),
                                "guided_alignment.py": wa.sha256(Path(ga.__file__)),
                                "compare_small_fixtures.py": wa.sha256(Path(write_fasta.__code__.co_filename))},
              "tool": {"path": mm, "version": subprocess.check_output([mm, "--version"], text=True).strip(), "sha256": wa.sha256(Path(mm))},
              "cases": []}
    try:
        for name, targets, sequence in fixtures():
            case = root / name
            case.mkdir()
            target, query = case / "target.fa", case / "query.fa"
            write_fasta(target, targets)
            write_fasta(query, {"query": sequence})
            identities = {"target_sha256": wa.sha256(target), "query_sha256": wa.sha256(query)}
            results = {}
            for mode, flags in (("chains", []), ("baseline", ["-c", "--eqx"]), ("diagnostic-all-chains", ["-c", "--eqx", "-P"])):
                paf = case / (mode + ".paf")
                wa.run_command([mm, "-x", "asm10", "-p", str(RATIO), *flags, "-t", "2", "-o", str(paf), str(target), str(query)],
                               case, mode, 60, 4)
                results[mode] = read_paf(paf, mode != "chains")
            witness = None
            if name == "chain_score_not_alignment_score":
                trace_paf = case / "trace.chains.paf"
                wa.run_command([mm, "-x", "asm10", "-p", str(RATIO), "--print-chains", "--print-qname", "-t", "1",
                                "-o", str(trace_paf), str(target), str(query)], case, "seed-trace", 60, 4)
                if trace_paf.read_bytes() != (case / "chains.paf").read_bytes():
                    raise wa.ExperimentError("diagnostic tracing changed the coarse result")
                witness = split_score_witness(case / "seed-trace.stderr", results["chains"], results["diagnostic-all-chains"])
            record = {"case": name, **identities, "runs": results,
                      "as_only_probe": score_probe(results["diagnostic-all-chains"], results["baseline"])}
            record["seed_trace_witness"] = witness
            options = argparse.Namespace(target=target, query=query, out=case / "guided", minimap2=mm, preset="asm10",
                                         core_bases=50_000, context_bases=2000, guide_slack=1000, threads=2,
                                         timeout=60, memory_gib=4, require_full_query_coverage=False)
            try:
                guidance = ga.experiment(options)
            except wa.ExperimentError:
                guidance = json.loads((options.out / "guidance.json").read_text())
            if name == "chain_score_not_alignment_score":
                record["window_pool_witness"] = window_pool_witness(case, target, query, mm, results)
            record["guidance_status"] = guidance["status"]
            record["guidance_error"] = guidance.get("error")
            record["guided_final_exists"] = (options.out / "guided.experimental.paf").exists()
            coverage = options.out / "chain-coverage.json"
            if coverage.exists():
                record["chain_coverage"] = json.loads(coverage.read_text())
            if identities != {"target_sha256": wa.sha256(target), "query_sha256": wa.sha256(query)} or wa.sha256(Path(mm)) != report["tool"]["sha256"]:
                raise wa.ExperimentError("score audit input/tool changed")
            report["cases"].append(record)
            wa.write_json(root / "audit.json", report)
            print(json.dumps({k: record[k] for k in ("case", "guidance_status", "guidance_error", "guided_final_exists")}), flush=True)
        report["status"] = "completed_diagnostics_not_recovery_acceptance"
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root / "audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--out", type=Path, required=True)
    experiment(parser.parse_args())


if __name__ == "__main__":
    main()
