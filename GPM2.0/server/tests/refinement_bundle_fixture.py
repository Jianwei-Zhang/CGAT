"""Controlled admission over a real frozen LGZ bundle; not a native tool run.

The exact serializer output is frozen for cross-language App contract tests.
"""
import hashlib
from contextlib import ExitStack
import os
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout, initialize_workspace
from refinement_sources import FastaCatalog
from refinement_path import Edit, inspect_baseline
from refinement_degap import materialize_patches
from refinement_publication import prepare_publication
from refinement_reports import build_tool_report
from refinement_bundle import build_full, build_light, read_table, write_table
from refinement_bundle_validate import validate_payload
from post_lgz_degap import digest, atomic_json
from refinement_tools import fingerprint

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/grt_contract_v3/frozen_bridge_server.json"


def _populate_initial(root, layout):
    original = json.loads(FIXTURE.read_text())
    for name, contents in original["files"].items():
        target = layout.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    # Real preparation writes numbered locator values and partition FASTAs
    # whose headers/offsets differ from the complete dataset index. Exercise
    # those paths rather than only a byte-relocated legacy fixture.
    from lgz_core.common import read_fasta
    locator = layout.path("metadata/source_seq_locator.tsv")
    fields, rows = read_table(locator)
    for row in rows:
        original_fasta = layout.path(row["fasta_relpath"])
        records = dict(read_fasta(original_fasta))
        sequence = records[row["seq_name"]]
        partition = layout.path(f"data/partitions/controlled/{row['dataset_name']}/{row['seq_name']}.fa")
        partition.parent.mkdir(parents=True, exist_ok=True)
        partition.write_text(">" + row["seq_name"] + " partitioned-source-context\n" + "\n".join(sequence[i:i + 47] for i in range(0, len(sequence), 47)) + "\n")
        row["fasta_relpath"] = partition.relative_to(root).as_posix()
    write_table(locator, fields, rows)
    for name in ("reference.tsv", "datasets.tsv", "reference_chr_locator.tsv"):
        path = layout.path("metadata/" + name)
        fields, rows = read_table(path)
        for row in rows:
            for key in fields:
                if key.endswith("_relpath") and row[key]:
                    row[key] = layout.relative(row[key])
        write_table(path, fields, rows)


def create(root, *, with_source_evidence=False, with_source_annotations=False, native_diagnostics=None, job_outputs=False,
           tool="degap", reuse_workspace=False):
    layout = WorkspaceLayout.detect(root) if reuse_workspace else initialize_workspace(root, job_outputs=job_outputs)
    if not reuse_workspace:
        _populate_initial(root, layout)
    code = TOOL_DIRECTORIES[tool]
    run_id = "a" * 32 if tool == "degap" else "b" * 32
    final_file = layout.path("metadata/grt_final_path.json")
    baseline = json.loads(final_file.read_text())
    fasta = layout.path(baseline["q4_relpath"])
    private = root / f".runtime/refinement/{code}" / run_id
    catalog = FastaCatalog(root, private / "fixture-indexes")
    catalog.load_workspace()
    gaps, _ = inspect_baseline(baseline, catalog)
    gap = gaps[0]
    native = root / f"04_refinement/{code}/03_native" / run_id
    native.mkdir(parents=True)
    candidate = native / "controlled_candidate.fa"
    candidate.write_text(">candidate\nGTNNAC\n")
    catalog.register("controlled_native", "candidate", candidate, origin="controlled-admission-fixture")
    edit = Edit("fixture-edit", tool, gap.chromosome, gap.start, gap.end,
                {"dataset": "controlled_native", "contig": "candidate", "start": 1, "end": 6, "orientation": "+"},
                (gap.gap_id,), "controlled-not-native-engine", {"fixture": "controlled admission; native engine not executed"})
    accepted = root / f"04_refinement/{code}/04_accepted" / run_id
    accepted.mkdir(parents=True)
    edits = materialize_patches([edit], catalog, accepted, tool=tool)
    jobs = root / f"04_refinement/{code}/02_jobs" / run_id
    jobs.mkdir(parents=True)
    log = jobs / "native.log"
    log.write_text("Controlled admission fixture; no native engine was executed.\n")
    recipe = {"name": "controlled-admission-fixture", "revision": "0" * 40, "reads": []}
    execution = {"status": "success", "tool": tool, "run_id": run_id, "baseline_sha256": digest(fasta),
                 "recipe": recipe, "recipe_sha256": fingerprint(recipe), "threads": 1, "native_executed": False,
                 "artifacts": {log.relative_to(root).as_posix(): digest(log)}}
    staging = private / "final"
    provenance = prepare_publication(staging, baseline, fasta, catalog, edits, execution, [])
    atomic_json(jobs / "invocation.json", {"status": "staged", "tool": tool, "run_id": run_id,
                                         "provenance_sha256": digest(staging / "provenance.json")})
    result = {"tool": tool, "run_id": run_id, "staging": str(staging), "provenance": provenance}
    with ExitStack() as stack:
        if with_source_annotations:
            from refinement_source_evidence_fixture import frozen_rules, controlled_mummer
            from unittest import mock
            frozen_rules(root)
            folder = controlled_mummer(root.parent)
            stack.enter_context(mock.patch.dict(os.environ, {"PATH": str(folder) + os.pathsep + os.environ["PATH"]}))
        if with_source_evidence:
            from refinement_source_evidence import build
            result["source_evidence"] = build(root, result, 1)
        if native_diagnostics is not None:
            native_diagnostics(native, gap)
        report = build_tool_report(root, result)
        full, light = root / ".runtime/app-fixture/full", root / ".runtime/app-fixture/light"
        if reuse_workspace:
            full, light = full.parent / (tool + "-full"), light.parent / (tool + "-light")
        build_full(root, result, report, full)
        build_light(full, light)
        validate_payload(full, full=True)
        validate_payload(light, full=False)
        return result, full, light


def freeze(output, *, with_source_evidence=False, with_source_annotations=False):
    import tempfile
    with tempfile.TemporaryDirectory(prefix="cgat-refined-app-fixture-") as temporary:
        _, full, _ = create(Path(temporary) / "workspace", with_source_evidence=with_source_evidence, with_source_annotations=with_source_annotations)
        files = {path.relative_to(full).as_posix(): path.read_text(encoding="utf-8") for path in sorted(full.rglob("*")) if path.is_file()}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"fixture_schema": "cgat.refined-app-fixture.v1",
            "provenance": "Controlled admission GTNNAC over frozen_bridge_server.json; real serializer and source reconstruction; no native engine executed." +
                (" Accepted sources have actual developer-base minimap2 no-hit measurements; no pinned-environment or four-engine acceptance claim." if with_source_evidence else "") +
                (" Telomere rules are controlled inputs; nucmer/show-coords are explicit controlled producers for annotation contract testing, not real MUMmer acceptance." if with_source_annotations else ""),
            "files": files}, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
        print(output, output.stat().st_size, "bytes", len(files), "files")


if __name__ == "__main__":
    freeze(Path(__file__).resolve().parents[2] / "tests/fixtures/refinement_app_v5/controlled_partial.json")
