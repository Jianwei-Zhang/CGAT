"""Deterministic, synthetic report workspaces (not scientific datasets or importable App packages).
python -B server/tests/report_scenarios_fixture.py /tmp/new-report-fixtures
"""

import hashlib
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from workspace_layout import initialize_workspace, WorkspaceLayout, TOOL_DIRECTORIES
from server_report_io import SCHEMA, write_json, fasta_stats
from run_orchestration import sha256_file
from refinement_commit import inventory, targets, SCHEMA as COMMIT
from refine_report import automatic_overview_digest, INDEX_SCHEMA, REPORT_SCHEMA
from report_overview_data import build_overview_view_model
from render_server_report import render
from render_refinement_report import render_tool_pages
from refinement_overview import overview_html
from refinement_config import save_request
from refinement_tools import fingerprint
from job_final_catalog import _encode

RUN = "fixture-run"
BID = "c" * 32
AT = "2026-11-24T00:00:00+00:00"
PRIVATE = "/private/server/with spaces/reads.fq"
SCENARIOS = ("success", "lgz_only", "partial", "manual", "large", "legacy_v1", "v2_job", "v2_legacy")


def text(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(value, encoding="utf-8")
    return p


def archive(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w") as f:
        f.writestr(
            zipfile.ZipInfo("fixture.txt", (2026, 11, 24, 0, 0, 0)),
            b"Synthetic report fixture, not an App package.",
        )
    return sha256_file(p)


def workspace(root, scenario):
    if scenario not in SCENARIOS:
        raise ValueError(scenario)
    if root.exists() and any(root.iterdir()):
        raise ValueError("fixture target is not empty")
    project = scenario not in ("legacy_v1", "v2_job", "v2_legacy")
    root.mkdir(parents=True, exist_ok=True)
    l = (
        WorkspaceLayout.detect(root)
        if scenario == "legacy_v1"
        else initialize_workspace(
            root, prepared_runtime=".lib", job_outputs=project or scenario == "v2_job", project_delivery=project
        )
    )
    scientific = l.path("report")
    n = 21 if scenario == "large" else 2
    nper = 16 if scenario == "large" else 2
    names = [f"chr{i + 1}" for i in range(n)]
    sequence = "A" + ("N" * 100 + "C") * nper
    seq = "".join(f">{c}\n{sequence}\n" for c in names)
    fasta = text(l.path("grt/q/q3.fa"), seq)
    st = fasta_stats(fasta)
    text(
        l.path("runs/A_vs_ref/result.paf"),
        "".join(
            f"{c}\t{len(sequence)}\t0\t{len(sequence)}\t+\t{c}\t{len(sequence)}\t0\t{len(sequence)}\t{len(sequence)}\t{len(sequence)}\t60\n"
            for c in names
        ),
    )
    text(l.path("logs/run_all.log"), "Synthetic fixture run: reference alignment, q0, LGZ completed.\n")
    text(l.path("logs/status.tsv"), "unit_id\tstate\nref:A\tsuccess\nassign\tsuccess\n")
    text(l.path(".lib/README.txt"), "Fixture runtime location only; no executable tools.\n")
    for k in ("data/reference/ref.fa", "data/datasets/A.fa"):
        text(l.path(k), seq)
    paths = {
        "q4_relpath": "grt/q/q3.fa",
        "chromosomes": [
            dict(
                chr=c,
                q4_length=len(sequence),
                q4_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
                segments=[dict(kind="source", length=len(sequence), source={"dataset": "A", "contig": c})],
            )
            for c in names
        ],
    }
    write_json(l.path("metadata/grt_final_path.json"), paths)
    gaps = [
        dict(gap_id=f"gap-{c}-{i}", chromosome=c, start=1 + 101 * i, end=101 + 101 * i)
        for c in names
        for i in range(nper)
    ]
    tools = (
        {}
        if scenario not in ("success", "large", "partial")
        else {"degap": "published", "tgsgapcloser": "failed" if scenario == "partial" else "published"}
    )
    head = dict(schema_version=SCHEMA, run_id=RUN)
    q0 = dict(
        summary={"selected_chromosomes": n, "selected_source_bp": len(sequence) * n, "unknown_joins": 0}, tables={}
    )
    records = [
        ("ref:A", {"summary": {"aligned_query_count": n}}),
        ("assign", {"summary": {"assigned_unique_contigs": n, "unassigned_contigs": 0},
                    "tables": {"assignments": {"available": True,
                               "rows": [{"dataset_name": "A", "seq_name": c, "assigned_chr_name": c} for c in names]}}}),
        (
            "lgz_prepare",
            {
                "q0_construction": q0,
                "sequence_versions": {"q0": st},
                "tables": {
                    "donor_sets": {"available": True, "row_count": n, "rows": []},
                    "donor_members": {"available": True, "row_count": n, "rows": []},
                },
            },
        ),
    ]
    q0["source_bp_by_dataset"] = {"A": st["length_bp"]}
    for number in (1, 2, 3):
        stage = f"step{number}"
        parent = "grt_" + stage
        records.append((parent, {}))
        write_json(
            scientific / f"steps/grt-{stage}.json",
            dict(
                head,
                stage_id=stage,
                parent_unit=parent,
                title=stage,
                status="success",
                execution="computed",
                facts={
                    "summary": {"event_count": 1, "by_status": {"unresolved": 1}, "by_action": {"inspect": 1}},
                    "sequence_versions": {f"q{number - 1}": st, f"q{number}": st},
                    "result": {
                        "q_input_version": f"q{number - 1}",
                        "q_output_version": f"q{number}",
                        "events": [
                            {
                                "event_id": f"fixture-event-{number}",
                                "chr": names[0],
                                "stage": stage,
                                "status": "unresolved",
                                "action": "inspect",
                            }
                        ],
                    },
                },
            ),
        )
    for i, (unit, facts) in enumerate(records):
        write_json(
            scientific / f"steps/{i:03}.json",
            dict(
                head,
                stage_id=unit,
                title=unit,
                facts=facts,
                status="success",
                execution="computed",
                runtime={"elapsed_seconds": "2", "started_at": AT, "ended_at": AT},
            ),
        )
    write_json(
        scientific / "manifest.json",
        dict(
            head,
            status="success",
            workspace_name=root.name,
            started_at=AT,
            ended_at=AT,
            steps=[f"steps/{i:03}.json" for i in range(len(records))],
        ),
    )
    write_json(
        scientific / "inputs.json",
        dict(
            head,
            status="success",
            facts={
                "package": {"rows": [{"chr_assignment_min_coverage_percent": "12.5"}]},
                "datasets": [dict(name=v, role=r, stats=st) for v, r in [("ref", "reference"), ("A", "primary")]],
                "typed_reads": [dict(technology="hifi", file_count=1)] if tools else [],
            },
        ),
    )
    write_json(
        scientific / "final_summary.json",
        dict(
            head,
            available=True,
            final_q_version="q3",
            final_path=paths,
            sequence_versions={q: st for q in ("q0", "q1", "q2", "q3")},
            annotations={
                "telomere": {
                    "configured": True,
                    "terminal_rows": [
                        {"chr": c, "terminal": "5prime", "final_status": "already_present"} for c in names
                    ],
                },
                "centromere": {
                    "configured": True,
                    "markers": [{"chr": c, "q4_start": 20, "q4_end": 40} for c in names],
                },
            },
            process_summary={"event_count": 3, "by_status": {"unresolved": 3}, "by_action": {"inspect": 3}},
            outcome_summary={"remaining_gap_count": len(gaps)},
            q0_construction=q0,
        ),
    )
    render(scientific)
    batch = dict(
        schema="cgat.refinement-batch",
        schema_version=1,
        batch_id=BID,
        status="partial_failure" if scenario == "partial" else "published" if tools else "not_requested",
        exit_code=int(scenario == "partial"),
        tools={},
    )
    rows = []
    tool_cells = {}
    catalog = []
    variants = {}
    for i, (tool, status) in enumerate(tools.items()):
        code = TOOL_DIRECTORIES[tool]
        run = str(i + 1) * 32
        tx = str(i + 3) * 32
        rec = dict(status=status, phase="native" if status == "failed" else "published", run_id=run)
        batch["tools"][tool] = rec
        c = None
        cells = []
        if status == "published":
            dirs = targets(l, tool)
            states = (
                ["rejected" if j == 0 else "unfilled" for j in range(len(gaps))]
                if scenario == "partial"
                else ["closed" if j % 2 == i else "unfilled" for j in range(len(gaps))]
            )
            c = {key: states.count(key) for key in ("closed", "partial", "rejected", "unfilled")}
            cells = states
            exc = {"native_executed": True, "native_reused": False, "threads": 2, "recipe": {"reads": []}}
            edits = [
                {
                    "edit_id": "edit-" + g["gap_id"],
                    "gap_ids": [g["gap_id"]],
                    "evidence": {},
                    "native_job": "fixture",
                }
                for g, s in zip(gaps, states)
                if s == "closed"
            ]
            accepted = sum(s == "closed" for s in states)
            final = dict(edits=edits, original_gaps=gaps, chromosomes=[])
            prov = dict(
                tool=tool,
                run_id=run,
                execution=exc,
                accepted_edit_count=accepted,
                gap_outcomes=[
                    dict(g, status=s, edit_ids=["edit-" + g["gap_id"]] if s == "closed" else [])
                    for g, s in zip(gaps, states)
                ],
                rejected_candidates=[],
            )
            if scenario == "partial":
                prov["rejected_candidates"] = [
                    dict(
                        gap_ids=[gaps[0]["gap_id"]],
                        reason="incomplete closure",
                        flank_decisions=[
                            dict(
                                decision="retained_lgz",
                                side="left",
                                baseline_interval=[0, 1],
                                native_interval=[0, 2],
                                native_length_delta_bp=1,
                            )
                        ],
                    )
                ]
            write_json(dirs["final"] / "provenance.json", prov)
            versions = {
                c: "A"
                + "".join(
                    ("A" * 100 if states[ci * nper + j] == "closed" else "N" * 100) + "C" for j in range(nper)
                )
                for ci, c in enumerate(names)
            }
            text(dirs["final"] / "assembly.fa", "".join(f">{c}\n{v}\n" for c, v in versions.items()))
            write_json(dirs["final"] / "final_path.json", final)
            site = dirs["report"]
            summary = dict(
                schema="cgat.refinement-report",
                schema_version=1,
                tool=tool,
                run_id=run,
                execution=exc,
                counts=c,
                retained_flank_count=int(scenario == "partial"),
                original_gap_count=len(gaps),
                remaining_gap_count=len(gaps) - accepted,
                accepted_edit_count=accepted,
                outcome="completed",
                chromosomes=[
                    dict(
                        chromosome=c,
                        accepted_length=len(v),
                        accepted_n_bases=v.count("N"),
                        accepted_sha256=hashlib.sha256(v.encode()).hexdigest(),
                        native=None,
                        native_equals_accepted=None,
                    )
                    for c, v in versions.items()
                ],
                native_jobs=[],
                native_gaps_by_original={},
                artifacts=[],
            )
            write_json(site / "summary.json", summary)
            write_json(site / "final_path.json", final)
            text(site / "native_visualization/index.html", "<p>Synthetic offline native index</p>")
            for name, html in render_tool_pages(summary, prov, final, []):
                text(site / name, html)
            write_json(
                site / "manifest.json",
                dict(
                    schema="cgat.refinement-report",
                    schema_version=1,
                    binding={"provenance_sha256": sha256_file(dirs["final"] / "provenance.json")},
                    files=inventory(site)["files"],
                ),
            )
            light = "d" * 64
            write_json(dirs["delivery"] / "delivery.json", {"light_manifest": light})
            variants[tool] = dict(run_id=run, light_manifest=light)
            journal = dict(
                schema=COMMIT,
                schema_version=1,
                state="committed",
                transaction=tx,
                run_id=run,
                tool=tool,
                areas={k: {"new": inventory(v)} for k, v in dirs.items()},
            )
            j = l.path(f".runtime/refinement/publications/{tx}/journal.json")
            write_json(j, journal)
            write_json(
                l.path(f".runtime/refinement/publication/{tool}.json"),
                dict(schema=COMMIT, tool=tool, status="committed", transaction=tx, journal_sha256=sha256_file(j)),
            )
            rec.update(
                publication_transaction=tx,
                report={
                    "manifest_sha256": sha256_file(site / "manifest.json"),
                    "report": str(site / "report.html"),
                    "directory": str(site),
                },
            )
        else:
            rec["error"] = "Native command exited 19"
            cells = ["tool_failed"] * len(gaps)
        tool_cells[tool] = cells
        rows.append(
            dict(tool=tool, status=status, counts=c, publication_transaction=rec.get("publication_transaction"))
        )
    if tools:
        base = l.path("06_report/03_comparison/" + BID)
        write_json(base / "original_gaps.json", gaps)
        write_json(
            base / "comparison.json",
            dict(
                schema="cgat.refinement-comparison",
                schema_version=1,
                batch_id=BID,
                batch_status=batch["status"],
                baseline_valid=True,
                original_gap_count=len(gaps),
                tools=rows,
                best_tool=None,
                biological_accuracy_validated=False,
            ),
        )
        text(
            base / "gap_comparison.tsv",
            "gap_id\tchromosome\tstart\tend\t"
            + "\t".join(tools)
            + "\n"
            + "".join(
                "\t".join(
                    [
                        g["gap_id"],
                        g["chromosome"],
                        str(g["start"]),
                        str(g["end"]),
                        *[tool_cells[t][i] for t in tools],
                    ]
                )
                + "\n"
                for i, g in enumerate(gaps)
            ),
        )
    if l.result_prefix:
        for tool in ("lgz", *tools):
            if tools.get(tool) == "failed":
                continue
            name = f"{root.name}.{tool}.fa"
            p = text(
                l.path("05_final/" + name),
                seq if tool == "lgz" else (targets(l, tool)["final"] / "assembly.fa").read_text(),
            )
            catalog.append(
                [
                    tool,
                    RUN,
                    "published",
                    "completed",
                    str(tool_cells.get(tool, []).count("closed")),
                    name,
                    sha256_file(p),
                    batch["tools"].get(tool, {}).get("publication_transaction", "lgz-fixture"),
                ]
            )
        cat = l.path("05_final/results.tsv")
        cat.write_bytes(_encode(catalog))
        write_json(l.path(".runtime/refinement/final_catalog/results.tsv.json"), {"next": sha256_file(cat)})
    if project:
        files = {}
        for mode in ("full", "light", *(["auto"] if tools else [])):
            name = root.name + "." + ("auto.patch" if mode == "auto" else mode) + ".zip"
            p = l.path("07_delivery/" + name)
            sha = archive(p)
            files[mode] = dict(file=name, sha256=sha, size_bytes=p.stat().st_size)
        if "auto" in files:
            from project_auto_patch import patch_path

            patch_path(l).parent.mkdir(parents=True, exist_ok=True)
            patch_path(l).write_bytes(l.path("07_delivery/" + files["auto"]["file"]).read_bytes())
            write_json(
                l.path(".runtime/refinement/project-delivery/auto-patch.json"),
                {"generation": "f" * 64, "sha256": files["auto"]["sha256"]},
            )
        write_json(
            l.path(".runtime/refinement/project-delivery/committed.json"),
            dict(
                schema="cgat.project-delivery-publication",
                schema_version=1,
                generation="f" * 64,
                files=files,
                tools=variants,
            ),
        )
    if scenario == "manual":
        entries = []
        for token, status in [("e", "pending_app_import"), ("f", "no_patch")]:
            bid = token * 64
            patch = l.path(f"07_delivery/manual/{root.name}.manual-{bid[:16]}.patch.zip")
            sha = archive(patch)
            row = dict(
                batch_sha256=bid,
                report_status=status,
                completed_at=AT,
                results=[
                    dict(
                        tool="degap",
                        status="closed" if token == "e" else "no_candidate",
                        patch={} if token == "e" else None,
                    )
                ],
            )
            entries.append(row)
            home = l.path("04_refinement/manual/" + bid + "/03_report")
            write_json(
                home.parent / "manual-delivery.json",
                dict(batch=bid, state="committed", relative=patch.relative_to(root).as_posix(), sha256=sha),
            )
            text(home / "report.html", "legacy manual report")
            write_json(
                home / "summary.json",
                dict(
                    row,
                    report_schema=REPORT_SCHEMA,
                    reads={"degap": [dict(technology="hifi", path=PRIVATE, sha256="b" * 64)]},
                    delivery=str(patch.relative_to(root)),
                    delivery_sha256=sha,
                ),
            )
        write_json(l.path("06_report/manual_refinement.json"), dict(schema=INDEX_SCHEMA, batches=entries))
    if scenario == "manual":
        text(l.path("06_report/report.html"), overview_html(l, mode="manual_only"))
    if project and scenario != "manual":
        request = save_request(
            root, {"--gapfill-tools": [[",".join(tools)]], "--hifi": [[PRIVATE]]} if tools else {}, RUN
        )
        baseline = l.path("05_final/00_lgz")
        text(baseline / "assembly.fa", seq)
        write_json(baseline / "provenance.json", {"tool": "lgz"})
        write_json(baseline / "final_path.json", paths)
        write_json(
            l.path(".runtime/refinement/lgz_baseline.json"),
            dict(
                schema="cgat.lgz-baseline-publication",
                state="committed",
                binding={
                    "final_path_sha256": sha256_file(l.path("metadata/grt_final_path.json")),
                    "assembly_sha256": sha256_file(fasta),
                },
                files=inventory(baseline),
            ),
        )
        bf = l.path(".runtime/refinement/batches/" + BID + ".json")
        write_json(bf, batch)
        report = l.path("06_report/report.html")
        text(report, overview_html(l, batch))
        members = {"06_report/report.html": automatic_overview_digest(report)}
        if tools:
            members.update({str(p.relative_to(root)): sha256_file(p) for p in base.iterdir()})
        write_json(
            l.path(f".runtime/refinement/completions/{RUN}.json"),
            dict(
                schema="cgat.refinement-invocation",
                schema_version=1,
                run_id=RUN,
                batch_id=BID,
                batch_sha256=sha256_file(bf),
                request_sha256=fingerprint(request),
                exit_code=batch["exit_code"],
                overview_files=members,
                final_catalog_sha256=sha256_file(cat),
                auto_patch_sha256=files.get("auto", {}).get("sha256"),
            ),
        )
    return build_overview_view_model(root, generated_at=AT)


if __name__ == "__main__":
    for name in SCENARIOS:
        root = Path(sys.argv[1]).resolve() / name
        vm = workspace(root, name)
        write_json(root.parent / (name + ".json"), vm)
