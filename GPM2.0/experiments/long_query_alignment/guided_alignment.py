#!/usr/bin/env python3
"""EXPERIMENT ONLY: whole-query chain guidance over validated windowed CIGARs.

An extra non-CIGAR pass supplies provisional placement evidence, NEVER final
alignments or DP MAPQ. Only uniquely supported, base-checked CIGAR rows survive;
every selected whole-query candidate must recover its canonical query bases.
No Server integration, self alignment, retry, minimap2 patch or ranking claim.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil

import windowed_alignment as wa


@dataclass(frozen=True)
class Chain:
    row: int
    query: str
    qlen: int
    qs: int
    qe: int
    strand: str
    target: str
    tlen: int
    ts: int
    te: int
    chain_mapq: int
    kind: str
    score: int
    minimizers: int


def read_chains(path, queries, targets):
    chains = []
    with path.open() as handle:
        for number, line in enumerate(handle, 1):
            if not line.endswith("\n"):
                raise wa.ExperimentError("incomplete whole-query chain PAF")
            f = line.rstrip("\r\n").split("\t")
            if len(f) < 15 or f[0] not in queries or f[5] not in targets:
                raise wa.ExperimentError("invalid/unknown whole-query chain identity")
            tags = {}
            for field in f[12:]:
                key = field.split(":", 1)[0]
                if key in tags:
                    raise wa.ExperimentError("duplicate whole-query chain tag")
                tags[key] = field
            if any(key in tags for key in ("cg", "AS", "ms")):
                raise wa.ExperimentError("guidance must be a separate approximate chain pass")
            try:
                if not tags["s1"].startswith("s1:i:") or not tags["cm"].startswith("cm:i:") or tags["tp"] not in ("tp:A:P", "tp:A:S"):
                    raise ValueError("unsupported chain metadata")
                chain = Chain(number, f[0], int(f[1]), int(f[2]), int(f[3]), f[4], f[5],
                              int(f[6]), int(f[7]), int(f[8]), int(f[11]), tags["tp"][-1],
                              int(tags["s1"][5:]), int(tags["cm"][5:]))
                matches, block = int(f[9]), int(f[10])
            except (KeyError, ValueError) as exc:
                raise wa.ExperimentError("invalid whole-query chain fields") from exc
            if not (chain.qlen == queries[chain.query]["length"] and chain.tlen == targets[chain.target]["length"]
                    and 0 <= chain.qs < chain.qe <= chain.qlen and 0 <= chain.ts < chain.te <= chain.tlen
                    and chain.strand in ("+", "-") and 0 <= chain.chain_mapq <= 255
                    and chain.score > 0 and chain.minimizers > 0 and 0 <= matches <= block and block > 0):
                raise wa.ExperimentError("inconsistent whole-query chain bounds/statistics")
            chains.append(chain)
    if not chains:
        raise wa.ExperimentError("no whole-query candidates; not a successful recovery")
    return chains


def query_oriented_interval(row):
    return (row.qs, row.qe) if row.strand == "+" else (row.qlen - row.qe, row.qlen - row.qs)


def pair_key(row):
    return row.query, row.target, row.strand


def overlaps(a, b, c, d):
    return max(a, c) < min(b, d)


def compatible(hit, chain, slack):
    """A conservative endpoint/diagonal corridor, not a recreated minimap chain.

    Every CIGAR vertex must remain in the endpoint-derived diagonal band. Paths
    with cancelling large indels may be rejected; never expand this silently.
    """
    if pair_key(hit) != pair_key(chain):
        return False
    if not (chain.qs - slack <= hit.qs < hit.qe <= chain.qe + slack
            and chain.ts - slack <= hit.ts < hit.te <= chain.te + slack
            and overlaps(hit.qs, hit.qe, chain.qs, chain.qe)
            and overlaps(hit.ts, hit.te, chain.ts, chain.te)):
        return False
    cqs, cqe = query_oriented_interval(chain)
    low, high = sorted((chain.ts - cqs, chain.te - cqe))
    q, _ = query_oriented_interval(hit)
    t = hit.ts
    for length, op in ((0, "="), *hit.ops):
        q += length if op in wa.Q_OPS else 0
        t += length if op in wa.T_OPS else 0
        if not low - slack <= t - q <= high + slack:
            return False
    return True


def canonical_uncovered(store, name, start, end, intervals):
    """Count actual A/C/G/T in uncovered chain query spans; N gaps stay visible."""
    missing, canonical = [], 0
    cursor = start
    for left, right in wa.coverage(intervals)["intervals"]:
        left, right = max(start, left), min(end, right)
        if right <= left or right <= cursor:
            continue
        if left > cursor:
            missing.append([cursor, left])
        cursor = max(cursor, right)
    if cursor < end:
        missing.append([cursor, end])
    for left, right in missing:
        for offset in range(left, right, wa.CHUNK):
            chunk = store.fetch(name, offset, min(right, offset + wa.CHUNK))
            canonical += sum(chunk.count(base) for base in (b"A", b"C", b"G", b"T"))
    return {"uncovered_intervals": missing, "uncovered_canonical_bases": canonical}


def select_guided(stitched, chains, output, provenance, coverage_path, query, target, slack):
    if slack < 0:
        raise wa.ExperimentError("negative chain corridor slack")
    whole_records = {name: wa.Window(name, name, row["length"], 0, row["length"], 0, row["length"])
                     for name, row in query.records.items()}
    supported = {chain.row: [] for chain in chains}
    query_intervals = {name: [] for name in query.records}
    target_intervals = {name: [] for name in target.records}
    counts = {"input_rows": 0, "kept_rows": 0, "excluded_rows": 0}
    temporary = output.with_suffix(".paf.partial")
    with stitched.open() as inp, temporary.open("x") as out, provenance.open("x") as audit:
        for number, line in enumerate(inp, 1):
            if not line.endswith("\n"):
                raise wa.ExperimentError("incomplete stitched PAF")
            hit = wa.parse_hit(line, whole_records, target.records)
            if hit.mapq != 255 or any(tag.startswith(("tp:", "AS:", "ms:")) for tag in line.rstrip().split("\t")[12:]):
                raise wa.ExperimentError("windowed DP score/ranking must not be inherited")
            matches, block, _ = wa.checked_statistics(hit, query, target)
            if (matches, block) != (hit.matches, hit.block):
                raise wa.ExperimentError("stitched counts disagree with original bases")
            candidates = [chain for chain in chains if pair_key(chain) == pair_key(hit)]
            owners = [chain for chain in candidates if compatible(hit, chain, slack)]
            record = {"stitched_row": number, "pair": pair_key(hit), "bounds": [hit.qs, hit.qe, hit.ts, hit.te],
                      "compatible_chain_rows": [chain.row for chain in owners]}
            counts["input_rows"] += 1
            if len(owners) > 1:
                record["status"] = "ambiguous_chain_ownership"
                audit.write(json.dumps(record) + "\n")
                raise wa.ExperimentError("stitched row matches multiple whole-query candidates")
            if owners:
                owner = owners[0]
                supported[owner.row].append(hit)
                query_intervals[hit.query].append((hit.qs, hit.qe))
                target_intervals[hit.target].append((hit.ts, hit.te))
                counts["kept_rows"] += 1
                record.update(status="supported", guided_row=counts["kept_rows"])
                # Deliberately keep MAPQ unknown; chain tags live only in the
                # provenance sidecar and are never called full DP confidence.
                fields = line.rstrip("\n").split("\t")
                fields = fields[:12] + [f for f in fields[12:] if not f.startswith("zp:Z:")]
                out.write("\t".join(fields) + f"\tzp:Z:experimental-chain-guided\tzg:i:{owner.row}\n")
            else:
                touching = [chain for chain in candidates if overlaps(hit.qs, hit.qe, chain.qs, chain.qe)
                            and overlaps(hit.ts, hit.te, chain.ts, chain.te)]
                if touching:
                    record["status"] = "overlapping_candidate_outside_supported_corridor"
                    audit.write(json.dumps(record) + "\n")
                    raise wa.ExperimentError("candidate geometry cannot safely be assigned to the chain corridor")
                counts["excluded_rows"] += 1
                record["status"] = "no_whole_query_placement_candidate"
            audit.write(json.dumps(record) + "\n")
    # Reject lost secondary candidates too. Do not demand nonexistent bases in
    # ambiguous N gaps, but record those intervals and preserve all candidate IDs.
    coverage = []
    for chain in chains:
        hits = supported[chain.row]
        row = {"chain": asdict(chain), "supported_rows": len(hits),
               "query_coverage": wa.coverage([(h.qs, h.qe) for h in hits]),
               "target_coverage": wa.coverage([(h.ts, h.te) for h in hits]),
               **canonical_uncovered(query, chain.query, chain.qs, chain.qe, [(h.qs, h.qe) for h in hits])}
        row["target_endpoints_recovered"] = bool(hits) and min(h.ts for h in hits) <= chain.ts + slack and max(h.te for h in hits) >= chain.te - slack
        coverage.append(row)
    wa.write_json(coverage_path, coverage)
    if not counts["kept_rows"] or any(not r["supported_rows"] or r["uncovered_canonical_bases"] or not r["target_endpoints_recovered"] for r in coverage):
        raise wa.ExperimentError("whole-query candidate not completely recovered; inspect chain coverage")
    os.replace(temporary, output)
    return {**counts, "whole_query_candidates": len(chains), "candidate_coverage": coverage,
            "queries": {name: {"length": record["length"], **wa.coverage(query_intervals[name])} for name, record in query.records.items()},
            "targets": {name: {"length": record["length"], **wa.coverage(target_intervals[name])} for name, record in target.records.items()},
            "dp_ranking_reconstructed": False, "mapq": "unknown_255"}


def require_full_query_coverage(selection):
    if not selection["queries"] or any(r["covered_bases"] != r["length"] for r in selection["queries"].values()):
        raise wa.ExperimentError("full-query-coverage acceptance failed after chain guidance")


def experiment(args, *, shared_target=None, shared_query=None):
    if args.guide_slack < 0 or args.guide_slack > args.context_bases:
        raise wa.ExperimentError("require 0 <= guide slack <= context; no automatic widening")
    if getattr(args,"recover_path_scores",False) and args.preset != "asm10":
        raise wa.ExperimentError("branch full-path scoring is pinned to asm10")
    native_bundle = getattr(args,"native_state_bundle",None)
    if native_bundle is not None and (args.preset != "asm10" or getattr(args,"index_context",None) is None):
        raise wa.ExperimentError("native chain-state recovery requires pinned asm10 original-part context")
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "experimental_only": True, "production_ready": False, "customer_validated": False,
              "harness_sha256": wa.sha256(Path(__file__)), "guide_slack": args.guide_slack,
              "caveat": "Whole-query chain selection is provisional, not post-DP ranking/MAPQ equivalence. No production import."}
    ownership = wa.ExitStack()
    try:
        stores = ownership.enter_context(wa.sequence_stores(args.target, args.query, root,
            shared_target=shared_target, shared_query=shared_query))
        target, query = stores
        report["sequence_storage"] = {"target_shared": shared_target is not None,
            "query_shared": shared_query is not None, "window_stores_reused": True}
        options = argparse.Namespace(**vars(args))
        options.out = root / "windows"
        windowed = wa.experiment(options, shared_target=target, shared_query=query)
        if native_bundle is not None and not windowed.get("stitching",{}).get("overlap_consistency_required",False):
            raise wa.ExperimentError("native recovery requires original raw overlap witnesses, not endpoint-only stitching")
        report["windowed_report_sha256"] = wa.sha256(options.out / "experiment.json")
        if target.identity["sha256"] != windowed["target"]["sha256"] or query.identity["sha256"] != windowed["query"]["sha256"]:
            raise wa.ExperimentError("inputs differ between windowed and whole-query passes")
        mm = str(Path(shutil.which(args.minimap2)).resolve())
        if wa.sha256(Path(mm)) != windowed["tool"]["sha256"]:
            raise wa.ExperimentError("minimap2 changed before whole-query pass")
        index = Path(windowed["index_path"])
        index_hash = wa.sha256(index)
        if index_hash != windowed["index_sha256"]:
            raise wa.ExperimentError("index changed between window and whole-query guidance passes")
        chain_path = root / "whole-query.chains.paf"
        inherited = getattr(args,"index_context",None)
        mapping_flags = ["-f",str(inherited["mid_occ"])] if inherited is not None else []
        wa.run_command([mm, "-x", args.preset, *mapping_flags, "-t", str(args.threads), "-o", str(chain_path), str(index), str(args.query.resolve())],
                       root, "whole-query", args.timeout, args.memory_gib)
        chain_hash = wa.sha256(chain_path)
        original = options.out / "stitched.experimental.paf"
        if (getattr(args,"allow_empty_index_part",False) and chain_path.stat().st_size == 0
                and original.stat().st_size == 0):
            # Legitimate no-hit original target part. Never use this to hide a
            # chain/window disagreement or assume every query must map here.
            if (not all(s.unchanged() for s in stores) or wa.sha256(index) != index_hash
                    or wa.sha256(Path(mm)) != windowed["tool"]["sha256"]
                    or wa.sha256(original) != windowed["stitched_sha256"] or wa.sha256(chain_path) != chain_hash):
                raise wa.ExperimentError("input/index/tool changed in no-hit target part")
            final = root / "guided.experimental.paf"
            final.open("xb").close()
            report.update(status="no_candidates_in_original_part",output_sha256=wa.sha256(final),
                          index_sha256=index_hash,index_path=str(index),tool=windowed["tool"],
                          original_inputs_unchanged=True,candidate_rows=0)
            return report
        chains = read_chains(chain_path, query.records, target.records)
        wa.write_json(root / "chains.json", [asdict(c) for c in chains])
        if native_bundle is not None:
            if windowed["tool"]["version"] != "2.31-r1302":
                raise wa.ExperimentError("native chain-state companion is pinned to minimap2 2.31-r1302")
            import native_chain_state as nst
            report["native_chain_state"] = nst.collect(query,target,inherited,windowed["tool"]["sha256"],
                native_bundle,chain_path,root/"native-chains",timeout=args.timeout,memory_gib=args.memory_gib)
        pending = root / "guided.pending.paf"
        if wa.sha256(original) != windowed["stitched_sha256"]:
            raise wa.ExperimentError("validated stitched input changed")
        if native_bundle is not None:
            import native_recovery as nr
            report["native_recovery"] = nr.recover(original,chains,pending,query=query,target=target,
                context=inherited,native_receipt=report["native_chain_state"],bundle=native_bundle,chain_paf=chain_path,
                window_root=options.out,window_report=windowed,root=root/"native-recovery",
                timeout=args.timeout,memory_gib=args.memory_gib)
            report["selection"] = report["native_recovery"]["selection"]
        else:
            report["selection"] = select_guided(original, chains, pending, root / "guide-provenance.jsonl",
                                                 root / "chain-coverage.json", query, target, args.guide_slack)
        if args.require_full_query_coverage:
            require_full_query_coverage(report["selection"])
        if getattr(args,"recover_path_scores",False):
            import whole_query_scores as wqs
            report["path_scoring"] = wqs.write_guided_path_scores(
                pending,root/"guided.path-scores.jsonl",query,target,index_sha256=index_hash)
        if (not all(s.unchanged() for s in stores) or wa.sha256(index) != index_hash
                or wa.sha256(Path(mm)) != windowed["tool"]["sha256"] or wa.sha256(original) != windowed["stitched_sha256"] or wa.sha256(chain_path) != chain_hash):
            raise wa.ExperimentError("input/index/tool changed during guided recovery")
        final = root / "guided.experimental.paf"
        os.replace(pending, final)
        report.update(status="validated_experimental_guidance", output_sha256=wa.sha256(final),
                      unfiltered_paf=str(original), unfiltered_sha256=windowed["stitched_sha256"],
                      index_sha256=index_hash, chain_paf_sha256=chain_hash,
                      tool=windowed["tool"], target=target.identity, query=query.identity,
                      original_inputs_unchanged=True)
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        ownership.close()
        wa.write_json(root / "guidance.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("target", "query", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--preset", choices=("asm5", "asm10"), default="asm10")
    parser.add_argument("--core-bases", type=int, default=50_000_000)
    parser.add_argument("--context-bases", type=int, default=100_000)
    parser.add_argument("--guide-slack", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--memory-gib", type=int, default=10)
    parser.add_argument("--require-full-query-coverage", action="store_true")
    print(json.dumps(experiment(parser.parse_args())))


if __name__ == "__main__":
    main()
