#!/usr/bin/env python3
"""Compare windowing to unsplit minimap2 on synthetic cases below its size limit.

Optional --server-dir runs ONLY prepare.sh and chromosome assignment in NEW
synthetic workspaces, never any customer workspace or the complete GRT pipeline.
Not a release gate or a claim of biological equivalence.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess

import windowed_alignment as wa


def relation_signature(path: Path) -> dict:
    """Aligned-base/indel relation union, independent of PAF row fragmentation.

    Different placements, orientation, mismatches or indel coordinates remain
    different. Only exact duplicate/contiguous pieces of the same relation merge.
    MAPQ/ranking are deliberately outside this comparison, NOT declared equal.
    """
    groups = defaultdict(list)
    for line in path.read_text().splitlines():
        f = line.split("\t")
        qs, qe, ts = int(f[2]), int(f[3]), int(f[7])
        qoffset = 0
        tags = [tag[5:] for tag in f[12:] if tag.startswith("cg:Z:")]
        if len(tags) != 1:
            raise wa.ExperimentError("one CIGAR required for relation comparison")
        cigar = tags[0]
        ops = [(int(n), op) for n, op in wa.OP_RE.findall(cigar)]
        if "".join(f"{n}{op}" for n, op in ops) != cigar:
            raise wa.ExperimentError("invalid relation CIGAR")
        for n, op in ops:
            if f[4] == "+":
                qleft = qs + qoffset
                qright = qleft + (n if op in wa.Q_OPS else 0)
            else:
                qright = qe - qoffset
                qleft = qright - (n if op in wa.Q_OPS else 0)
            if op in "=X":
                diagonal = ts - qleft if f[4] == "+" else ts + qright
                key, interval = (f[0], f[5], f[4], op, diagonal), (qleft, qright)
            elif op == "I":
                key, interval = (f[0], f[5], f[4], op, ts), (qleft, qright)
            else:
                key, interval = (f[0], f[5], f[4], op, qleft), (ts, ts + n)
            groups[key].append(interval)
            qoffset += n if op in wa.Q_OPS else 0
            ts += n if op in wa.T_OPS else 0
        if qoffset != qe - qs or ts != int(f[8]):
            raise wa.ExperimentError("relation PAF consumption mismatch")
    return {json.dumps(key): wa.coverage(intervals)["intervals"] for key, intervals in sorted(groups.items())}


def write_fasta(path: Path, records: dict[str, bytes]):
    with path.open("xb") as handle:
        for name, sequence in records.items():
            handle.write(f">{name}\n".encode())
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start:start+80] + b"\n")


def assignment(server: Path, directory: Path, target: Path, query: Path, paf: Path):
    workspace = directory / "prepared"
    with (directory / "prepare.log").open("wb") as log:
        subprocess.run(["bash", str(server / "prepare.sh"), "--ref", "reference", str(target),
                        "--ds", "assembly", str(query), "-o", str(workspace), "-t", "2", "--skip-self"],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    result = workspace / "runs/assembly_vs_ref/result.paf"
    shutil.copyfile(paf, result)
    with (directory / "assign.log").open("wb") as log:
        subprocess.run(["bash", str(workspace / "assign_chr_groups.sh")], check=True,
                       stdout=log, stderr=subprocess.STDOUT, timeout=60)
    with (workspace / "metadata/chr_assignments.tsv").open() as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return rows


def fixtures():
    rng = random.Random(29102026)
    ref = bytes(rng.choice(b"ACGT") for _ in range(2_000_000))
    insertion = bytes(rng.choice(b"ACGT") for _ in range(2048))
    mismatch = ref[:500000] + (b"C" if ref[500000:500001] != b"C" else b"A") + ref[500001:]
    nref = ref[:499800] + b"N"*400 + ref[500200:]
    repeated = ref[:499900] + b"A"*200 + ref[500100:]
    return [
        ("identity", {"chr1": ref}, ref),
        ("reverse", {"chr1": ref}, ref.translate(wa.RC)[::-1]),
        ("insertion_across_core", {"chr1": ref}, ref[:499000] + insertion + ref[499000:]),
        ("deletion_at_core", {"chr1": ref}, ref[:500000] + ref[503000:]),
        ("reverse_insertion_across_core", {"chr1": ref}, (ref[:499000] + insertion + ref[499000:]).translate(wa.RC)[::-1]),
        ("reverse_deletion_near_core", {"chr1": ref}, (ref[:500000] + ref[503000:]).translate(wa.RC)[::-1]),
        ("mismatch_at_core", {"chr1": ref}, mismatch),
        ("ambiguous_across_core", {"chr1": nref}, nref),
        ("repeat_deletion_at_core", {"chr1": repeated}, repeated[:499985] + repeated[500015:]),
        ("inversion_at_core", {"chr1": ref}, ref[:500000] + ref[500000:600000].translate(wa.RC)[::-1] + ref[600000:]),
        ("duplicated_target", {"chr1": ref, "chr2": ref}, ref),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--server-dir", type=Path)
    parser.add_argument("--case", action="append", help="Run only named fixtures (repeatable)")
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    mm = shutil.which(args.minimap2)
    if not mm:
        parser.error("minimap2 executable not found")
    mm = str(Path(mm).resolve())
    summary = {"tool": {"path": mm, "sha256": wa.sha256(Path(mm)),
                         "version": subprocess.check_output([mm, "--version"], text=True).strip()},
               "production_ready": False, "full_grt_tested": False, "cases": []}
    cases = fixtures()
    if args.case and set(args.case) - {name for name, _, _ in cases}:
        parser.error("unknown fixture name")
    for name, references, bases in cases:
        if args.case and name not in args.case:
            continue
        case = root / name
        case.mkdir()
        target, query = case / "target.fa", case / "query.fa"
        write_fasta(target, references)
        write_fasta(query, {"query": bases})
        baseline = case / "baseline"
        baseline.mkdir()
        baseline_paf = baseline / "result.paf"
        wa.run_command([mm, "-c", "--eqx", "-x", "asm10", "-t", "2", "-o", str(baseline_paf),
                        str(target), str(query)], baseline, "map", 60, 4)
        windowed = case / "windowed"
        options = argparse.Namespace(target=target, query=query, out=windowed, minimap2=mm, preset="asm10",
                                     core_bases=500000, context_bases=10000, threads=2, timeout=60, memory_gib=4,
                                     require_full_query_coverage=False)
        run = wa.experiment(options)
        candidate_paf = windowed / "owned.experimental.paf"
        before, after = relation_signature(baseline_paf), relation_signature(candidate_paf)
        stitched_paf = windowed / "stitched.experimental.paf"
        stitched = relation_signature(stitched_paf)
        record = {"case": name, "target_sha256": wa.sha256(target), "query_sha256": wa.sha256(query),
                  "query_length": len(bases), "baseline_rows": len(baseline_paf.read_text().splitlines()),
                  "windowed_rows": run["coverage"]["owned_rows"], "covered_query_bases": run["coverage"]["queries"]["query"]["covered_bases"],
                  "path_relation_equal": before == after, "stitched_relation_equal": before == stitched,
                  "stitched_rows": run["stitching"]["stitched_rows"],
                  "baseline_signature_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                  "windowed_signature_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
                  "ranking_equivalence": "not_established"}
        wa.write_json(case / "baseline-relations.json", before)
        wa.write_json(case / "windowed-relations.json", after)
        wa.write_json(case / "stitched-relations.json", stitched)
        if args.server_dir:
            server = args.server_dir.resolve()
            first = assignment(server, baseline, target, query, baseline_paf)
            second = assignment(server, windowed, target, query, candidate_paf)
            stitched_directory = case / "stitched_assignment"
            stitched_directory.mkdir()
            third = assignment(server, stitched_directory, target, query, stitched_paf)
            record.update(assignment_equal=first == second, stitched_assignment_equal=first == third,
                          baseline_assignment=first, windowed_assignment=second, stitched_assignment=third)
        summary["cases"].append(record)
        wa.write_json(root / "comparison.json", summary)
        print(json.dumps(record), flush=True)
    print("Comparisons complete; differences remain explicit. No default algorithm changed.")


if __name__ == "__main__":
    main()
