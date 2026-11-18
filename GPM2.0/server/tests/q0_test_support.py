"""Explicit synthetic completed-alignment fixtures for legacy LGZ stage tests.

These fixtures do not measure assembly quality. They materialize the newly
required evidence stage so later-stage tests keep exercising their own contracts.
"""
from collections import defaultdict
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import sys
from unittest import mock

from server.tools.lgz_core.common import read_fasta, write_fasta
from server.tools.lgz_core.q0_preparation import prepare_evidence
from server.tools.run_outer_checkpoints import OuterCheckpointManager


def seed_q0_evidence(server: Path) -> None:
    def rows(name):
        with (server / "metadata" / name).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))
    datasets = rows("datasets.tsv")
    references = rows("reference.tsv")
    sources = {row["dataset_name"]: dict(read_fasta(server / row["fasta_relpath"])) for row in datasets}
    refs = dict(read_fasta(server / references[0]["fasta_relpath"]))
    groups = defaultdict(lambda: defaultdict(set))
    for row in rows("chr_assignments.tsv"):
        groups[row["assigned_chr_name"]][row["dataset_name"]].add(row["seq_name"])
    # Historic test PAFs specify synthetic geometry but omit cg. Add that explicit
    # synthetic path in the fixture only; production never invents CIGARs.
    for row in datasets:
        paf = server / f"runs/{row['dataset_name']}_vs_ref/result.paf"
        lines = []
        for raw in paf.read_text().splitlines():
            if not raw.strip():
                continue
            if raw.startswith("#"):
                lines.append(raw)
                continue
            fields = raw.split("\t")
            if not any(tag.startswith("cg:Z:") for tag in fields[12:]):
                q, t = int(fields[3]) - int(fields[2]), int(fields[8]) - int(fields[7])
                cigar = f"{min(q, t)}M" + (f"{q-t}I" if q > t else f"{t-q}D" if t > q else "")
                raw += "\tcg:Z:" + cigar
            lines.append(raw)
        paf.write_text("\n".join(lines) + ("\n" if lines else ""))
    fake_bin = server.parent / "q0-fixture-bin"
    fake_bin.mkdir(exist_ok=True)
    minimap = fake_bin / "minimap2"
    minimap.write_text(f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\n"
                       "if '--version' in sys.argv: print('q0-fixture-empty-aligner')\n"
                       "else: Path(sys.argv[sys.argv.index('-o')+1]).write_text('')\n")
    minimap.chmod(0o755)
    with mock.patch.dict(os.environ, {"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}):
        manager = OuterCheckpointManager(server)
        for chromosome in refs:
            run = server / f"runs/chr_{chromosome}"
            (run / "datasets").mkdir(parents=True, exist_ok=True)
            group = groups[chromosome]
            for dataset, names in sorted(group.items()):
                write_fasta(run / f"datasets/{dataset}.fa", [(name, sources[dataset][name]) for name in sorted(names)])
            entries, tasks = [], []
            names = sorted(group)
            pairs = [(name, name) for name in names if len(group[name]) > 1]
            pairs += [(left, right) for i, left in enumerate(names) for right in names[i+1:]]
            for left, right in pairs:
                stem = f"{left}_vs_self" if left == right else f"{left}_vs_{right}"
                operation = run / stem
                operation.mkdir(exist_ok=True)
                (operation / "command.sh").write_text("# synthetic completed chr alignment\n")
                if not (operation / "result.paf").is_file():
                    (operation / "result.paf").write_text("")
                relative = operation.relative_to(server).as_posix()
                entries.append({"kind": "self" if left == right else "cross",
                                "query_dataset": right, "target_dataset": left,
                                "query_fasta": f"runs/chr_{chromosome}/datasets/{right}.fa",
                                "target_fasta": f"runs/chr_{chromosome}/datasets/{left}.fa",
                                "run_dir": relative, "paf": relative + "/result.paf"})
                tasks.append({"command": relative + "/command.sh", "max_threads": 1, "priority": 0})
            for filename in ("q0_command.sh", "q0_generated_command.sh"):
                (run / filename).write_text("# synthetic q0 chr stage\n")
            (run / "q0_alignment_inputs.json").write_text(json.dumps({"version": 1, "chromosome": chromosome, "alignments": entries}))
            (run / "q0_alignment_tasks.json").write_text(json.dumps({"version": 3, "tasks": tasks}))
            prepared = manager.prepare(f"q0_chr:{chromosome}", f"runs/chr_{chromosome}/q0_command.sh")
            manager.commit(prepared)
        with contextlib.redirect_stdout(io.StringIO()):
            prepare_evidence(server, minimap2=str(minimap))
