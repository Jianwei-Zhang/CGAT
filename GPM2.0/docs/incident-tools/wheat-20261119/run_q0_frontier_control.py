"""Prospective full/targeted Q0 control on artificial fragments of real DNA.

Run with GPM2.0 and GPM2.0/server/tools on PYTHONPATH. Both arms run real
minimap2 in fresh scratch workspaces; no ready artifacts survive this probe.
The coordinate fixture holds out initial cross alignments on purpose.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from lgz_core import q0_preparation as prep
from lgz_core.common import stable_id
from lgz_core.q0_admission import construct_q0, load_evidence_input
from lgz_core.q0_regional_execution import RegionalExecutor
from probe_q0_decision_frontier import compare, decision_frontier, member_geometry, subset_input
from server.tests.q0_test_support import seed_q0_evidence
from server.tests.test_q0_admission import EvidenceFixture

SLICES = {"chr1": (0, 2_000_000), "chr2": (2_800_000, 2_810_000)}
FRAGMENTS = {"chr1": ((100_000, 900_000), (940_000, 1_850_000), (795_000, 1_075_000),
                      (360_000, 570_000), (1_335_000, 1_520_000)),
             "chr2": ((0, 4400), (5200, 10_000), (3600, 6000))}


def read_control(path):
    need = max(b for _, b in SLICES.values())
    with path.open(encoding="ascii") as f:
        first = next(f)
        if not first.startswith(">"):
            raise ValueError("control source must be a FASTA")
        lines, n = [], 0
        for raw in f:
            if raw.startswith(">"):
                break
            row = raw.strip()
            n += len(row)
            lines.append(row)
            if n >= need:
                break
    if n < need:
        raise ValueError("first reference record is shorter than the bounded control")
    text = "".join(lines).upper()
    return first[1:].split()[0], {k: text[a:b] for k, (a, b) in SLICES.items()}


def filtered_dispatch(data, frontier, counts):
    original = RegionalExecutor.completed

    def completed(self, requests):
        for ordinal, request, (planned, native, reason) in original(self, requests):
            kept = []
            for query, targets in planned:
                for w in (query, *targets):
                    source, span = member_geometry(w.record(), data.parts)
                    if any(span.intersection(i) for i in frontier.get(source, ())):
                        kept.append((query, targets))
                        break
            counts["scheduled"] += len(kept)
            counts["omitted"] += len(planned) - len(kept)
            # Retained regional work and all native fallbacks are identical.
            yield ordinal, request, (kept, native, reason)
    return completed


def work(root, refs, mapper, targeted, threads):
    fixture = EvidenceFixture({k: len(v) for k, v in refs.items()})
    fixture.reference_sequences = refs
    for chr_name, seq in refs.items():
        for i, (a, b) in enumerate(FRAGMENTS[chr_name]):
            k = fixture.source(f"{chr_name}_s{i + 1}", seq[a:b])
            fixture.ref(k, (0, b - a), (a, b), chromosome=chr_name)
    workspace = fixture.workspace(root)
    version = subprocess.check_output([mapper, "--version"])
    for source in fixture.sources:
        p = workspace / "runs" / f"{source.dataset}_vs_ref"
        with (p / "result.paf").open("wb") as out, (p / "ref.stderr.log").open("wb") as err:
            subprocess.run([mapper, "-cx", "asm10", "-t", "2", str(workspace / "data/reference/ref.fa"),
                            str(workspace / "data/datasets" / f"{source.dataset}.fa")],
                           check=True, stdout=out, stderr=err)
        (p / "tool_version.txt").write_bytes(version)
    seed_q0_evidence(workspace)  # Rebind fixture checkpoints to real ref PAFs.
    count = {"scheduled": 0, "omitted": 0}
    decision_seconds = None
    if targeted:
        start = time.monotonic()
        d = load_evidence_input(workspace)
        frontier = decision_frontier(construct_q0(subset_input(d, set())), 100_000)
        dispatch = filtered_dispatch(d, frontier, count)
        decision_seconds = time.monotonic() - start
    else:
        dispatch = RegionalExecutor.completed
    path = str(root / "q0-fixture-bin") + os.pathsep + os.environ["PATH"]
    start = time.monotonic()
    # Lab only: force the large-genome route, retain ordinary mapper options,
    # and restrict the dispatcher inside this process, never on production data.
    with (patch.object(prep, "regional_enabled", return_value=True),
          patch.dict(os.environ, {"PATH": path}),
          patch.object(RegionalExecutor, "completed", dispatch), redirect_stdout(sys.stderr)):
        ready = prep.prepare_evidence(workspace, threads=threads, minimap2=mapper)
    seconds = time.monotonic() - start
    data = load_evidence_input(workspace)
    tasks = data.catalog["supplementary_alignments"]
    scientific_inputs = [r for r in ready["inputs"] if r["path"].endswith((".fa", "/result.paf", ".tsv"))]
    return construct_q0(data), {"preparation_seconds": seconds, "base_load_and_decision_seconds": decision_seconds,
                                "regional_tasks": sum(t["kind"] == "regional_discovery" for t in tasks),
                                "native_tasks": sum(t["kind"] != "regional_discovery" for t in tasks),
                                "dispatch_audit": count if targeted else None,
                                "workspace_ready_input_fingerprint": ready["input_fingerprint"],
                                "scientific_inputs_identity": stable_id("q0-control-input", scientific_inputs)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reference", type=Path, help="read-only real FASTA, first record >=2.81 Mb")
    p.add_argument("--mapper", default="minimap2")
    p.add_argument("--threads", type=int, default=6, choices=(2, 4, 6))
    a = p.parse_args()
    mapper = str(Path(shutil.which(a.mapper) or a.mapper).resolve(strict=True))
    name, refs = read_control(a.reference)
    report = {"scope": "artificial fragmentation with real DNA and real minimap2; not natural assembly recall",
              "record": name, "source_slices": SLICES, "fragments": FRAGMENTS,
              "ref_slice_sha256": {k: sha256(v.encode("ascii")).hexdigest() for k, v in refs.items()},
              "mapper": subprocess.check_output([mapper, "--version"], text=True).strip(), "runs": []}
    reference_result = None
    with tempfile.TemporaryDirectory(prefix="q0-frontier-control-") as directory:
        for i, targeted in enumerate((False, True, True, False)):
            root = Path(directory) / str(i)
            root.mkdir()
            result, row = work(root, refs, mapper, targeted, a.threads)
            if reference_result is None:
                reference_result = result
            row.update(mode="frontier" if targeted else "full", against_first_full=compare(reference_result, result),
                       matches_control_reference={k: result.records.get(k) == v for k, v in refs.items()})
            report["runs"].append(row)
    if len({row["scientific_inputs_identity"] for row in report["runs"]}) != 1:
        raise ValueError("control arm source, base alignments or scientific metadata differ")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
