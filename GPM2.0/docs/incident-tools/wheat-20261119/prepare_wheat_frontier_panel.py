"""Freeze bounded, natural JM19 panels from verified existing PAF/FASTA evidence.

Never runs a mapper or writes to the parent workspace. Retains ALL original
reference PAF records for each included whole contig, and all original base
PAF records between members. Not a whole-genome competitor search.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, digest, window_bytes, within
from lgz_core.common import write_fasta, write_tsv

# Chosen from assignment metadata alone before seeing supplemental results:
# small balanced, larger mixed, then dense repeat-heavy candidate inventory.
PANELS = (("4B", 358), ("5B", 596), ("3D", 589))


def tsv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def fai(path):
    with path.open(encoding="utf-8") as f:
        return {r[0]: tuple(map(int, r[1:5])) for line in f if (r := line.rstrip("\n").split("\t"))}


def cohorts(assignments, datasets, panels=PANELS):
    picked = {panel: {} for panel in panels}
    for row in assignments:
        n, start = int(row["seq_length_bp"]), row["anchor_start"]
        if not start or not 20_000 <= n <= 1_500_000 or float(row["support_percent"]) < 20:
            continue
        panel = row["assigned_chr_name"], (int(start) - 1) // 1_000_000
        if panel not in picked:
            continue
        key = (row["dataset_name"], row["seq_name"])
        if key in picked[panel]:
            raise ValueError("duplicate selected assignment")
        picked[panel][key] = n
    for panel, members in picked.items():
        if not 5 <= len(members) <= 128 or sum(members.values()) > 10_000_000:
            raise ValueError(f"invalid panel size: {panel}")
        if any(sum(k[0] == d for k in members) < 2 for d in datasets):
            raise ValueError(f"panel must contain both source assemblies: {panel}")
    return picked


def receipt_outputs(work, chromosome):
    directory = within(work, ".run_all/checkpoints")
    candidates = list(directory.glob(f"q0-chr-{chromosome}.*.json"))
    if len(candidates) != 1:
        raise ValueError("expected a unique original chromosome checkpoint")
    path = candidates[0]
    doc = json.loads(path.read_text())
    if doc.get("unit_id") != f"q0_chr:{chromosome}" or doc.get("status") != "success":
        raise ValueError("invalid original chromosome checkpoint")
    inputs = {r["path"]: r for r in doc["input_payload"]["inputs"]}
    return inputs, {r["path"]: r for r in doc["outputs"]}, digest(path)


def read_bound(path, receipt, consume):
    """One streaming pass over the frozen input; keep exactly selected rows."""
    before = path.stat()
    h = sha256()
    count = nbytes = 0
    with path.open("rb", buffering=1024**2) as stream:
        for line in stream:
            h.update(line)
            nbytes += len(line)
            if line.strip() and not line.startswith(b"#"):
                fields = line.split(b"\t", 6)
                if len(fields) != 7:
                    raise ValueError("malformed source PAF columns")
                consume(fields[0], fields[5], line)
                count += 1
    after = path.stat()
    ident = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if (ident(before) != ident(after) or nbytes != receipt["size"] or h.hexdigest() != receipt["sha256"]):
        raise ValueError(f"source PAF differs from its frozen receipt: {path.name}")
    return count


def freeze(work, out, lookup_path, index_receipt, *, panels=PANELS):
    if out.exists() or out.is_relative_to(work) or work.is_relative_to(out):
        raise ValueError("panel output must be a new isolated directory")
    if digest(lookup_path) != LOOKUP_SHA:
        raise ValueError("frozen whole-source lookup identity differs")
    lookup = json.loads(lookup_path.read_text())
    ref_receipt = json.loads(index_receipt.read_text())
    if ref_receipt.get("status") != "success":
        raise ValueError("invalid frozen reference index receipt")
    reference_records = {i["path"]: i for i in ref_receipt["inputs"]}
    datasets = {r["dataset_name"]: r for r in tsv(work / "metadata/datasets.tsv")}
    if set(datasets) != {"JM19_hifiasm", "JM19_flye_ABD"}:
        raise ValueError("unexpected natural JM19 input assemblies")
    reference, = tsv(work / "metadata/reference.tsv")
    lengths = {k: v[0] for k,v in fai(within(work, reference["fai_relpath"])).items()}
    sizes = {d: fai(within(work, row["fai_relpath"])) for d, row in datasets.items()}
    assignments = tsv(work / "metadata/chr_assignments.tsv")
    selected = cohorts(assignments, datasets, panels)
    by_source = {(r["dataset"],r["contig"]): r for r in lookup.values()}
    out.mkdir(exist_ok=False)
    report, paths = [], {}
    base_files = defaultdict(list)
    checkpoints = {}
    for (chr_name, mb), members in selected.items():
        root = out / f"{chr_name}-{mb}Mb"
        paths[chr_name, mb] = root
        root.mkdir()
        all_scientific, sequences = [], {}
        for dataset, row in datasets.items():
            seqs = {}
            for (d, name), n in sorted(members.items()):
                if d != dataset:
                    continue
                frozen = by_source[d, name]
                fa = sizes[d][name]
                if n != fa[0] or n != frozen["length"]:
                    raise ValueError("natural source lengths disagree")
                seq = window_bytes(within(work, row["fasta_relpath"]), fa, 0, n)
                if sha256(seq.encode("ascii")).hexdigest() != frozen["sequence_sha256"]:
                    raise ValueError("natural source content changed")
                seqs[name] = seq
            sequences[dataset] = seqs
            write_fasta(root / row["fasta_relpath"], seqs.items())
            all_scientific.append(row["fasta_relpath"])
        rows = [r for r in assignments if (r["dataset_name"], r["seq_name"]) in members]
        group = defaultdict(lambda: defaultdict(set))
        for r in rows:
            c, d, n = r["assigned_chr_name"], r["dataset_name"], r["seq_name"]
            group[c][d].add(n)
        for d, n in members:
            actual = {c for c, g in group.items() if n in g.get(d, ())}
            if actual != set(by_source[d,n]["original_assigned_chromosomes"]):
                raise ValueError("natural source assignment inventory changed")
        write_tsv(root / "metadata/chr_assignments.tsv", list(rows[0]), rows)
        write_tsv(root / "metadata/datasets.tsv", list(next(iter(datasets.values()))), datasets.values())
        write_tsv(root / "metadata/reference.tsv", ["fasta_relpath"], [{"fasta_relpath":"reference-lengths.json"}])
        (root / "reference-lengths.json").write_text(json.dumps(lengths, sort_keys=True)+"\n")
        all_scientific += ["metadata/chr_assignments.tsv", "metadata/datasets.tsv", "metadata/reference.tsv", "reference-lengths.json"]
        for d in datasets:
            relative = f"runs/{d}_vs_ref/result.paf"
            (root / relative).parent.mkdir(parents=True)
            all_scientific.append(relative)
        checkpoint_shas, base = {}, []
        for c, grouped in sorted(group.items()):
            if sum(len(v) for v in grouped.values()) < 2:
                continue
            if c not in checkpoints:
                inputs, outputs, checkpoint_sha = receipt_outputs(work,c)
                rel = f"runs/chr_{c}/q0_alignment_inputs.json"
                if digest(within(work,rel)) != inputs[rel]["sha256"]:
                    raise ValueError("original chr descriptor identity differs")
                desc = json.loads((work/rel).read_text())
                if desc["chromosome"] != c:
                    raise ValueError("wrong original chromosome descriptor")
                checkpoints[c] = outputs, checkpoint_sha, desc["alignments"]
            outputs, checkpoint_shas[c], alignments = checkpoints[c]
            for a in alignments:
                q, t = a["query_dataset"], a["target_dataset"]
                if q not in grouped or t not in grouped:
                    continue
                if q == t and len(grouped[q]) < 2:
                    continue
                relative = a["paf"]
                base_files[relative].append((root,outputs[relative],{k.encode() for k in grouped[q]},
                                            {k.encode() for k in grouped[t]}))
                all_scientific.append(relative)
                for dataset,suffix in ((q,"query_fasta"),(t,"target_fasta")):
                    file = a[suffix]
                    if file not in all_scientific:
                        write_fasta(root/file,[(k,sequences[dataset][k]) for k in sorted(grouped[dataset])])
                        all_scientific.append(file)
                base.append(a)
        (root / "base-alignments.json").write_text(json.dumps(base, sort_keys=True)+"\n")
        all_scientific.append("base-alignments.json")
        report.append({"panel":root.name,"members":len(members),"source_bases":sum(members.values()),
                       "chr_checkpoint_sha256":checkpoint_shas,"artifacts":sorted(all_scientific)})
        print(f"Selected natural inventory: {root.name}, {len(members)} contigs / {len(group)} assigned chromosomes", flush=True)
    source_base_bytes = sum(arms[0][1]["size"] for arms in base_files.values())
    if source_base_bytes > 14*1024**3:
        raise ValueError("frozen natural base evidence exceeds the diagnostic input budget")
    print(f"Reading {len(base_files)} distinct original base PAF files, {source_base_bytes} bytes",flush=True)
    for relative, arms in sorted(base_files.items()):
        streams=[]
        try:
            for root,receipt,q,t in arms:
                if receipt != arms[0][1]:
                    raise ValueError("original base receipt differs across panels")
                dest=root/relative
                dest.parent.mkdir(parents=True)
                streams.append((q,t,dest.open("wb")))
            def consume_base(query,target,line):
                for q,t,stream in streams:
                    if query in q and target in t:
                        stream.write(line)
            read_bound(within(work,relative), arms[0][1], consume_base)
        finally:
            for _,_,stream in streams:
                stream.close()
    for d in datasets:
        relative = f"runs/{d}_vs_ref/result.paf"
        streams=[]
        try:
            for panel, root in paths.items():
                names={k.encode() for ds,k in selected[panel] if ds == d}
                streams.append((names,(root/relative).open("wb")))
            def consume(query, _target, line):
                for names, stream in streams:
                    if query in names:
                        stream.write(line)
            read_bound(within(work,relative),reference_records[relative],consume)
        finally:
            for _, stream in streams:
                stream.close()
    for panel in report:
        root=out/panel["panel"]
        panel["artifacts"] = {name:digest(root/name) for name in panel["artifacts"]}
        (root / "panel.json").write_text(json.dumps(panel,sort_keys=True,indent=2)+"\n")
    (out / "report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("workspace","output","lookup","index-receipt"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    freeze(a.workspace.resolve(strict=True),a.output.resolve(),a.lookup.resolve(strict=True),a.index_receipt.resolve(strict=True))


if __name__ == "__main__":
    main()
