#!/usr/bin/env python3
"""Deferred synthetic normal-input regressions for parameter candidates.

This does NOT test the 270 Mb assertion itself and never reads customer data.
Run only in the final validation phase. Exit-zero alone is never acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import windowed_alignment as wa
from compare_small_fixtures import fixtures, relation_signature, write_fasta

CANDIDATES = {
    "default": {"preset":"asm10", "flags":[]},
    "no_long_join_narrow_band": {"preset":"asm10", "flags":["--no-long-join", "-r", "500,1000"]},
    "query_batch_50M": {"preset":"asm10", "flags":["-K", "50M"]},
    "index_batch_50M": {"preset":"asm10", "flags":["-I", "50M"]},
    "asm5": {"preset":"asm5", "flags":[]},
    "zdrop_1": {"preset":"asm10", "flags":["-z", "1,1"]},
    "sw_cap_1M": {"preset":"asm10", "flags":["--cap-sw-mem=1M"]},
    "max_qlen_1M": {"preset":"asm10", "flags":["--max-qlen=1M"], "data_omission_expected":True},
}


def paf_summary(path):
    """Strict =/X PAF semantics plus candidate/confidence metadata."""
    rows, pairs, intervals, confidence, types = 0, Counter(), defaultdict(list), Counter(), Counter()
    exact_rows = Counter()
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith("\n"):
                raise wa.ExperimentError("incomplete parameter-control PAF line")
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 12:
                raise wa.ExperimentError("invalid parameter-control PAF")
            qlen, qs, qe = map(int, fields[1:4])
            tlen, ts, te = map(int, fields[6:9])
            mapq = int(fields[11])
            if fields[4] not in ("+", "-") or not (0 <= qs < qe <= qlen and 0 <= ts < te <= tlen and 0 <= mapq <= 255):
                raise wa.ExperimentError("invalid parameter-control coordinates/confidence")
            tags = {}
            for raw in fields[12:]:
                pieces = raw.split(":",2)
                if len(pieces) != 3 or pieces[0] in tags:
                    raise wa.ExperimentError("invalid/duplicate parameter-control tag")
                tags[pieces[0]] = pieces[2]
            cigar = tags.get("cg")
            if cigar is None:
                raise wa.ExperimentError("parameter-control PAF requires CIGAR")
            ops = [(int(size), op) for size,op in wa.OP_RE.findall(cigar)]
            if not ops or "".join(f"{size}{op}" for size,op in ops) != cigar or any(op not in "=XID" for _,op in ops):
                raise wa.ExperimentError("parameter-control PAF requires unambiguous --eqx CIGAR")
            if sum(size for size,op in ops if op in wa.Q_OPS) != qe-qs or sum(size for size,op in ops if op in wa.T_OPS) != te-ts:
                raise wa.ExperimentError("parameter-control CIGAR consumption mismatch")
            rows += 1
            pair = (fields[0], fields[5], fields[4])
            pairs[pair] += 1
            intervals[pair].append((qs,qe))
            confidence[mapq] += 1
            types[tags.get("tp", "missing")] += 1
            exact_key = json.dumps([fields[0],qlen,qs,qe,fields[4],fields[5],tlen,ts,te,cigar,mapq,tags.get("tp")],
                                   separators=(",",":"))
            exact_rows[exact_key] += 1
    merged = {json.dumps(key):wa.coverage(value) for key,value in sorted(intervals.items())}
    return {"rows":rows, "pair_strand_rows":{json.dumps(k):v for k,v in sorted(pairs.items())},
            "query_coverage_by_pair_strand":merged,
            "mapq_histogram":dict(sorted(confidence.items())), "type_histogram":dict(sorted(types.items())),
            "unknown_mapq_rows":confidence[255],
            "exact_row_multiset_sha256":hashlib.sha256(json.dumps(sorted(exact_rows.items()),
                                                                  separators=(",",":"), sort_keys=True).encode()).hexdigest(),
            "empty":rows == 0}


def compare_contract(baseline, candidate):
    if candidate.get("status") != "success":
        return {"checks":{"execution_and_parse":False}, "all_equal":False,
                "candidate_empty":None, "normal_input_only":True,
                "long_assertion_avoided":None, "parameter_workaround_accepted":False,
                "failure":candidate.get("error","candidate did not complete")}
    checks = {"execution_and_parse":True,"aligned_base_indel_relations":baseline["relations"] == candidate["relations"],
              "row_count":baseline["summary"]["rows"] == candidate["summary"]["rows"],
              "pair_strand_multiplicity":baseline["summary"]["pair_strand_rows"] == candidate["summary"]["pair_strand_rows"],
              "pair_strand_query_coverage":baseline["summary"]["query_coverage_by_pair_strand"] == candidate["summary"]["query_coverage_by_pair_strand"],
              "mapq":baseline["summary"]["mapq_histogram"] == candidate["summary"]["mapq_histogram"],
              "primary_secondary_type":baseline["summary"]["type_histogram"] == candidate["summary"]["type_histogram"],
              "exact_row_multiset":baseline["summary"]["exact_row_multiset_sha256"] == candidate["summary"]["exact_row_multiset_sha256"]}
    return {"checks":checks, "all_equal":all(checks.values()),
            "candidate_empty":candidate["summary"]["empty"],
            "normal_input_only":True, "long_assertion_avoided":None,
            "parameter_workaround_accepted":False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--memory-gib", type=int, default=6)
    parser.add_argument("--candidate", action="append", choices=tuple(CANDIDATES),
                        help="repeatable; defaults to every candidate")
    args = parser.parse_args(argv)
    if min(args.threads,args.timeout,args.memory_gib) < 1:
        parser.error("resource limits must be positive")
    mm = shutil.which(args.minimap2)
    if not mm:
        parser.error("minimap2 unavailable")
    mm = str(Path(mm).resolve())
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    names = list(dict.fromkeys(args.candidate or CANDIDATES))
    if "default" not in names:
        names.insert(0,"default")
    report = {"status":"running", "production_ready":False, "customer_validated":False,
              "scope":"normal synthetic inputs only; not 270 Mb assertion acceptance",
              "tool":{"path":mm, "version":subprocess.check_output([mm,"--version"],text=True).strip(),
                      "sha256":wa.sha256(Path(mm))},
              "candidates":{name:{"spec":CANDIDATES[name], "cases":[]} for name in names}}
    wa.write_json(root/"parameter-control-comparison.json",report)
    for case_name, references, bases in fixtures():
        case = root/case_name
        case.mkdir()
        target, query = case/"target.fa", case/"query.fa"
        write_fasta(target,references)
        write_fasta(query,{"query":bases})
        observations = {}
        for name in names:
            spec = CANDIDATES[name]
            directory = case/name
            directory.mkdir()
            paf = directory/"result.paf"
            command = [mm,"-c","--eqx","-x",spec["preset"],*spec["flags"],"-t",str(args.threads),
                       "-o",str(paf),str(target),str(query)]
            try:
                wa.run_command(command,directory,"map",args.timeout,args.memory_gib)
                observations[name] = {"status":"success", "summary":paf_summary(paf),
                                      "relations":relation_signature(paf),
                                      "paf_sha256":wa.sha256(paf), "command":command}
            except wa.ExperimentError as exc:
                observations[name] = {"status":"execution_or_parse_failure", "error":str(exc),
                                      "command":command,
                                      "partial_paf_sha256":wa.sha256(paf) if paf.is_file() else None}
        baseline = observations["default"]
        if baseline.get("status") != "success":
            raise wa.ExperimentError("default normal-input oracle did not complete: " + baseline.get("error","unknown"))
        for name in names:
            record = {"case":case_name, "target_sha256":wa.sha256(target), "query_sha256":wa.sha256(query),
                      **observations[name], "comparison":compare_contract(baseline,observations[name])}
            if CANDIDATES[name].get("data_omission_expected"):
                record["comparison"]["disqualified_reason"] = "configured query-length omission is not a repair"
            report["candidates"][name]["cases"].append(record)
            wa.write_json(root/"parameter-control-comparison.json",report)
    for name in names:
        records = report["candidates"][name]["cases"]
        report["candidates"][name]["all_normal_contracts_equal"] = all(r["comparison"]["all_equal"] for r in records)
        report["candidates"][name]["eligible_for_long_synthetic_evaluation"] = (
            name != "max_qlen_1M" and report["candidates"][name]["all_normal_contracts_equal"])
        report["candidates"][name]["parameter_workaround_accepted"] = False
    report["status"] = "normal_control_comparison_completed"
    wa.write_json(root/"parameter-control-comparison.json",report)
    print(json.dumps({name:{"normal_equal":row["all_normal_contracts_equal"],
                            "eligible_for_long_synthetic_evaluation":row["eligible_for_long_synthetic_evaluation"]}
                      for name,row in report["candidates"].items()},indent=2))
    print("NORMAL CONTROLS ONLY. No parameter workaround accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
