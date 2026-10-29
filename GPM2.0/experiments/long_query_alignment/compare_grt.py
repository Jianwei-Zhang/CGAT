#!/usr/bin/env python3
"""Isolated initial-reference-PAF substitution and real GRT/Final Path comparison.

Never edits Server code or an existing workspace. No windowing of independent GRT
flank/validation or chromosome-pair alignments; no claim of whole-run equivalence.
Requires the normal Server toolchain on PATH. Outputs retain raw differences.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess

import windowed_alignment as wa
from compare_small_fixtures import relation_signature, write_fasta


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures():
    rng = random.Random(29102027)
    ref = bytes(rng.choice(b"ACGT") for _ in range(800_000))
    insert = bytes(rng.choice(b"ACGT") for _ in range(2048))
    gap = ref[:399_800] + b"N" * 400 + ref[400_200:]
    donor = ref[370_000:430_000]
    cases = [
        ("identity", {"chr1": ref}, {"query": ref}),
        ("reverse_indel", {"chr1": ref}, {"query": (ref[:199_000] + insert + ref[199_000:]).translate(wa.RC)[::-1]}),
        ("gap_with_donor", {"chr1": ref}, {"query": gap, "donor": donor}),
        ("reverse_gap_with_donor", {"chr1": ref}, {"query": gap.translate(wa.RC)[::-1], "donor": donor}),
        ("competing_targets", {"chr1": ref, "chr2": ref}, {"query": ref}),
        # Full-length unique context makes the complete chain different from
        # repeated local cores. This is a deliberate negative/stress control.
        ("local_repeat_competition", {"chr1": ref, "chr2": ref[200_000:600_000]}, {"query": ref}),
        ("repeat_assignment_threshold", {"chr1": ref, "chr2": ref[:600_000]}, {"query": ref}),
    ]
    return [(name, targets, queries, None) for name, targets, queries in cases] + [
        ("gap_with_external_donor", {"chr1": ref}, {"query": gap}, {"donor": donor}),
        ("reverse_gap_with_external_donor", {"chr1": ref}, {"query": gap.translate(wa.RC)[::-1]}, {"donor": donor}),
    ]


def confidence_summary(path):
    """Expose the 255 sentinel hazard, never invent whole-contig MAPQ/ranking."""
    rows = [line.split("\t") for line in path.read_text().splitlines()]
    if any(len(row) < 12 or not 0 <= int(row[11]) <= 255 for row in rows):
        raise wa.ExperimentError("invalid PAF confidence fields")
    values = [int(row[11]) for row in rows]
    return {"rows": len(rows), "mapq_histogram": dict(sorted(Counter(values).items())),
            "numeric_mapq_ge_20": sum(v >= 20 for v in values),
            "known_mapq_ge_20": sum(20 <= v < 255 for v in values),
            "unknown_mapq": sum(v == 255 for v in values),
            "primary_tags": sum("tp:A:P" in row[12:] for row in rows),
            "secondary_tags": sum("tp:A:S" in row[12:] for row in rows)}


def read_tsv(path):
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def run_grt(server, directory, target, query, paf, donor=None):
    workspace = directory / "prepared"
    extra = ["--ds", "donors", str(donor)] if donor else []
    wa.run_command(["bash", str(server / "prepare.sh"), "--ref", "reference", str(target),
                    "--ds", "assembly", str(query), "-o", str(workspace), "-t", "2", "--skip-self", *extra],
                   directory, "prepare", 120, 6)
    result = workspace / "runs/assembly_vs_ref/result.paf"
    shutil.copyfile(paf, result)
    (result.parent / "tool_version.txt").write_text(subprocess.check_output(["minimap2", "--version"], text=True))
    wa.write_json(result.parent / "EXPERIMENTAL_SUBSTITUTION.json", {
        "production_ready": False, "original_command_not_executed": True,
        "input_paf": str(paf), "sha256": wa.sha256(paf),
        "scope": "isolated synthetic initial-reference comparison only",
    })
    if donor:
        # The donor/reference mapping is a genuine ordinary whole-record run
        # in BOTH workspaces. Only the primary initial PAF is substituted.
        wa.run_command(["bash", str(workspace / "runs/donors_vs_ref/command.sh")], directory, "donor-ref", 60, 6)
    # Run generated, unchanged scripts; do not mark scheduler checkpoints as
    # successful and do not run run_all (which would regenerate the input PAF).
    scripts = ["assign_chr_groups.sh", "prepare_grt_inputs.sh", "run_grt_step1.sh",
               "run_grt_step2.sh", "run_grt_step3.sh", "run_grt_telomere_finalize.sh"]
    for script in scripts:
        wa.run_command(["bash", str(workspace / script)], directory, script[:-3], 180, 6)
    for number, script in enumerate(sorted((workspace / "runs").glob("chr_*/command.sh"))):
        wa.run_command(["bash", str(script)], directory, f"chromosome-{number}", 180, 6)
    wa.run_command(["bash", str(workspace / "finalize_grt_evidence.sh")], directory, "finalize", 180, 6)
    if wa.sha256(result) != wa.sha256(paf):
        raise wa.ExperimentError("initial reference PAF changed during GRT")
    return workspace


def export_final(server, directory, workspace, validator):
    document = json.loads((workspace / "metadata/grt_final_path.json").read_text())
    tsv = directory / "FinalPath.tsv"
    with tsv.open("x") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("Chr", "#", "Ctg", "Origin ID", "overall_len", "orient", "Ctg_start", "Ctg_end", "Chr_start", "Chr_end"))
        for chromosome in document["chromosomes"]:
            start = 1
            for number, segment in enumerate(chromosome["segments"], 1):
                end = start + int(segment["length"]) - 1
                src = segment.get("source")
                values = ((src["dataset"] + "_" + src["contig"], src["contig"], "", src["orientation"], src["start"], src["end"])
                          if src else ("Gap", "NA", "", "+", 1, segment["length"]))
                writer.writerow((chromosome["chr"], number, *values, start, end))
                start = end + 1
    out = directory / "FinalPath.fa"
    wa.run_command(["bash", str(server / "export_final_path_fasta.sh"), "--gpm_server", str(workspace),
                    "--tsv", str(tsv), "-o", str(out)], directory, "export", 120, 6)
    return validator.fasta_dna(out)


def event_semantics(rows, references):
    # Drop only generated trace identities. Keep every scientific/event field,
    # including cross-gap coverage, output intervals, source-card provenance,
    # and future fields; strict raw JSON remains in raw_metadata as well.
    trace = {"run_id", "event_id", "evidence_ids", "usage_ids", "final_path_segment_id"}
    return [references.normalize({key: value for key, value in row.items() if key not in trace}) for row in rows]


def compare(server, roots, directories):
    validator = load_module(server / "validation/grt_formal_optimized.py", "formal_validation")
    semantic = load_module(server / "validation/grt_semantic_review.py", "semantic_validation")
    checks, raw = [], []

    def check(label, values, category="scientific"):
        item = {"label": label, "category": category, "equal": values[0] == values[1],
                "sha256": [validator.identity(v) for v in values]}
        if not item["equal"]:
            item["values"] = values  # Retain actual differences, not just counts.
        checks.append(item)

    # Keep exact comparison for all scientific metadata; generated identities and
    # source file fingerprints are not silently waived by this raw audit.
    for relative in sorted({str(p.relative_to(root)) for root in roots
                            for p in (root / "metadata").glob("grt_*") if p.is_file()}):
        hashes = [wa.sha256(root / relative) if (root / relative).is_file() else None for root in roots]
        raw.append({"path": relative, "equal": hashes[0] == hashes[1], "sha256": hashes})
    check("chromosome assignments", [read_tsv(r / "metadata/chr_assignments.tsv") for r in roots])
    for q in ("q0", "q1", "q2", "q3", "q4"):
        check(f"{q} ordered DNA", [validator.fasta_dna(r / f"grt/q/{q}.fa") for r in roots])
    events = [[json.loads(line) for line in (root / "metadata/grt_events.jsonl").read_text().splitlines() if line.strip()]
              for root in roots]
    refs = [semantic.References(root, rows, validator) for root, rows in zip(roots, events)]
    check("complete ordered event semantics except generated trace IDs", [event_semantics(rows, ref) for rows, ref in zip(events, refs)])
    for name in ("grt_q_segments.tsv", "grt_donor_fragments.tsv", "grt_donor_members.tsv", "grt_contig_roles.tsv"):
        rows = [read_tsv(root / "metadata" / name) for root in roots]
        if name == "grt_q_segments.tsv":
            check("all Q versions ordered source paths", [validator.paths(value) for value in rows])
            check("all Q versions source card lineage", [
                ref.normalize([{k: v for k, v in row.items() if k not in {"segment_id", "evidence_ids_json"}} for row in value])
                for ref, value in zip(refs, rows)])
        else:
            check(f"strict {name}", rows, "strict_audit")
    check("final events semantic projection", [ref.normalize(validator.events(rows)) for ref, rows in zip(refs, events)], "audit_projection")
    check("final accepted events semantic projection", [ref.normalize(validator.events([r for r in rows if r.get("status") == "accepted"]))
                                                        for ref, rows in zip(refs, events)])
    for stage in ("step2", "step3"):
        results = [json.loads((root / f"grt/evidence/{stage}/result.json").read_text()) for root in roots]
        check(f"{stage} ordered source paths", [validator.paths(r["q_rows"]) for r in results])
        for field in ("accepted_intervals", "usage_rows", "attempts", "strategies" if stage == "step2" else "classification_rows"):
            # Run identities remain differences here. The metadata projection
            # above is reported separately and never changes this strict check.
            check(f"{stage} strict {field}", [r[field] for r in results], "strict_audit")
        for name in ("candidates.tsv", "rejections.tsv"):
            paths = [root / f"grt/evidence/{stage}/{name}" for root in roots]
            if any(p.exists() for p in paths):
                check(f"{stage} strict {name}", [read_tsv(p) if p.exists() else None for p in paths], "strict_audit")
    documents = [json.loads((root / "metadata/grt_final_path.json").read_text()) for root in roots]
    check("Final Path ordered kinds sources orientations DNA", [validator.final_path(d) for d in documents])
    for root, directory in zip(roots, directories):
        exported = export_final(server, directory, root, validator)
        check(f"{directory.name} Final Path export equals q4", [validator.fasta_dna(root / "grt/q/q4.fa"), exported])
    return {"checks": checks, "raw_metadata": raw,
            "scientific_projection_equal": all(c["equal"] for c in checks if c["category"] == "scientific"),
            "all_checks_equal": all(c["equal"] for c in checks),
            "raw_metadata_equal": all(c["equal"] for c in raw),
            "raw_different_files": [c["path"] for c in raw if not c["equal"]],
            "accepted_event_counts": [sum(r.get("status") == "accepted" for r in rows) for rows in events],
            "accepted_event_actions": [[r.get("action") for r in rows if r.get("status") == "accepted"] for rows in events]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimap2", required=True)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    mm = shutil.which(args.minimap2)
    if not mm or Path(shutil.which("minimap2") or "").resolve() != Path(mm).resolve():
        parser.error("PATH minimap2 must match the explicit experimental binary for real GRT comparisons")
    cases = fixtures()
    if args.case and set(args.case) - {c[0] for c in cases}:
        parser.error("unknown fixture")
    root, server = args.out.resolve(), args.server_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    summary = {"status": "running", "production_ready": False, "customer_validated": False,
               "harness_sha256": wa.sha256(Path(__file__)),
               "server_prepare_sha256": wa.sha256(server / "prepare.sh"),
               "scope": "initial reference PAF only; self skipped; independent GRT alignments unchanged; no native App",
               "tool": {"path": mm, "sha256": wa.sha256(Path(mm)), "version": subprocess.check_output([mm, "--version"], text=True).strip()},
               "cases": []}
    try:
        for name, references, sequences, donors in cases:
            if args.case and name not in args.case:
                continue
            directory = root / name
            directory.mkdir()
            target, query = directory / "target.fa", directory / "query.fa"
            write_fasta(target, references)
            write_fasta(query, sequences)
            donor = directory / "donor.fa" if donors else None
            if donor:
                write_fasta(donor, donors)
            input_paths = [target, query, *([donor] if donor else [])]
            before_hashes = [wa.sha256(p) for p in input_paths]
            baseline, candidate = directory / "baseline", directory / "candidate"
            baseline.mkdir()
            candidate.mkdir()
            paf = baseline / "initial.paf"
            wa.run_command([mm, "-c", "--eqx", "-x", "asm10", "-t", "2", "-o", str(paf), str(target), str(query)], baseline, "map", 60, 6)
            windowed = directory / "windowed"
            wa.experiment(argparse.Namespace(target=target, query=query, out=windowed, minimap2=mm, preset="asm10",
                                            core_bases=200_000, context_bases=10_000, threads=2, timeout=60,
                                            memory_gib=6, require_full_query_coverage=False))
            stitched = windowed / "stitched.experimental.paf"
            record = {"case": name, "inputs_sha256": before_hashes,
                      "relation_equal": relation_signature(paf) == relation_signature(stitched), "status": "running",
                      "confidence": {"baseline": confidence_summary(paf), "stitched": confidence_summary(stitched)},
                      "ranking_equivalence": "not_established"}
            summary["cases"].append(record)
            wa.write_json(root / "comparison.json", summary)
            workspaces = [run_grt(server, d, target, query, p, donor) for d, p in ((baseline, paf), (candidate, stitched))]
            result = compare(server, workspaces, (baseline, candidate))
            wa.write_json(directory / "comparison.json", result)
            record.update(status="completed", **{k: v for k, v in result.items() if k not in ("checks", "raw_metadata")},
                          failed_checks=[c["label"] for c in result["checks"] if not c["equal"]])
            record["coordinate_and_downstream_equal"] = record["relation_equal"] and record["all_checks_equal"]
            if before_hashes != [wa.sha256(p) for p in input_paths]:
                raise wa.ExperimentError("fixture inputs changed")
            print(json.dumps(record), flush=True)
        summary["status"] = "completed_comparisons_not_production_acceptance"
    except BaseException as exc:
        summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        wa.write_json(root / "comparison.json", summary)


if __name__ == "__main__":
    main()
